//! Teste da fixture de áudio versionada (T0.1).
//!
//! Existe porque o blueprint registrou como lacuna que **nenhum peer versiona
//! fixture de áudio** — todos exigem download manual de modelo, o que torna os
//! testes dependentes de rede e o CI não reprodutível.

use std::path::PathBuf;

fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/tone_440hz_16k.wav")
}

#[test]
fn test_fixture_tone_has_expected_properties() {
    let path = fixture_path();
    assert!(
        path.exists(),
        "fixture ausente em {} — gere com scripts/make_fixtures.sh",
        path.display()
    );

    let reader = hound::WavReader::open(&path).expect("fixture não é um WAV válido");
    let spec = reader.spec();

    assert_eq!(spec.sample_rate, 16_000, "sample rate deve ser 16 kHz");
    assert_eq!(spec.channels, 1, "fixture deve ser mono");

    let samples: Vec<i16> = reader
        .into_samples::<i16>()
        .collect::<Result<_, _>>()
        .expect("falha ao ler amostras");

    assert_eq!(
        samples.len(),
        48_000,
        "fixture deve ter exatamente 3s a 16 kHz"
    );

    // Não é silêncio: um tom de 440 Hz tem RMS bem acima de zero.
    let sum_sq: f64 = samples.iter().map(|&s| {
        let v = s as f64 / i16::MAX as f64;
        v * v
    }).sum();
    let rms = (sum_sq / samples.len() as f64).sqrt();
    assert!(
        rms > 0.1,
        "fixture parece silenciosa (RMS = {rms:.6}); o tom não foi gerado"
    );
}
