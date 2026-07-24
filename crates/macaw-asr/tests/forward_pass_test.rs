//! Teste de encanamento acústico ponta a ponta (T4.1 — prova do walking skeleton).
//!
//! Prova que áudio real → features → encoder ONNX (600M, pesos reais) → tensor de
//! saída válido funciona de ponta a ponta. É a evidência central de M0 sobre o
//! estágio de modelo.
//!
//! O decode completo (encoder → decoder_joint → texto) é específico da arquitetura
//! do modelo emprestado e está BLOQUEADO POR M2
//! (`.claude/rules/asr-evidence-discipline.md` § 0) — ver
//! `knowledge-base/discoveries/m0-borrowed-model-dod-analysis.md`.

use std::path::PathBuf;
use std::time::Instant;

use macaw_asr::AsrEngine;
use macaw_audio::features::{FeatureCache, StreamState};
use macaw_audio::MEL_BINS;

fn model_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../models/m0-borrowed")
}

fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/tone_440hz_16k.wav")
}

/// Extrai log-mel da fixture inteira, achatado em ordem row-major `[128 * T]`.
fn fixture_features() -> (Vec<f32>, usize) {
    let reader = hound::WavReader::open(fixture_path()).expect("fixture deve abrir");
    let samples: Vec<i16> = reader
        .into_samples::<i16>()
        .collect::<Result<_, _>>()
        .expect("amostras da fixture");

    let cache = FeatureCache::new();
    let mut state = StreamState::new(&cache);
    let n_fft = 512; // = VAD_WINDOW, o hop da fixture

    // Colhe um frame por janela não sobreposta; guarda [frame][mel].
    let mut frames: Vec<Vec<f32>> = Vec::new();
    for chunk in samples.chunks_exact(n_fft) {
        let mel = state.extract(&cache, chunk).expect("extract");
        frames.push(mel.to_vec());
    }
    let n_frames = frames.len();
    assert!(n_frames > 0, "fixture deveria render ao menos um frame");

    // Rearranja [frame][mel] -> [mel * n_frames] (layout [1, 128, T] do encoder).
    let mut flat = vec![0.0f32; MEL_BINS * n_frames];
    for (t, frame) in frames.iter().enumerate() {
        for (m, &v) in frame.iter().enumerate() {
            flat[m * n_frames + t] = v;
        }
    }
    (flat, n_frames)
}

#[test]
fn test_end_to_end_encoder_forward_pass_on_real_features() {
    let encoder = model_dir().join("encoder-model.onnx");
    if !encoder.exists() || !model_dir().join("encoder-model.onnx.data").exists() {
        eprintln!(
            "SKIP: encoder ou pesos ausentes em {} — rode scripts/setup_model.sh",
            model_dir().display()
        );
        return;
    }

    let mut engine = AsrEngine::load(&encoder).expect("encoder deve carregar");
    let (mel, n_frames) = fixture_features();

    // O forward pass real: features → encoder → tensor de saída.
    let t = Instant::now();
    let out_shape = engine
        .encode(&mel, MEL_BINS, n_frames)
        .expect("forward pass do encoder deve rodar");
    let elapsed = t.elapsed();

    // O encoder produz [dim0, 1024, dim2]: batch 1, hidden 1024, tempo subamostrado.
    assert_eq!(out_shape.len(), 3, "saída do encoder deve ser 3D, veio {out_shape:?}");
    assert_eq!(out_shape[0], 1, "batch deve ser 1");
    assert_eq!(out_shape[1], 1024, "dim hidden do encoder deve ser 1024");
    assert!(out_shape[2] > 0, "dimensão temporal deve ser positiva");

    // Evidência `[MEDIDO — encanamento apenas]`: tempo do forward pass do encoder
    // de 600M nesta CPU. Não é RTFx de produto (modelo emprestado, offline), mas
    // mostra a ordem de grandeza que motiva o modelo próprio de M5/M6.
    let audio_secs = n_frames as f64 * 512.0 / 16_000.0;
    eprintln!(
        "[MEDIDO — encanamento apenas] encoder 600M: {n_frames} frames ({audio_secs:.2}s de áudio) \
         em {:.0}ms → shape {out_shape:?}",
        elapsed.as_millis()
    );
}
