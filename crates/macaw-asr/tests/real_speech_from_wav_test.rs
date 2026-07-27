//! PROVA end-to-end do runtime v0 a partir de um WAV (task #25 — fecha o pilar (a)
//! de wiring que `real_speech_test.rs` deixou explicitamente aberto).
//!
//! Diferença de `real_speech_test.rs`: aquele teste alimenta `transcribe()` com
//! features **pré-computadas pelo lhotse** (`fleurs_one.f32`) — prova o decoder, não
//! o extrator. Este teste roda a cadeia completa `wav → macaw_audio::kaldi_fbank →
//! AsrEngine::transcribe`, ou seja, prova que o **macaw-audio produz o sinal
//! correto** para o modelo de produção, fechando o pilar (a) do wiring (caller de
//! produção) apontado pelo `/review` do runtime v0.
//!
//! `fleurs_one_16k.wav` é a MESMA utterance FLEURS pt_br usada por `fleurs_one.f32`
//! (extraída via `training/scripts/extract_fleurs_one_wav.py`) — permite comparar a
//! transcrição obtida a partir do sinal do macaw-audio com a mesma referência já
//! usada em `real_speech_test.rs`. Fixtures de fala real não são versionadas (mesma
//! decisão já registrada ali) — `#[ignore]` + checagem de existência.

use std::path::PathBuf;

use hound::WavReader;
use macaw_asr::{AsrEngine, Vocab};
use macaw_audio::kaldi_fbank::{extract_utterance, KaldiFbankCache};

fn model_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../training/results/onnx")
}

fn wav_fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../macaw-audio/tests/fixtures/fleurs_one_16k.wav")
}

fn word_overlap(reference: &str, hyp: &str) -> f32 {
    let hyp_words: std::collections::HashSet<&str> = hyp.split_whitespace().collect();
    let ref_words: Vec<&str> = reference.split_whitespace().collect();
    if ref_words.is_empty() {
        return 0.0;
    }
    let hits = ref_words.iter().filter(|w| hyp_words.contains(*w)).count();
    hits as f32 / ref_words.len() as f32
}

// Mesmo padrão de T-02 do /review em `real_speech_test.rs`: `#[ignore]` em vez de
// early-return silencioso, para não mascarar a camada de integração vazia no CI.
#[test]
#[ignore = "requer fixtures de fala real (model.int8.onnx + fleurs_one_16k.wav) não versionados"]
fn transcreve_wav_real_via_macaw_audio_kaldi_fbank() {
    let model = model_dir().join("model.int8.onnx");
    let wav_path = wav_fixture_path();
    let text_f = model_dir().join("fleurs_one.txt");
    if !model.exists() || !wav_path.exists() {
        panic!(
            "fixtures ausentes (modelo={}, wav={}) — rode training/scripts/extract_fleurs_one_wav.py \
             e coloque model.int8.onnx/tokens.txt em training/results/onnx/",
            model.display(),
            wav_path.display()
        );
    }
    let reference = std::fs::read_to_string(&text_f).unwrap_or_default();
    let reference = reference.trim();

    // wav → macaw_audio::kaldi_fbank (80 bins, o extrator sob teste).
    let mut reader = WavReader::open(&wav_path).expect("wav fixture deve abrir");
    let spec = reader.spec();
    assert_eq!(spec.sample_rate, 16_000, "fixture deve ser 16 kHz");
    assert_eq!(spec.channels, 1, "fixture deve ser mono");
    let samples: Vec<i16> = reader
        .samples::<i16>()
        .collect::<Result<_, _>>()
        .expect("falha ao ler amostras do wav");

    let cache = KaldiFbankCache::new();
    let (mel, n_frames) =
        extract_utterance(&cache, &samples).expect("extração de fbank não deve falhar");
    assert!(
        n_frames > 0,
        "utterance real deveria produzir ao menos 1 frame"
    );

    // macaw_audio features → AsrEngine::transcribe (o decoder de produção).
    let mut engine = AsrEngine::load(&model).expect("carrega int8");
    let vocab = Vocab::load(&model_dir().join("tokens.txt")).expect("tokens");

    let hyp = engine
        .transcribe(&mel, n_frames, &vocab)
        .expect("transcribe");
    let overlap = word_overlap(reference, &hyp);
    eprintln!("REF: {reference}");
    eprintln!("HYP (via macaw_audio::kaldi_fbank): {hyp}");
    eprintln!(
        "[MEDIDO] word-overlap = {:.0}% (T={n_frames}, wav→macaw_audio→transcribe)",
        overlap * 100.0
    );

    assert!(
        !hyp.is_empty(),
        "transcrição a partir do sinal do macaw-audio não pode ser vazia"
    );
    // Mesmo piso conservador de `real_speech_test.rs` (WER medido ~30% em FLEURS).
    // Aqui a barra é ligeiramente mais severa: além do decoder, o EXTRATOR precisa
    // estar correto — um piso mais baixo mascararia um bug de extração como "ainda
    // aceitável".
    assert!(
        overlap >= 0.45,
        "overlap {overlap:.2} < 0.45 — sinal do macaw-audio não está alimentando o \
         decoder corretamente (features/decode desalinhados)"
    );
}
