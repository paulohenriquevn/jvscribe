//! Extração de fbank kaldi/HTK de 80 bins — o formato consumido pelo modelo de
//! produção (`training/results/onnx/model.int8.onnx`, Zipformer-CTC exportado do
//! icefall), treinado com `lhotse.Fbank(FbankConfig(num_mel_bins=80))`
//! (`training/prep_mls.py:99`, `training/prep_icefall.py:112`).
//!
//! **Não é o mesmo pipeline que [`crate::features`]** (128 bins, mel Slaney, um
//! frame por janela de VAD, sem overlap — convenção NeMo). Este módulo implementa
//! a convenção kaldi/HTK: mel Slaney≠HTK, janela povey, frames de 25 ms com hop de
//! 10 ms (overlap), pré-ênfase e remoção de DC no domínio do tempo, `snip_edges`
//! falso (reflete a borda em vez de descartar). As duas convenções coexistem porque
//! servem modelos diferentes — `features.rs` prova o encanamento do M0 (modelo
//! emprestado, 128 bins); este módulo alimenta o decoder de produção. Nenhuma
//! mudança aqui afeta `features.rs` (ADR: adicionar, não migrar — ver
//! `knowledge-base/plans/m6-runtime-v0-plan.md` ADR-1, mesmo racional).
//!
//! Algoritmo verificado bin-a-bin contra o golden do lhotse
//! (`crates/macaw-audio/tests/kaldi_fbank_golden_test.rs`,
//! `training/scripts/make_kaldi_fbank_golden.py`) — a fonte de verdade da fórmula é
//! `lhotse/features/kaldi/layers.py` (`Wav2Win`, `Wav2LogFilterBank`,
//! `get_mel_banks`), lida em disco nesta máquina (lhotse reimplementa Kaldi em
//! PyTorch puro, "very close to Kaldi's" — docstring do módulo, linha 9-12; não usa
//! `torchaudio.compliance.kaldi`, que não está instalado neste ambiente).
//!
//! Ao contrário de [`crate::features::StreamState`] (zero-alocação, um frame por
//! chamada, pensado para o laço de captura em tempo real), este extrator processa
//! uma UTTERANCE inteira de uma vez: `snip_edges=False` reflete a borda direita do
//! sinal, o que exige conhecer o fim do áudio — streaming verdadeiro deste fbank
//! está fora do v0 (`m6-runtime-v0-plan.md`, Coverage Matrix: "hotwords/streaming
//! FORA do v0"). Isso é aceitável: o consumidor é `AsrEngine::transcribe`, que já
//! recebe a utterance completa.

use crate::SAMPLE_RATE;
use realfft::num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};
use std::sync::Arc;

/// Bins mel do fbank de produção — casa com o `num_mel_bins=80` do treino.
pub const KALDI_MEL_BINS: usize = 80;

/// Duração de frame em segundos (25 ms) — `FbankConfig.frame_length` default do lhotse.
const FRAME_LENGTH_SECS: f64 = 0.025;
/// Hop entre frames em segundos (10 ms) — `FbankConfig.frame_shift` default do lhotse.
const FRAME_SHIFT_SECS: f64 = 0.01;
/// Frequência mel mínima (Hz) — `FbankConfig.low_freq` default do lhotse.
const LOW_FREQ_HZ: f64 = 20.0;
/// Offset de frequência mel máxima (Hz, negativo = subtraído de Nyquist) —
/// `FbankConfig.high_freq` default do lhotse (`-400.0` → `8000 - 400 = 7600 Hz`).
const HIGH_FREQ_OFFSET_HZ: f64 = -400.0;
/// Coeficiente de pré-ênfase — `FbankConfig.preemph_coeff` default do lhotse.
const PREEMPH_COEFF: f32 = 0.97;
/// Expoente da janela povey (`hann_window ** POVEY_EXPONENT`) — convenção kaldi.
const POVEY_EXPONENT: f32 = 0.85;
/// Piso do log-mel — `torch.finfo(torch.float32).eps`, o mesmo piso do lhotse
/// (`Wav2LogFilterBank._eps`, `layers.py:536-538`). Natural log, não log10.
const LOG_FLOOR: f32 = f32::EPSILON;
/// Divisor de normalização de amostras PCM16 → f32. `soundfile`/`libsndfile` (o
/// backend que o `lhotse`/`training/prep_*.py` usam para ler wav) normalizam por
/// `2^15`, não por `i16::MAX` (`2^15 - 1`) — `[MEDIDO]`: amplitude 0.5 sintetizada
/// pelo `sox` lê de volta como `0.5000305` via `soundfile`, que só bate com
/// `16385 / 32768`. Usar `i16::MAX` aqui introduziria um viés sistemático de escala
/// entre o sinal que o macaw-audio produz e o sinal que o modelo viu no treino.
const PCM16_NORM: f32 = 32_768.0;

