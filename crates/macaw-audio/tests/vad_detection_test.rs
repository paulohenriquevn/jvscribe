//! Testes de comportamento do VAD (T2.1).
//!
//! Existe porque `.claude/rules/asr-evidence-discipline.md` exige que cada
//! afirmação sobre o VAD seja verificável, e o blueprint registrou
//! `threshold=0.5`, `window_size=512`, `sample_rate=16000` como os
//! parâmetros consistentes entre os dois exemplos do peer sherpa-onnx.

use hound::WavReader;
use macaw_audio::vad::{EnergyZcrVad, SpeechDetector, SpeechState, VadConfig, VadError};
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
fn test_vad_detects_speech_in_tone_fixture() {
    let samples = load_fixture_i16();
    let mut vad = EnergyZcrVad::new(VadConfig::default());

    let mut any_speech = false;
    for window in samples.chunks_exact(VAD_WINDOW) {
        let state = vad
            .process_window(window)
            .expect("janela de 512 amostras não deve falhar");
        if state == SpeechState::Speech {
            any_speech = true;
        }
    }

    assert!(
        any_speech,
        "nenhuma janela do tom de 440 Hz foi classificada como fala [MEDIDO]"
    );
}

#[test]
fn test_vad_reports_silence_for_zero_signal() {
    let samples = vec![0i16; 48_000];
    let mut vad = EnergyZcrVad::new(VadConfig::default());

    for window in samples.chunks_exact(VAD_WINDOW) {
        let state = vad
            .process_window(window)
            .expect("janela de 512 amostras não deve falhar");
        assert_eq!(
            state,
            SpeechState::Silence,
            "sinal de zeros não pode ser classificado como fala"
        );
    }
}

#[test]
fn test_vad_rejects_window_of_wrong_size() {
    let window = vec![0i16; 256];
    let mut vad = EnergyZcrVad::new(VadConfig::default());

    let result = vad.process_window(&window);

    assert_eq!(
        result,
        Err(VadError::InvalidWindowSize {
            expected: 512,
            got: 256
        })
    );
}
