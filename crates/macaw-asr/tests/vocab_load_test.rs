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

// --- T1.2 (M9) — recusa do par (modelo, vocabulário) incoerente ----------------

#[test]
#[ignore = "requer o model.int8.onnx real (não versionado)"]
fn transcribe_falha_quando_vocab_nao_bate_com_saida_do_modelo() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let model = root.join("training/results/onnx/model.int8.onnx");
    if !model.exists() {
        eprintln!("SKIP: modelo ausente em {model:?}");
        return;
    }
    let mut engine = AsrEngine::load(&model).expect("modelo real deve carregar");

    // Vocabulário com 499 tokens reais contra um modelo de 500 classes.
    let mut body = String::new();
    for i in 0..499 {
        body.push_str(&format!("t{i} {i}\n"));
    }
    let vocab = Vocab::load(&tmp("mismatch499", &body)).unwrap();
    assert_eq!(vocab.real_len(), 499);

    let mel = vec![0.0f32; 80 * 40];
    let err = engine.transcribe(&mel, 40, &vocab).unwrap_err();
    assert!(
        matches!(err, AsrError::VocabModelMismatch { model_dim: 500, vocab_real: 499, .. }),
        "esperado VocabModelMismatch{{500,499}}, veio {err:?}"
    );
    let msg = format!("{err}");
    assert!(msg.contains("model_dim=500"), "mensagem deve citar model_dim=500: {msg}");
    assert!(msg.contains("vocab_real=499"), "mensagem deve citar vocab_real=499: {msg}");
}

#[test]
#[ignore = "requer o artefato canônico real (não versionado)"]
fn transcribe_aceita_o_artefato_canonico_real() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = root.join("training/results/onnx");
    if !dir.join("model.int8.onnx").exists() {
        eprintln!("SKIP: artefato ausente");
        return;
    }
    let mut engine = AsrEngine::load(&dir.join("model.int8.onnx")).unwrap();
    let vocab = Vocab::load(&dir.join("tokens.txt")).unwrap();
    // 502 linhas, 500 reais — a regra D2 NÃO pode gerar falso positivo aqui.
    let mel = vec![0.0f32; 80 * 40];
    let r = engine.transcribe(&mel, 40, &vocab);
    assert!(r.is_ok(), "artefato canônico deve ser aceito, veio {r:?}");
}

// --- T1.2b (M9) — o caso CENTRAL: mesmo tamanho, vocabulário trocado -------------
//
// `[MEDIDO]` os dois artefatos em disco têm 500 tokens emitíveis CADA e 492 dos 500 ids
// mapeiam tokens diferentes. A checagem de cardinalidade passa nos dois — só a identidade
// distingue. Sem esta validação, M9 detectaria o erro fácil e deixaria passar o difícil.

#[test]
fn valida_fingerprint_contra_model_card_quando_presente() {
    let dir = std::env::temp_dir().join(format!("macaw_card_{}", std::process::id()));
    let _ = std::fs::create_dir_all(&dir);

    // Vocabulário A e um card que declara o fingerprint de OUTRO vocabulário do mesmo tamanho.
    let vocab_path = dir.join("tokens.txt");
    std::fs::write(&vocab_path, "<blk> 0\n\u{2581}a 1\nr 2\n").unwrap();
    let outro = Vocab::load(&tmp("card_outro", "<blk> 0\nr 1\n\u{2581}a 2\n")).unwrap();
    std::fs::write(
        dir.join("model_card.json"),
        format!("{{\"vocab_fingerprint\": \"{}\"}}", outro.fingerprint()),
    )
    .unwrap();

    let vocab = Vocab::load(&vocab_path).unwrap();
    let err = macaw_asr::validate_against_model_card(&dir, &vocab).unwrap_err();
    assert!(
        matches!(err, AsrError::VocabFingerprintMismatch { .. }),
        "esperado VocabFingerprintMismatch, veio {err:?}"
    );
}

#[test]
fn card_ausente_degrada_para_ok_sem_falhar() {
    let dir = std::env::temp_dir().join(format!("macaw_nocard_{}", std::process::id()));
    let _ = std::fs::create_dir_all(&dir);
    let vocab = Vocab::load(&tmp("nocard", "<blk> 0\na 1\n")).unwrap();
    assert!(
        macaw_asr::validate_against_model_card(&dir, &vocab).is_ok(),
        "sem card, a validação de identidade degrada — não falha"
    );
}

#[test]
#[ignore = "requer o artefato canônico com model_card.json gerado"]
fn artefato_canonico_passa_na_validacao_de_identidade() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = root.join("training/results/onnx");
    if !dir.join("model_card.json").exists() {
        eprintln!("SKIP: model_card.json ausente");
        return;
    }
    let vocab = Vocab::load(&dir.join("tokens.txt")).unwrap();
    let r = macaw_asr::validate_against_model_card(&dir, &vocab);
    assert!(r.is_ok(), "o artefato canônico deve casar com seu próprio card: {r:?}");
}
