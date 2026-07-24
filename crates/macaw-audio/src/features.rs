//! Extração de log-mel de 128 bins **sem alocação no caminho quente** (T3.1,
//! ADR D3).
//!
//! O blueprint mediu que `parakeet-rs/src/audio.rs` aloca 5× por chunk
//! (`padded`, `spectrogram`, `input`, `output`, `scratch`, e recomputa a
//! janela de Hann a cada chamada — ver `stft_with_plan`, linhas 95-106 e 99).
//! Este módulo reaproveita o *padrão* de cache (`FeatureCache` construído uma
//! vez, compartilhado via `Arc`) e as *fórmulas* de mel scale / Hann window
//! documentadas ali — nunca o laço que realoca. [`StreamState`] pré-aloca
//! todos os buffers de trabalho na construção; [`StreamState::extract`] nunca
//! aloca depois disso.

use crate::{MEL_BINS, SAMPLE_RATE, VAD_WINDOW};
use realfft::num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};
use std::sync::Arc;

/// Guarda log-zero aditiva para o log do espectro mel (mesma convenção do
/// NeMo — `log_zero_guard_type="add"`, `value=2^-24` — documentada em
/// `knowledge-base/references/parakeet-rs/src/audio.rs:239-241`). Evita
/// `ln(0.0) == -inf` sem introduzir um ramo condicional no caminho quente.
const LOG_ZERO_GUARD: f32 = 1.0 / 16_777_216.0; // 2^-24

/// Erros tipados da extração de features. Nunca panic, nunca silêncio —
/// `.claude/rules/error-handling.md` § 2.
#[derive(Debug)]
pub enum FeatureError {
    /// O chunk recebido não tem o tamanho de FFT esperado pelo cache.
    InvalidChunkSize { expected: usize, got: usize },
    /// A FFT real subjacente (`realfft`) rejeitou os buffers fornecidos.
    FftFailed(String),
}

impl std::fmt::Display for FeatureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            FeatureError::InvalidChunkSize { expected, got } => write!(
                f,
                "chunk deve ter {expected} amostras, recebeu {got}"
            ),
            FeatureError::FftFailed(msg) => write!(f, "FFT falhou: {msg}"),
        }
    }
}

impl std::error::Error for FeatureError {}

/// Cache de FFT + filterbank mel — construído **uma única vez** e
/// compartilhado (via `Arc`, aplicado pelo chamador) entre todos os
/// [`StreamState`]. Nunca é o caminho quente: sua construção pode alocar
/// livremente.
///
/// `Send + Sync` por construção: todos os campos são `Send + Sync` (o
/// próprio traço `realfft::RealToComplex` exige `Sync + Send` de quem o
/// implementa), então nenhum `unsafe impl` é necessário. Ver o teste de
/// compilação no fim deste módulo.
pub struct FeatureCache {
    /// Matriz `n_mels x freq_bins`, linha-major.
    mel_basis: Vec<f32>,
    /// Frequência central (Hz) de cada bin mel, na mesma ordem de `mel_basis`.
    mel_centers: Vec<f32>,
    fft_plan: Arc<dyn RealToComplex<f32>>,
    n_fft: usize,
    n_mels: usize,
    freq_bins: usize,
}

impl FeatureCache {
    /// Constrói o cache para uma janela de [`VAD_WINDOW`] amostras e
    /// [`MEL_BINS`] bins mel a [`SAMPLE_RATE`]. M0 extrai um frame de
    /// log-mel por janela de VAD, sem overlap — suficiente para provar o
    /// encanamento (ADR D3). A estratégia de frame de produção (overlap,
    /// hop diferente da janela do VAD) é decisão de M2/M4, não deste plano.
    pub fn new() -> Self {
        let n_fft = VAD_WINDOW;
        let n_mels = MEL_BINS;
        let freq_bins = n_fft / 2 + 1;

        let (mel_basis, mel_centers) = build_mel_filterbank(n_fft, n_mels, SAMPLE_RATE);

        let mut planner = RealFftPlanner::<f32>::new();
        let fft_plan = planner.plan_fft_forward(n_fft);

        Self {
            mel_basis,
            mel_centers,
            fft_plan,
            n_fft,
            n_mels,
            freq_bins,
        }
    }

    /// Índice do bin mel cujo centro (Hz) está mais próximo de `hz`. Usado
    /// por testes para verificar que a STFT concentra energia no bin
    /// esperado, sem hard-codar o índice (que depende da fórmula de mel
    /// scale e mudaria silenciosamente se ela mudasse).
    pub fn nearest_mel_bin(&self, hz: f32) -> usize {
        let mut best_idx = 0usize;
        let mut best_diff = f32::MAX;
        for (i, &center) in self.mel_centers.iter().enumerate() {
            let diff = (center - hz).abs();
            if diff < best_diff {
                best_diff = diff;
                best_idx = i;
            }
        }
        best_idx
    }
}

impl Default for FeatureCache {
    fn default() -> Self {
        Self::new()
    }
}

/// Estado por stream — todos os buffers pré-alocados na construção.
/// [`StreamState::extract`] nunca aloca (T3.1, ADR D3): reescrever
/// `parakeet-rs/src/audio.rs` verbatim, que aloca 5× por chunk, repetiria
/// exatamente o defeito que este plano existe para medir.
pub struct StreamState {
    hann: Vec<f32>,
    padded: Vec<f32>,
    input: Vec<f32>,
    output: Vec<Complex<f32>>,
    scratch: Vec<Complex<f32>>,
    mel: Vec<f32>,
}