/// Erros tipados da extração de fbank kaldi. Nunca panic, nunca silêncio —
/// `.claude/rules/error-handling.md` § 2.
#[derive(Debug)]
pub enum KaldiFbankError {
    /// A utterance tem amostras demais faltando para refletir a borda esquerda
    /// (`snip_edges=False` exige pelo menos `(frame_length - frame_shift) / 2`
    /// amostras de contexto). Utterances tão curtas não produzem frames válidos.
    TooFewSamples { minimum: usize, got: usize },
    /// A FFT real subjacente (`realfft`) rejeitou os buffers fornecidos.
    FftFailed(String),
}

impl std::fmt::Display for KaldiFbankError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            KaldiFbankError::TooFewSamples { minimum, got } => write!(
                f,
                "utterance curta demais para refletir a borda: precisa de pelo menos \
                 {minimum} amostras de contexto, recebeu {got} amostras no total"
            ),
            KaldiFbankError::FftFailed(msg) => write!(f, "FFT falhou: {msg}"),
        }
    }
}

impl std::error::Error for KaldiFbankError {}

/// Cache de FFT + filterbank mel kaldi/HTK — construído **uma única vez** e
/// reaproveitado entre chamadas de [`extract_utterance`]. Nunca é o caminho quente
/// por-frame: sua construção pode alocar livremente (mesmo padrão de
/// [`crate::features::FeatureCache`]).
pub struct KaldiFbankCache {
    /// Matriz `n_mels x n_fft_bins` (row-major); `n_fft_bins = fft_len / 2` — o bin
    /// de Nyquist (índice `fft_len/2`) nunca recebe peso no filterbank kaldi
    /// compatível com torchaudio (`get_mel_banks`, ver docstring do módulo), então
    /// não é armazenado.
    mel_basis: Vec<f32>,
    povey_window: Vec<f32>,
    fft_plan: Arc<dyn RealToComplex<f32>>,
    frame_len: usize,
    frame_shift: usize,
    fft_len: usize,
    n_fft_bins: usize,
    n_mels: usize,
}

impl KaldiFbankCache {
    /// Constrói o cache para a configuração de produção fixa: 80 bins mel,
    /// 16 kHz, frames de 25 ms / hop de 10 ms, janela povey, mel HTK
    /// (`low_freq=20 Hz`, `high_freq=7600 Hz`). Casa bit-a-bit com
    /// `Fbank(FbankConfig(num_mel_bins=80))` do lhotse (defaults do lhotse para
    /// todo o resto).
    #[must_use]
    pub fn new() -> Self {
        let frame_len = (FRAME_LENGTH_SECS * SAMPLE_RATE as f64).floor() as usize;
        let frame_shift = (FRAME_SHIFT_SECS * SAMPLE_RATE as f64).floor() as usize;
        let fft_len = frame_len.next_power_of_two();
        let n_fft_bins = fft_len / 2;
        let n_mels = KALDI_MEL_BINS;

        let nyquist = SAMPLE_RATE as f64 / 2.0;
        let high_freq = nyquist + HIGH_FREQ_OFFSET_HZ;
        let mel_basis =
            build_kaldi_mel_filterbank(fft_len, n_mels, SAMPLE_RATE, LOW_FREQ_HZ, high_freq);

        let povey_window = povey_window(frame_len);

        let mut planner = RealFftPlanner::<f32>::new();
        let fft_plan = planner.plan_fft_forward(fft_len);

        Self {
            mel_basis,
            povey_window,
            fft_plan,
            frame_len,
            frame_shift,
            fft_len,
            n_fft_bins,
            n_mels,
        }
    }
}

impl Default for KaldiFbankCache {
    fn default() -> Self {
        Self::new()
    }
}

/// Buffers de trabalho reaproveitados entre frames de UMA chamada de
/// [`extract_utterance`]. Ao contrário de [`crate::features::StreamState`], esta
/// struct não precisa sobreviver entre utterances diferentes — construí-la é
/// barato e seu papel é apenas evitar realocar por frame dentro do laço.
struct KaldiFbankScratch {
    frame: Vec<f32>,
    fft_input: Vec<f32>,
    fft_output: Vec<Complex<f32>>,
    fft_scratch: Vec<Complex<f32>>,
    power: Vec<f32>,
}

impl KaldiFbankScratch {
    fn new(cache: &KaldiFbankCache) -> Self {
        Self {
            frame: vec![0.0; cache.frame_len],
            fft_input: vec![0.0; cache.fft_len],
            fft_output: cache.fft_plan.make_output_vec(),
            fft_scratch: cache.fft_plan.make_scratch_vec(),
            power: vec![0.0; cache.n_fft_bins],
        }
    }
}

