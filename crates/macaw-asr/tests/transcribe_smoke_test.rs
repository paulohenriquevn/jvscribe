//! Integração da Fase 2 (plano m6-runtime-v0): prova que `ctc_logits`/`transcribe` rodam no
//! NOSSO modelo real (`model.int8.onnx`) com o contrato icefall `x`/`x_lens`→`log_probs`.
//! `#[ignore]` se o modelo não estiver presente (não temos no CI ainda).

use std::path::PathBuf;

use macaw_asr::{AsrEngine, Vocab};

fn model_path() -> PathBuf {
    // CARGO_MANIFEST_DIR = crates/macaw-asr → raiz do workspace = ../../
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../training/results/onnx/model.int8.onnx")
}

fn tokens_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../training/results/onnx/tokens.txt")
}

#[test]
fn transcribe_roda_no_modelo_real() {
    if !model_path().exists() {
        eprintln!("SKIP: {} ausente (baixar do export)", model_path().display());
        return;
    }
    let mut engine = AsrEngine::load(&model_path()).expect("carrega o int8 onnx");
    let vocab = Vocab::load(&tokens_path()).expect("carrega tokens.txt");

    // log-mel sintético (T=60, 80 bins). Valores não importam para provar o ENCANAMENTO
    // (nomes de input corretos + extração de log_probs + decode). O texto sai qualquer, mas
    // o contrato x/x_lens→log_probs tem de rodar sem erro — é o que o deep-review flagou.
    let t = 60usize;
    let mel: Vec<f32> = (0..t * 80).map(|i| ((i % 17) as f32 - 8.0) * 0.1).collect();

    let (logits, t_out, vocab_size) = engine.ctc_logits(&mel, t).expect("ctc_logits roda");
    assert!(t_out > 0 && vocab_size > 0, "log_probs 3-D válido");
    assert_eq!(logits.len(), t_out * vocab_size, "dados batem com o shape");

    // transcribe encadeia logits→greedy→detok sem panicar e devolve String (Ok).
    let text = engine.transcribe(&mel, t, &vocab).expect("transcribe roda");
    eprintln!("transcribe(synthetic) = {text:?} (T={t_out}, vocab={vocab_size})");
}