impl StreamState {
    /// Pré-aloca todos os buffers de trabalho a partir das dimensões do
    /// `cache`. Chamado uma vez por stream.
    pub fn new(cache: &FeatureCache) -> Self {
        Self {
            hann: hann_window(cache.n_fft),
            padded: vec![0.0; cache.n_fft],
            input: vec![0.0; cache.n_fft],
            output: cache.fft_plan.make_output_vec(),
            scratch: cache.fft_plan.make_scratch_vec(),
            mel: vec![0.0; cache.n_mels],
        }
    }

    /// Extrai um frame de log-mel de `chunk`. Não aloca após o warmup:
    /// `padded`/`input` recebem o sinal janelado, `output`/`scratch` são
    /// reaproveitados a cada chamada de FFT, e `mel` é sobrescrito in-place
    /// e devolvido por referência (`[MEDIDO]` — ver
    /// `tests/features_zero_alloc_test.rs`).
    pub fn extract(
        &mut self,
        cache: &FeatureCache,
        chunk: &[i16],
    ) -> Result<&[f32], FeatureError> {
        if chunk.len() != cache.n_fft {
            return Err(FeatureError::InvalidChunkSize {
                expected: cache.n_fft,
                got: chunk.len(),
            });
        }

        for ((dst, &sample), &w) in self.padded.iter_mut().zip(chunk).zip(self.hann.iter()) {
            *dst = (sample as f32 / i16::MAX as f32) * w;
        }
        self.input.copy_from_slice(&self.padded);

        cache
            .fft_plan
            .process_with_scratch(&mut self.input, &mut self.output, &mut self.scratch)
            .map_err(|e| FeatureError::FftFailed(e.to_string()))?;

        for m in 0..cache.n_mels {
            let row = &cache.mel_basis[m * cache.freq_bins..(m + 1) * cache.freq_bins];
            let energy: f32 = row
                .iter()
                .zip(self.output.iter())
                .map(|(&w, c)| w * c.norm_sqr())
                .sum();
            self.mel[m] = (energy + LOG_ZERO_GUARD).ln();
        }

        Ok(&self.mel)
    }
}

/// Janela de Hann periódica-simétrica padrão — mesma fórmula do peer
/// (`parakeet-rs/src/audio.rs:64-68`). Reaproveitamos a fórmula, não a
/// realocação por chamada: só roda na construção de [`StreamState`].
fn hann_window(len: usize) -> Vec<f32> {
    (0..len)
        .map(|i| {
            0.5 - 0.5 * ((2.0 * std::f32::consts::PI * i as f32) / (len as f32 - 1.0)).cos()
        })
        .collect()
}

// Escala mel de Slaney (idêntica à do librosa/NeMo) — mesma usada pelo peer
// citado em Prior Art (`parakeet-rs/src/audio.rs:127-147`). Reaproveitamos a
// fórmula publicada, não o laço de `stft_with_plan` que aloca por chunk.
const MEL_F_SP: f64 = 200.0 / 3.0;
const MEL_MIN_LOG_HZ: f64 = 1000.0;
const MEL_MIN_LOG_MEL: f64 = MEL_MIN_LOG_HZ / MEL_F_SP;
const MEL_LOG_STEP: f64 = 0.06875177742094912;

fn hz_to_mel(hz: f64) -> f64 {
    if hz < MEL_MIN_LOG_HZ {
        hz / MEL_F_SP
    } else {
        MEL_MIN_LOG_MEL + (hz / MEL_MIN_LOG_HZ).ln() / MEL_LOG_STEP
    }
}

fn mel_to_hz(mel: f64) -> f64 {
    if mel < MEL_MIN_LOG_MEL {
        mel * MEL_F_SP
    } else {
        MEL_MIN_LOG_HZ * ((mel - MEL_MIN_LOG_MEL) * MEL_LOG_STEP).exp()
    }
}

/// Constrói o filterbank mel triangular (Slaney-normalizado) e o vetor de
/// frequências centrais correspondente. Chamada apenas na construção de
/// [`FeatureCache`] — nunca no caminho quente, então alocar livremente aqui
/// é aceitável.
fn build_mel_filterbank(n_fft: usize, n_mels: usize, sample_rate: u32) -> (Vec<f32>, Vec<f32>) {
    let freq_bins = n_fft / 2 + 1;
    let fmax = sample_rate as f64 / 2.0;
    let mel_min = hz_to_mel(0.0);
    let mel_max = hz_to_mel(fmax);

    let mel_points: Vec<f64> = (0..=n_mels + 1)
        .map(|i| mel_to_hz(mel_min + (mel_max - mel_min) * i as f64 / (n_mels + 1) as f64))
        .collect();

    let fft_freqs: Vec<f64> = (0..freq_bins)
        .map(|k| k as f64 * sample_rate as f64 / n_fft as f64)
        .collect();

    let fdiff: Vec<f64> = mel_points.windows(2).map(|w| w[1] - w[0]).collect();

    let mut filterbank = vec![0.0f32; n_mels * freq_bins];
    for m in 0..n_mels {
        let enorm = 2.0 / (mel_points[m + 2] - mel_points[m]);
        for (k, &freq) in fft_freqs.iter().enumerate() {
            let lower = (freq - mel_points[m]) / fdiff[m];
            let upper = (mel_points[m + 2] - freq) / fdiff[m + 1];
            let weight = 0.0f64.max(lower.min(upper));
            filterbank[m * freq_bins + k] = (weight * enorm) as f32;
        }
    }

    // Centro de cada triângulo mel — usado por `nearest_mel_bin`.
    let centers: Vec<f32> = mel_points[1..=n_mels].iter().map(|&hz| hz as f32).collect();

    (filterbank, centers)
}

#[allow(dead_code)]
fn assert_feature_cache_is_send_sync() {
    fn assert_send<T: Send>() {}
    fn assert_sync<T: Sync>() {}
    assert_send::<FeatureCache>();
    assert_sync::<FeatureCache>();
}