/// Extrai o fbank kaldi/HTK de 80 bins de uma utterance inteira.
///
/// `samples` são amostras PCM16 mono a [`SAMPLE_RATE`] (16 kHz) — o mesmo tipo de
/// entrada usado por [`crate::features::StreamState::extract`] e pelo `hound`
/// (convenção já estabelecida pelos testes do crate). Retorna o log-mel achatado em
/// ordem row-major `[n_frames * 80]` e o número de frames.
///
/// `samples` vazio retorna `Ok((vec![], 0))` — zero frames é uma saída válida para
/// zero amostras, não um erro (mesma convenção de "áudio vazio → zero segmentos" já
/// adotada pelo VAD do crate).
///
/// # Erros
///
/// [`KaldiFbankError::TooFewSamples`] quando a utterance é curta demais para
/// refletir a borda esquerda (`snip_edges=False` exige contexto — ver
/// `lhotse/features/kaldi/layers.py:727-772`, `_get_strided_batch`).
/// [`KaldiFbankError::FftFailed`] se o `realfft` subjacente rejeitar os buffers.
pub fn extract_utterance(
    cache: &KaldiFbankCache,
    samples: &[i16],
) -> Result<(Vec<f32>, usize), KaldiFbankError> {
    if samples.is_empty() {
        return Ok((Vec::new(), 0));
    }

    let num_samples = samples.len();
    let num_frames = (num_samples + cache.frame_shift / 2) / cache.frame_shift;
    if num_frames == 0 {
        return Ok((Vec::new(), 0));
    }

    let padded = reflect_pad(samples, cache.frame_len, cache.frame_shift, num_frames)?;

    let mut scratch = KaldiFbankScratch::new(cache);
    let mut mel = vec![0.0f32; num_frames * cache.n_mels];

    for t in 0..num_frames {
        let start = t * cache.frame_shift;
        let raw = &padded[start..start + cache.frame_len];
        for (dst, &s) in scratch.frame.iter_mut().zip(raw) {
            *dst = s as f32 / PCM16_NORM;
        }

        remove_dc_offset(&mut scratch.frame);
        apply_preemphasis(&mut scratch.frame, PREEMPH_COEFF);
        for (s, &w) in scratch.frame.iter_mut().zip(cache.povey_window.iter()) {
            *s *= w;
        }

        scratch.fft_input[..cache.frame_len].copy_from_slice(&scratch.frame);
        for v in &mut scratch.fft_input[cache.frame_len..] {
            *v = 0.0;
        }

        cache
            .fft_plan
            .process_with_scratch(
                &mut scratch.fft_input,
                &mut scratch.fft_output,
                &mut scratch.fft_scratch,
            )
            .map_err(|e| KaldiFbankError::FftFailed(e.to_string()))?;

        for (p, c) in scratch
            .power
            .iter_mut()
            .zip(scratch.fft_output.iter().take(cache.n_fft_bins))
        {
            *p = c.norm_sqr();
        }

        let dst = &mut mel[t * cache.n_mels..(t + 1) * cache.n_mels];
        for (m, dst_m) in dst.iter_mut().enumerate() {
            let row = &cache.mel_basis[m * cache.n_fft_bins..(m + 1) * cache.n_fft_bins];
            let energy: f32 = row
                .iter()
                .zip(scratch.power.iter())
                .map(|(&w, &p)| w * p)
                .sum();
            *dst_m = energy.max(LOG_FLOOR).ln();
        }
    }

    Ok((mel, num_frames))
}

/// Reflete as bordas do sinal (mesma convenção de `_get_strided_batch` do lhotse,
/// `snip_edges=False`): espelha `(frame_len - frame_shift) / 2` amostras à esquerda
/// e o restante necessário à direita para cobrir `num_frames` janelas completas.
/// Isso reproduz o algoritmo per-amostra do Kaldi original (`FirstSampleOfFrame` +
/// reflexão de índice em `ExtractWindow`, `feature-window.cc`), verificado
/// numericamente contra o golden do lhotse.
fn reflect_pad(
    samples: &[i16],
    frame_len: usize,
    frame_shift: usize,
    num_frames: usize,
) -> Result<Vec<i16>, KaldiFbankError> {
    let num_samples = samples.len();
    let pad_left = (frame_len - frame_shift) / 2;
    if pad_left > num_samples {
        return Err(KaldiFbankError::TooFewSamples {
            minimum: pad_left,
            got: num_samples,
        });
    }

    let new_num_samples = (num_frames - 1) * frame_shift + frame_len;
    let total_pad = new_num_samples as isize - num_samples as isize;
    let pad_right = (total_pad - pad_left as isize).max(0) as usize;
    if pad_right > num_samples {
        return Err(KaldiFbankError::TooFewSamples {
            minimum: pad_right,
            got: num_samples,
        });
    }

    let mut padded = Vec::with_capacity(pad_left + num_samples + pad_right);
    padded.extend(samples[..pad_left].iter().rev().copied());
    padded.extend_from_slice(samples);
    padded.extend(samples[num_samples - pad_right..].iter().rev().copied());
    Ok(padded)
}

