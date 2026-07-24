//! Testes do adapter de inferência (T4.1).
//!
//! Este crate é **descartável por construção** — o ADR de M2 pode substituí-lo.
//! Os testes cobrem apenas o contrato de fronteira: carregamento e erro tipado.

use macaw_asr::{AsrError, AsrEngine, Vocab};
use std::path::PathBuf;

fn model_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../models/m0-borrowed")
}

#[test]
fn test_asr_returns_typed_error_when_model_file_missing() {
    let missing = PathBuf::from("/caminho/que/nao/existe/encoder-model.onnx");
    let result = AsrEngine::load(&missing);

    match result {
        Err(AsrError::ModelNotFound { ref path }) => {
            assert!(
                path.contains("nao/existe"),
                "a mensagem de erro deve citar o caminho informado, veio: {path}"
            );
        }
        Err(other) => panic!("esperava ModelNotFound, veio {other:?}"),
        Ok(_) => panic!("carregar modelo inexistente deveria falhar"),
    }
}

#[test]
fn test_vocab_loads_expected_token_count() {
    let path = model_dir().join("vocab.txt");
    if !path.exists() {
        eprintln!("modelo emprestado ausente em {} — teste ignorado", path.display());
        return;
    }

    let vocab = Vocab::load(&path).expect("vocab.txt deveria carregar");
    assert_eq!(
        vocab.len(),
        8193,
        "vocab do modelo emprestado tem 8193 tokens (medido em models/m0-borrowed/vocab.txt)"
    );
}

/// Prova que o runtime ONNX abre de fato o grafo — não apenas que o arquivo existe.
///
/// Evidência para o DoD de M0: o encanamento de inferência está funcional.
#[test]
fn test_encoder_graph_loads_and_exposes_io() {
    let path = model_dir().join("encoder-model.onnx");
    if !path.exists() {
        eprintln!("modelo emprestado ausente em {} — teste ignorado", path.display());
        return;
    }

    let engine = AsrEngine::load(&path).expect("encoder deveria carregar");
    let inputs = engine.input_names();
    let outputs = engine.output_names();

    assert!(!inputs.is_empty(), "grafo carregado deve expor ao menos uma entrada");
    assert!(!outputs.is_empty(), "grafo carregado deve expor ao menos uma saída");

    // Evidência impressa para o relatório de M0 (rotulada [MEDIDO — encanamento apenas]).
    eprintln!("encoder inputs : {inputs:?}");
    eprintln!("encoder outputs: {outputs:?}");
}

#[test]
fn test_vocab_returns_typed_error_when_file_missing() {
    let result = Vocab::load(&PathBuf::from("/nao/existe/vocab.txt"));
    assert!(
        matches!(result, Err(AsrError::VocabNotFound { .. })),
        "vocab ausente deve retornar VocabNotFound, veio {result:?}"
    );
}
