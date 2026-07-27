//! Resolução robusta da `libonnxruntime` para o binário standalone (task #26 do M6).
//!
//! O `ort` (feature `load-dynamic`) carrega a lib em runtime via `ORT_DYLIB_PATH`.
//! O `.cargo/config.toml` seta esse env — mas **só sob `cargo`**. O binário standalone
//! (rodado fora do cargo) não herda esse env e o `ort` cai numa `libonnxruntime` lenta
//! do sistema, deixando a inferência **até 40× mais lenta** (`[MEDIDO]` 2026-07-27,
//! `training/results/runtime-eval-findings.md`). Este módulo garante que o binário
//! **encontre a lib otimizada vendorizada ou falhe alto** — nunca degrade em silêncio
//! (`.claude/rules/error-handling.md` § 1: fail-fast, fail-clear).

use std::path::{Path, PathBuf};

/// Localiza `vendor/onnxruntime-*/lib/libonnxruntime.so` subindo a partir de `start`.
/// Procura em cada ancestral um diretório `vendor/` com uma subpasta `onnxruntime-*`.
#[must_use]
pub fn find_ort_dylib(start: &Path) -> Option<PathBuf> {
    let mut cur = Some(start);
    while let Some(dir) = cur {
        if let Ok(entries) = std::fs::read_dir(dir.join("vendor")) {
            for e in entries.flatten() {
                if e.file_name().to_string_lossy().starts_with("onnxruntime-") {
                    let lib = e.path().join("lib").join("libonnxruntime.so");
                    if lib.is_file() {
                        return Some(lib);
                    }
                }
            }
        }
        cur = dir.parent();
    }
    None
}

/// Garante que `ORT_DYLIB_PATH` aponte para uma `libonnxruntime` real ANTES do primeiro
/// uso do `ort`. Ordem: (1) respeita um env já setado e válido; (2) resolve a vendorizada
/// relativa ao executável (deploy) e ao `CARGO_MANIFEST_DIR` (dev); (3) senão, erro claro.
///
/// # Erros
/// Mensagem acionável quando nenhuma lib é encontrada — melhor falhar do que rodar 40× lento.
pub fn ensure_ort_dylib() -> Result<PathBuf, String> {
    if let Ok(p) = std::env::var("ORT_DYLIB_PATH") {
        let path = PathBuf::from(&p);
        if path.is_file() {
            return Ok(path);
        }
    }
    let mut roots: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            roots.push(d.to_path_buf());
        }
    }
    roots.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));
    for r in &roots {
        if let Some(lib) = find_ort_dylib(r) {
            std::env::set_var("ORT_DYLIB_PATH", &lib);
            return Ok(lib);
        }
    }
    Err(format!(
        "libonnxruntime não encontrada (procurado em {roots:?} e ancestrais). Defina \
         ORT_DYLIB_PATH ou coloque a lib em vendor/onnxruntime-*/lib/libonnxruntime.so \
         (rode scripts/setup_onnxruntime.sh). Sem a lib otimizada o runtime fica até 40× \
         mais lento — falhando em vez de degradar em silêncio."
    ))
}
