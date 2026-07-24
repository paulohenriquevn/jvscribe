//! Testes de comportamento da extração log-mel (T3.1).
//!
//! Existe porque o blueprint mediu que `parakeet-rs` produz 128 bins
//! (`models/m0-borrowed/config.json: features_size: 128`) e porque afirmar
//! que a STFT "concentra energia no bin certo" sem medir seria a falácia #8
//! de `.claude/rules/asr-evidence-discipline.md` § 3 (confundir tamanho de
//! modelo com comportamento numérico real).

use hound::WavReader;
use macaw_audio::features::{FeatureCache, StreamState};
use macaw_audio::VAD_WINDOW;
use std::path::PathBuf;

fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/tone_440hz_16k.wav")
}

fn load_fixture_i16() -> Vec<i16> {
    let mut reader = WavReader::open(fixture_path())
        .expect("fixture ausente — rode scripts/make_fixtures.sh");
    reader
        .samples::<i16>()
        .collect::<Result<_, _>>()
        .expect("falha ao ler amostras da fixture")
}

#[test]
fn test_mel_output_has_128_bins() {
    let cache = FeatureCache::new();
    let mut state = StreamState::new(&cache);
    let samples = load_fixture_i16();
    let chunk = &samples[0..VAD_WINDOW];

    let output = state
        .extract(&cache, chunk)
        .expect("chunk de tamanho correto não deve falhar");

    assert_eq!(
        output.len() % 128,
        0,
        "output.len()={} não é múltiplo de 128",
        output.len()
    );
}

#[test]
fn test_stft_concentrates_power_at_expected_bin() {
    let cache = FeatureCache::new();
    let mut state = StreamState::new(&cache);
    let samples = load_fixture_i16();
    let chunk = &samples[0..VAD_WINDOW];

    let output = state
        .extract(&cache, chunk)
        .expect("chunk de tamanho correto não deve falhar");

    let (peak_bin, _) = output
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.partial_cmp(b.1).expect("log-mel não deve conter NaN"))
        .expect("output não deve estar vazio");

    let expected_bin = cache.nearest_mel_bin(440.0);

    assert!(
        peak_bin.abs_diff(expected_bin) <= 1,
        "pico em bin {peak_bin}, esperado {expected_bin} ± 1 bin para tom de 440 Hz [MEDIDO]"
    );
}
