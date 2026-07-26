//! PROVA end-to-end do runtime v0 em FALA REAL (plano m6-runtime-v0, validação de integração).
//!
//! Alimenta o `transcribe()` com features CORRETAS (fbank 80-bin do lhotse, o MESMO extrator do
//! treino) de um utterance real do FLEURS test, e compara com a transcrição de referência. Isso
//! prova que o decoder decodifica fala real corretamente — **separado** do gap de features do
//! `macaw-audio` (task #25). `#[ignore]`-like skip se os fixtures não estiverem presentes.

use std::path::PathBuf;

use macaw_asr::{AsrEngine, Vocab};

fn dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../training/results/onnx")
}

fn word_overlap(reference: &str, hyp: &str) -> f32 {
    let hyp_words: std::collections::HashSet<&str> = hyp.split_whitespace().collect();
    let ref_words: Vec<&str> = reference.split_whitespace().collect();
    if ref_words.is_empty() {
        return 0.0;
    }
    let hits = ref_words.iter().filter(|w| hyp_words.contains(*w)).count();
    hits as f32 / ref_words.len() as f32
}

// T-02 (/review): #[ignore] em vez de early-return silencioso — verde-fictício no CI
// mascarava a camada de integração vazia. Listado como IGNORED; rodar com `--ignored`.
#[test]
#[ignore = "requer fixtures de fala real (model.int8.onnx + fleurs_one.f32) não versionados"]
fn transcreve_fala_real_do_fleurs() {
    let model = dir().join("model.int8.onnx");
    let feats_f = dir().join("fleurs_one.f32");
    let text_f = dir().join("fleurs_one.txt");
    if !model.exists() || !feats_f.exists() {
        panic!("fixtures ausentes ({}) — rode o export/prep para gerá-los", feats_f.display());
    }

    // fbank real (T, 80) row-major, f32 little-endian, do lhotse.
    let bytes = std::fs::read(&feats_f).expect("lê fleurs_one.f32");
    let mel: Vec<f32> = bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect();
    let n_frames = mel.len() / 80;
    let reference = std::fs::read_to_string(&text_f).unwrap_or_default();
    let reference = reference.trim();

    let mut engine = AsrEngine::load(&model).expect("carrega int8");
    let vocab = Vocab::load(&dir().join("tokens.txt")).expect("tokens");

    let hyp = engine.transcribe(&mel, n_frames, &vocab).expect("transcribe");
    let overlap = word_overlap(reference, &hyp);
    eprintln!("REF: {reference}");
    eprintln!("HYP: {hyp}");
    eprintln!("word-overlap = {:.0}% (T={n_frames})", overlap * 100.0);

    assert!(!hyp.is_empty(), "transcrição de fala real não pode ser vazia");
    // WER medido ~30% em FLEURS → esperamos ~70% de palavras certas; piso conservador 0,45.
    assert!(
        overlap >= 0.45,
        "overlap {:.2} < 0.45 — features/decode desalinhados",
        overlap
    );
}
