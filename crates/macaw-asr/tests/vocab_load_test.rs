//! Casos negativos de validação de fronteira (fix do /review 2026-07-26: T-03, T-09).
//! testing.md § 4.1: o teste de caso negativo asserta o ERRO TIPADO específico, não só "falha".

use macaw_asr::{AsrEngine, AsrError, Vocab};

fn tmp(suffix: &str, body: &str) -> std::path::PathBuf {
    let p = std::env::temp_dir().join(format!("macaw_vocab_{}_{}.txt", std::process::id(), suffix));
    std::fs::write(&p, body).unwrap();
    p
}

// --- Vocab::load (T-03) --------------------------------------------------------

#[test]
fn vocab_load_path_inexistente_da_vocab_not_found() {
    let p = std::env::temp_dir().join("macaw_vocab_nao_existe_xyz.txt");
    let _ = std::fs::remove_file(&p);
    let err = Vocab::load(&p).unwrap_err();
    assert!(
        matches!(err, AsrError::VocabNotFound { .. }),
        "esperado VocabNotFound, veio {err:?}"
    );
}

#[test]
fn vocab_load_arquivo_so_whitespace_da_invalid_vocab() {
    let p = tmp("whitespace", "\n   \n\t\n");
    let err = Vocab::load(&p).unwrap_err();
    assert!(
        matches!(err, AsrError::InvalidVocab { .. }),
        "esperado InvalidVocab, veio {err:?}"
    );
    let _ = std::fs::remove_file(&p);
}

#[test]
fn vocab_load_token_com_multiplos_espacos_usa_rsplit_no_ultimo() {
    // "a b c 5" → o id é o último campo; o token é tudo antes (rsplit_once no espaço).
    let p = tmp("multi_space", "<blk> 0\na b c 5\n");
    let v = Vocab::load(&p).unwrap();
    assert_eq!(v.decode(1), Some("a b c"));
    let _ = std::fs::remove_file(&p);
}

#[test]
fn vocab_load_linha_sem_espaco_vira_token_inteiro() {
    // Sem espaço: rsplit_once → None → a linha inteira é o token.
    let p = tmp("no_space", "<blk> 0\ntokensozinho\n");
    let v = Vocab::load(&p).unwrap();
    assert_eq!(v.decode(1), Some("tokensozinho"));
    let _ = std::fs::remove_file(&p);
}

// --- AsrEngine::load (T-09) ----------------------------------------------------

#[test]
fn engine_load_path_inexistente_da_model_not_found() {
    let p = std::env::temp_dir().join("macaw_modelo_nao_existe_xyz.onnx");
    let _ = std::fs::remove_file(&p);
    let err = AsrEngine::load(&p).unwrap_err();
    assert!(
        matches!(err, AsrError::ModelNotFound { .. }),
        "esperado ModelNotFound, veio {err:?}"
    );
}
