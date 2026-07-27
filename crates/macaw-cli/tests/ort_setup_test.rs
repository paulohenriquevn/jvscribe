//! Testa o resolver da libonnxruntime vendorizada (task #26): acha a lib subindo a
//! árvore; retorna None quando ausente (→ o caller falha alto em vez de degradar).

use std::fs;
use macaw_cli::ort_setup::find_ort_dylib;

fn unique_tmp(tag: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("macaw_ort_{}_{}", std::process::id(), tag))
}

#[test]
fn find_ort_dylib_acha_a_lib_vendorizada_subindo_a_arvore() {
    // Monta root/vendor/onnxruntime-linux-x64-1.23.0/lib/libonnxruntime.so
    let root = unique_tmp("found");
    let libdir = root.join("vendor/onnxruntime-linux-x64-1.23.0/lib");
    fs::create_dir_all(&libdir).unwrap();
    fs::write(libdir.join("libonnxruntime.so"), b"stub").unwrap();
    // procura a partir de um subdiretório profundo (simula target/release/)
    let deep = root.join("target/release");
    fs::create_dir_all(&deep).unwrap();

    let found = find_ort_dylib(&deep).expect("deveria achar a lib subindo a árvore");
    assert!(found.ends_with("onnxruntime-linux-x64-1.23.0/lib/libonnxruntime.so"));
    assert!(found.is_file());
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn find_ort_dylib_retorna_none_quando_ausente() {
    let root = unique_tmp("absent");
    fs::create_dir_all(&root).unwrap();
    assert!(
        find_ort_dylib(&root).is_none(),
        "sem vendor/ deve retornar None (caller falha alto)"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn find_ort_dylib_ignora_vendor_sem_a_lib() {
    // vendor/ existe mas sem a subpasta onnxruntime-* / sem o .so
    let root = unique_tmp("empty_vendor");
    fs::create_dir_all(root.join("vendor/outra-coisa")).unwrap();
    assert!(find_ort_dylib(&root).is_none());
    let _ = fs::remove_dir_all(&root);
}
