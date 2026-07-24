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

    // Aquecimento: a primeira passagem inclui paginação do mmap de 2,3 GB e
    // alocação de arena do ORT — descartada para não poluir a medição (a mesma
    // disciplina que vad_cost_test aplica). Review HIGH-2.
    let out_shape = engine
        .encode(&mel, MEL_BINS, n_frames)
        .expect("forward pass do encoder deve rodar");

    // O encoder produz [dim0, 1024, dim2]: batch 1, hidden 1024, tempo subamostrado.
    assert_eq!(out_shape.len(), 3, "saída do encoder deve ser 3D, veio {out_shape:?}");
    assert_eq!(out_shape[0], 1, "batch deve ser 1");
    assert_eq!(out_shape[1], 1024, "dim hidden do encoder deve ser 1024");
    assert!(out_shape[2] > 0, "dimensão temporal deve ser positiva");

    // Medição aquecida: 10 repetições, média ± desvio (não single-shot).
    const REPS: usize = 10;
    let mut times_ms: Vec<f64> = Vec::with_capacity(REPS);
    for _ in 0..REPS {
        let t = Instant::now();
        let _ = engine
            .encode(&mel, MEL_BINS, n_frames)
            .expect("forward pass deve rodar");
        times_ms.push(t.elapsed().as_secs_f64() * 1000.0);
    }
    let mean = times_ms.iter().sum::<f64>() / REPS as f64;
    let std = (times_ms.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / REPS as f64).sqrt();
    let audio_secs = n_frames as f64 * 512.0 / 16_000.0;
    let rtf = (mean / 1000.0) / audio_secs;

    // Evidência `[MEDIDO — só encoder, aquecido, grafo não-otimizado — encanamento
    // apenas]`. NÃO é RTFx de produto: mede só o encoder (o decode, a parte cara de
    // um transducer, está bloqueado por M2), com otimização de grafo desabilitada.
    // Não sustenta a tese do projeto — a viabilidade real-time do modelo completo é
    // [DESCONHECIDO]. Ver m0-borrowed-model-dod-analysis.md.
    eprintln!(
        "[MEDIDO — só encoder, aquecido, grafo não-otimizado — encanamento apenas] \
         encoder 600M: {mean:.0} ± {std:.0} ms (n={REPS}) para {audio_secs:.2}s de áudio \
         (RTF {rtf:.3}) → shape {out_shape:?}"
    );
}
