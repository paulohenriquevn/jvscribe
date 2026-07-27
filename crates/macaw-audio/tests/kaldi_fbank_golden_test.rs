//! Casamento numérico entre `macaw_audio::kaldi_fbank` e o fbank 80-bin do lhotse
//! (task #25 — o extrator que alimenta o modelo de produção).
//!
//! O golden é gerado por `training/scripts/make_kaldi_fbank_golden.py`, que roda
//! `Fbank(FbankConfig(num_mel_bins=80))` — a MESMA chamada de
//! `training/prep_mls.py:99`/`training/prep_icefall.py:112` — sobre a fixture
//! determinística `tests/fixtures/tone_440hz_16k.wav` (sox, sem RNG, já versionada
//! por T0.1). Ambos os arquivos golden (`kaldi_fbank80_golden.f32` +
//! `.meta`) são versionados: são determinísticos e não dependem de rede.

use hound::WavReader;
use macaw_audio::kaldi_fbank::{extract_utterance, KaldiFbankCache, KaldiFbankError};
use std::path::PathBuf;

fn fixture_wav_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/tone_440hz_16k.wav")
}

fn golden_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/kaldi_fbank80_golden.f32")
}

fn load_fixture_i16() -> Vec<i16> {
    let mut reader = WavReader::open(fixture_wav_path())
        .expect("fixture ausente — rode scripts/make_fixtures.sh");
    reader
        .samples::<i16>()
        .collect::<Result<_, _>>()
        .expect("falha ao ler amostras da fixture")
}

fn load_golden() -> Vec<f32> {
    let bytes = std::fs::read(golden_path())
        .expect("golden ausente — rode `python3 training/scripts/make_kaldi_fbank_golden.py`");
    bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect()
}

/// Tolerância de casamento. `[MEDIDO]` sobre o golden do tom 440 Hz: MAE=0.000088,
/// max_abs_err=0.0025, pearson_r=1.000000 (n=300 frames × 80 bins) — o resíduo é
/// diferença de ordem de operações em ponto flutuante entre a FFT do `realfft` e a
/// do backend de FFT do PyTorch, não erro de fórmula (a fórmula é verificada termo
/// a termo contra `lhotse/features/kaldi/layers.py`). O piso abaixo (0.01) ainda dá
/// margem de 100× sobre o valor medido — suficiente para não quebrar em outra
/// máquina/versão de BLAS sem mascarar uma regressão de fórmula real. Um MAE dessa
/// ordem em log-mel é muito menor que a variação natural entre frames vizinhos de
/// fala real (~1-5 nats), então não deveria confundir o decoder.
const MAX_MEAN_ABS_ERROR: f32 = 0.01;
const MIN_PEARSON_CORRELATION: f64 = 0.999;

#[test]
fn test_kaldi_fbank_matches_lhotse_golden_within_tolerance() {
    let samples = load_fixture_i16();
    let golden = load_golden();
    let golden_n_frames = golden.len() / 80;

    let cache = KaldiFbankCache::new();
    let (mel, n_frames) = extract_utterance(&cache, &samples).expect("extração não deve falhar");

    assert_eq!(
        n_frames, golden_n_frames,
        "número de frames diverge do golden do lhotse"
    );
    assert_eq!(
        mel.len(),
        golden.len(),
        "tamanho do vetor de features diverge"
    );

    let n = mel.len() as f64;
    let mut sum_abs_err = 0.0f64;
    let mut max_abs_err = 0.0f32;
    let (mut mean_a, mut mean_b) = (0.0f64, 0.0f64);
    for (&a, &b) in mel.iter().zip(golden.iter()) {
        assert!(a.is_finite(), "log-mel não deve conter NaN/Inf");
        let err = (a - b).abs();
        sum_abs_err += err as f64;
        max_abs_err = max_abs_err.max(err);
        mean_a += a as f64;
        mean_b += b as f64;
    }
    mean_a /= n;
    mean_b /= n;

    let mut cov = 0.0f64;
    let (mut var_a, mut var_b) = (0.0f64, 0.0f64);
    for (&a, &b) in mel.iter().zip(golden.iter()) {
        let da = a as f64 - mean_a;
        let db = b as f64 - mean_b;
        cov += da * db;
        var_a += da * da;
        var_b += db * db;
    }
    let correlation = cov / (var_a.sqrt() * var_b.sqrt());
    let mae = (sum_abs_err / n) as f32;

    eprintln!(
        "[MEDIDO] kaldi_fbank vs golden lhotse: MAE={mae:.6} max_abs_err={max_abs_err:.6} \
         pearson_r={correlation:.6} (n_frames={n_frames}, n_bins=80)"
    );

    assert!(
        mae < MAX_MEAN_ABS_ERROR,
        "MAE {mae} >= tolerância {MAX_MEAN_ABS_ERROR} — extração diverge do golden"
    );
    assert!(
        correlation > MIN_PEARSON_CORRELATION,
        "correlação {correlation} <= {MIN_PEARSON_CORRELATION} — forma diverge do golden"
    );
}

#[test]
fn test_kaldi_fbank_empty_input_returns_zero_frames() {
    let cache = KaldiFbankCache::new();
    let (mel, n_frames) = extract_utterance(&cache, &[]).expect("entrada vazia não deve falhar");
    assert_eq!(n_frames, 0, "áudio vazio deve produzir zero frames");
    assert!(mel.is_empty());
}

#[test]
fn test_kaldi_fbank_too_short_utterance_returns_typed_error() {
    // 100 amostras produz num_frames=1 pela fórmula `(n + shift/2) / shift`, mas
    // exige 120 amostras de contexto à esquerda para refletir a borda
    // (`snip_edges=False`) — `[MEDIDO]`: 100 < 120, caso negativo por construção.
    let cache = KaldiFbankCache::new();
    let short = vec![100i16; 100];

    let result = extract_utterance(&cache, &short);

    match result {
        Err(KaldiFbankError::TooFewSamples { minimum, got }) => {
            assert_eq!(got, 100);
            assert!(
                minimum > got,
                "minimum ({minimum}) deveria exceder got ({got})"
            );
        }
        other => panic!("esperava TooFewSamples, veio {other:?}"),
    }
}

#[test]
fn test_kaldi_fbank_minimum_valid_utterance_produces_one_frame() {
    // Borda: 140 amostras é o menor tamanho, para esta configuração de frame,
    // onde tanto o contexto de reflexão esquerdo (120) quanto o direito (140)
    // cabem na utterance — `[MEDIDO]` por busca exaustiva sobre a fórmula em
    // `training/scripts/make_kaldi_fbank_golden.py`'s companion check. 139
    // amostras cairia no caso negativo acima.
    let cache = KaldiFbankCache::new();
    let minimal = vec![1000i16; 140];

    let (mel, n_frames) =
        extract_utterance(&cache, &minimal).expect("140 amostras é o mínimo válido");

    assert_eq!(n_frames, 1, "140 amostras deve produzir exatamente 1 frame");
    assert_eq!(mel.len(), n_frames * 80);
    assert!(
        mel.iter().all(|v| v.is_finite()),
        "sem NaN/Inf em entrada mínima válida"
    );
}
