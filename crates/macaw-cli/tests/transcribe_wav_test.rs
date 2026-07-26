//! Integração do subcomando `transcribe <wav>` (pilar b do wiring triad).
//! Casos testáveis sem o modelo (leitura/validação de WAV) rodam sempre; a prova
//! e2e completa (com `model.int8.onnx`) é `#[ignore]` — mesma convenção dos demais
//! testes dependentes de fixture não versionada.

use std::path::PathBuf;

use macaw_cli::transcribe::{read_wav_16k_mono, transcribe_wav, TranscribeError};

fn tone_fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/tone_440hz_16k.wav")
}

fn onnx_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../training/results/onnx")
}

#[test]
fn read_wav_16k_mono_le_a_fixture_de_tom() {
    let samples = read_wav_16k_mono(&tone_fixture()).expect("fixture 16k mono deve ler");
    assert!(!samples.is_empty(), "a fixture de tom não pode vir vazia");
}

#[test]
fn read_wav_path_inexistente_da_wav_open() {
    let p = std::env::temp_dir().join("macaw_cli_wav_inexistente_xyz.wav");
    let _ = std::fs::remove_file(&p);
    let err = read_wav_16k_mono(&p).unwrap_err();
    assert!(
        matches!(err, TranscribeError::WavOpen { .. }),
        "esperado WavOpen, veio {err:?}"
    );
}

#[test]
#[ignore = "requer training/results/onnx/model.int8.onnx + tokens.txt (não versionados)"]
fn transcribe_wav_produz_texto_e_metrica() {
    let model_dir = onnx_dir();
    if !model_dir.join("model.int8.onnx").exists() {
        panic!("modelo ausente em {} — rode o export", model_dir.display());
    }
    // Usa o wav real de fala se presente; senão o tom (prova o caminho, texto qualquer).
    let wav = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../macaw-audio/tests/fixtures/fleurs_one_16k.wav");
    let wav = if wav.exists() { wav } else { tone_fixture() };

    let (text, m) = transcribe_wav(&model_dir, &wav).expect("transcribe_wav não deve falhar");
    eprintln!(
        "[MEDIDO] transcribe(cli): '{text}' | T={} audio={:.2}s decode={:.0}ms RTFx={:.1} tokens={}",
        m.n_frames, m.audio_secs, m.decode_ms, m.rtfx, m.tokens
    );
    assert!(m.n_frames > 0, "deveria produzir ao menos 1 frame");
    assert!(m.rtfx > 0.0, "RTFx deve ser positivo");
}
