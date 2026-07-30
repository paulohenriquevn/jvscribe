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

// --- T1.1 (M9) — tokens reais e fingerprint de identidade ----------------------
//
// Racional medido em 2026-07-30: `training/results/onnx/tokens.txt` tem 502 linhas
// para um modelo de 500 classes, e `models/m5-final-medium-phoneme/tokens.txt` tem
// 503 — a diferença são os símbolos de desambiguação do lexicon FST do icefall
// (`#0`, `#1`, `#2`), que o modelo NUNCA emite. Contar linhas é errado por construção.
//
// E o mais importante: os dois artefatos têm 500 tokens reais cada, mas 492 dos 500
// ids mapeiam tokens DIFERENTES. Cardinalidade não distingue os dois — só identidade.

#[test]
fn real_len_exclui_simbolos_de_desambiguacao() {
    let p = tmp("disambig", "<blk> 0\na 1\nb 2\n#0 3\n#1 4\n");
    let v = Vocab::load(&p).unwrap();
    assert_eq!(v.len(), 5, "len() conta todas as linhas");
    assert_eq!(v.real_len(), 3, "real_len() exclui #0 e #1");
}

#[test]
fn fingerprint_e_estavel_para_mesmo_conteudo() {
    let a = Vocab::load(&tmp("fp_a", "<blk> 0\nx 1\ny 2\n")).unwrap();
    let b = Vocab::load(&tmp("fp_b", "<blk> 0\nx 1\ny 2\n")).unwrap();
    assert_eq!(a.fingerprint(), b.fingerprint());
}

#[test]
fn fingerprint_difere_quando_um_id_mapeia_token_diferente() {
    // Mesmo TAMANHO, conteúdo trocado — o caso real dos dois artefatos em disco.
    let a = Vocab::load(&tmp("fp_ord_a", "<blk> 0\n\u{2581}a 1\nr 2\n")).unwrap();
    let b = Vocab::load(&tmp("fp_ord_b", "<blk> 0\nr 1\n\u{2581}a 2\n")).unwrap();
    assert_eq!(a.real_len(), b.real_len(), "cardinalidade idêntica");
    assert_ne!(
        a.fingerprint(),
        b.fingerprint(),
        "identidade DEVE diferir mesmo com mesmo tamanho"
    );
}

#[test]
fn fingerprint_ignora_diferenca_apenas_em_desambiguacao() {
    // Dois lang-dirs equivalentes com nº diferente de #N produzem o MESMO vocabulário real.
    let a = Vocab::load(&tmp("fp_d2", "<blk> 0\na 1\n#0 2\n#1 3\n")).unwrap();
    let b = Vocab::load(&tmp("fp_d3", "<blk> 0\na 1\n#0 2\n#1 3\n#2 4\n")).unwrap();
    assert_eq!(a.fingerprint(), b.fingerprint());
}

// --- T1.1 — critério de aceite sobre os ARTEFATOS REAIS ------------------------
// `#[ignore]` porque depende de artefatos não versionados (models/ e training/results/
// são gitignored). Rode com: cargo test -p macaw-asr --test vocab_load_test -- --ignored
#[test]
#[ignore = "requer os artefatos reais em disco (não versionados)"]
fn artefatos_reais_tem_500_tokens_e_fingerprints_distintos() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let runtime = root.join("training/results/onnx/tokens.txt");
    let eval = root.join("models/m5-final-medium-phoneme/tokens.txt");
    if !runtime.exists() || !eval.exists() {
        eprintln!("SKIP: artefatos ausentes ({runtime:?} / {eval:?})");
        return;
    }
    let a = Vocab::load(&runtime).unwrap();
    let b = Vocab::load(&eval).unwrap();

    // Cardinalidade REAL é idêntica — é exatamente por isso que ela não serve como
    // critério de identidade.
    assert_eq!(a.real_len(), 500, "runtime deve ter 500 tokens emitíveis");
    assert_eq!(b.real_len(), 500, "eval deve ter 500 tokens emitíveis");
    assert_eq!(a.len(), 502, "runtime tem 2 símbolos de desambiguação");
    assert_eq!(b.len(), 503, "eval tem 3 símbolos de desambiguação");

    // Identidade difere — o que prova que o fingerprint detecta os 492 ids divergentes.
    assert_ne!(
        a.fingerprint(),
        b.fingerprint(),
        "vocabulários de mesmo tamanho e conteúdo divergente DEVEM ter fingerprints distintos"
    );
}