/// Remove o offset DC do frame (subtrai a média), no domínio do tempo — mesma
/// convenção do lhotse (`Wav2Win._forward_strided`, `layers.py:154-157`; a
/// docstring do módulo, linha 9-12, nota explicitamente que o lhotse faz isso e a
/// pré-ênfase no domínio do tempo em vez do domínio da frequência, "sem afetar
/// significativamente os resultados").
fn remove_dc_offset(frame: &mut [f32]) {
    let mean: f32 = frame.iter().sum::<f32>() / frame.len() as f32;
    for s in frame.iter_mut() {
        *s -= mean;
    }
}

/// Pré-ênfase kaldi: `y[0] = x[0] * (1 - coeff)`, `y[i] = x[i] - coeff * x[i-1]`
/// para `i >= 1`. Iterando de trás para frente evita precisar de um buffer
/// temporário: ao processar o índice `i`, `frame[i-1]` ainda guarda o valor
/// original (só é sobrescrito quando o próprio laço chega até ele).
fn apply_preemphasis(frame: &mut [f32], coeff: f32) {
    for i in (1..frame.len()).rev() {
        frame[i] -= coeff * frame[i - 1];
    }
    frame[0] -= coeff * frame[0];
}

/// Janela povey — `hann_window(N, periodic=False) ** 0.85` (convenção kaldi;
/// `lhotse/features/kaldi/layers.py:921-940`, `create_frame_window`).
fn povey_window(len: usize) -> Vec<f32> {
    (0..len)
        .map(|i| {
            let hann =
                0.5 - 0.5 * ((2.0 * std::f32::consts::PI * i as f32) / (len as f32 - 1.0)).cos();
            hann.powf(POVEY_EXPONENT)
        })
        .collect()
}

/// Escala mel HTK: `1127 * ln(1 + hz/700)` — distinta da escala Slaney usada em
/// [`crate::features`]. Fonte: `lhotse/features/kaldi/layers.py:943-944`
/// (`lin2mel`), a mesma fórmula do `torchaudio.compliance.kaldi`.
fn hz_to_mel_htk(hz: f64) -> f64 {
    1127.0 * (1.0 + hz / 700.0).ln()
}

/// Constrói o filterbank mel triangular compatível com torchaudio/kaldi
/// (`get_mel_banks`, `lhotse/features/kaldi/layers.py:960-1017`). Diferente do
/// filterbank Slaney de [`crate::features::build_mel_filterbank`]: sem
/// normalização de área, `n_fft_bins = fft_len / 2` (o bin de Nyquist nunca recebe
/// peso — a implementação de referência preenche esse bin com zero explicitamente,
/// então simplesmente o excluímos da matriz e do produto interno). Chamada apenas
/// na construção de [`KaldiFbankCache`] — nunca no caminho por-frame.
fn build_kaldi_mel_filterbank(
    fft_len: usize,
    n_mels: usize,
    sample_rate: u32,
    low_freq: f64,
    high_freq: f64,
) -> Vec<f32> {
    let n_fft_bins = fft_len / 2;
    let fft_bin_width = sample_rate as f64 / fft_len as f64;
    let mel_low = hz_to_mel_htk(low_freq);
    let mel_high = hz_to_mel_htk(high_freq);
    let mel_delta = (mel_high - mel_low) / (n_mels as f64 + 1.0);

    let mut fb = vec![0.0f32; n_mels * n_fft_bins];
    for m in 0..n_mels {
        let left = mel_low + m as f64 * mel_delta;
        let center = mel_low + (m as f64 + 1.0) * mel_delta;
        let right = mel_low + (m as f64 + 2.0) * mel_delta;
        for k in 0..n_fft_bins {
            let freq = k as f64 * fft_bin_width;
            let mel_k = hz_to_mel_htk(freq);
            let up = (mel_k - left) / (center - left);
            let down = (right - mel_k) / (right - center);
            let weight = up.min(down).max(0.0);
            fb[m * n_fft_bins + k] = weight as f32;
        }
    }
    fb
}

#[allow(dead_code)]
fn assert_kaldi_fbank_cache_is_send_sync() {
    fn assert_send<T: Send>() {}
    fn assert_sync<T: Sync>() {}
    assert_send::<KaldiFbankCache>();
    assert_sync::<KaldiFbankCache>();
}
