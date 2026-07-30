//! Subcomando `transcribe <wav>` — o **caller de produção** do runtime v0 (pilar (a)
//! do wiring triad, `.claude/rules/cycle-implement.md`) apontado como pendente pelo
//! `/review`. Roda a cadeia completa `wav → macaw_audio::kaldi_fbank → AsrEngine::
//! transcribe → texto` e emite uma métrica de runtime (pilar (c): RTFx/tokens/duração).
//!
//! A prova numérica da cadeia vive em `macaw-asr/tests/real_speech_from_wav_test.rs`
//! (86% word-overlap `[MEDIDO]`); este módulo a expõe como um caminho de produção
//! observável, não só como teste.

use std::path::Path;
use std::time::Instant;

use hound::WavReader;
use macaw_asr::{AsrEngine, Vocab};
use macaw_audio::kaldi_fbank::{extract_utterance, KaldiFbankCache};
use macaw_audio::SAMPLE_RATE;

/// Erros tipados do subcomando — nunca panic, nunca silêncio
/// (`.claude/rules/error-handling.md` § 2).
#[derive(Debug)]
pub enum TranscribeError {
    /// O arquivo WAV não pôde ser aberto/lido.
    WavOpen { path: String, reason: String },
    /// O WAV não é 16 kHz mono (o modelo foi treinado nessa taxa).
    WavFormat { path: String, reason: String },
    /// A extração de features falhou (áudio curto demais, etc.).
    Features(String),
    /// O modelo ONNX ou o vocabulário não foram encontrados / falharam.
    Asr(String),
}

impl std::fmt::Display for TranscribeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::WavOpen { path, reason } => write!(f, "não abriu o WAV {path}: {reason}"),
            Self::WavFormat { path, reason } => write!(f, "formato de WAV inválido em {path}: {reason}"),
            Self::Features(r) => write!(f, "extração de features falhou: {r}"),
            Self::Asr(r) => write!(f, "inferência falhou: {r}"),
        }
    }
}

impl std::error::Error for TranscribeError {}

/// Observabilidade do wiring triad (pilar c): o que ops veem quando o decode roda.
#[derive(Debug, Clone, Copy)]
pub struct TranscribeMetrics {
    /// Frames de log-mel (T após subsampling do fbank).
    pub n_frames: usize,
    /// Duração do áudio em segundos.
    pub audio_secs: f32,
    /// Wall-time do decode (fbank + inferência + greedy) em ms.
    pub decode_ms: f32,
    /// RTFx = duração_áudio ÷ wall (o número decisivo de RNF-07).
    pub rtfx: f32,
    /// Nº de tokens (palavras) decodados.
    pub tokens: usize,
}

/// Lê um WAV 16 kHz mono i16 e valida o formato (caso negativo → erro tipado).
///
/// # Erros
/// [`TranscribeError::WavOpen`] se o arquivo não abre; [`TranscribeError::WavFormat`]
/// se a taxa não é 16 kHz ou não é mono.
pub fn read_wav_16k_mono(path: &Path) -> Result<Vec<i16>, TranscribeError> {
    let mut reader = WavReader::open(path).map_err(|e| TranscribeError::WavOpen {
        path: path.display().to_string(),
        reason: e.to_string(),
    })?;
    let spec = reader.spec();
    if spec.sample_rate != SAMPLE_RATE {
        return Err(TranscribeError::WavFormat {
            path: path.display().to_string(),
            reason: format!("esperado {SAMPLE_RATE} Hz, veio {}", spec.sample_rate),
        });
    }
    if spec.channels != 1 {
        return Err(TranscribeError::WavFormat {
            path: path.display().to_string(),
            reason: format!("esperado mono, veio {} canais", spec.channels),
        });
    }
    reader
        .samples::<i16>()
        .collect::<Result<_, _>>()
        .map_err(|e| TranscribeError::WavOpen {
            path: path.display().to_string(),
            reason: e.to_string(),
        })
}

/// Transcreve um WAV de ponta a ponta: `wav → kaldi_fbank → transcribe`, medindo RTFx.
/// `model_dir` deve conter `model.int8.onnx` + `tokens.txt` (o export do icefall).
///
/// # Erros
/// Propaga [`TranscribeError`] de leitura de WAV, extração ou inferência.
pub fn transcribe_wav(
    model_dir: &Path,
    wav_path: &Path,
) -> Result<(String, TranscribeMetrics), TranscribeError> {
    let samples = read_wav_16k_mono(wav_path)?;
    let audio_secs = samples.len() as f32 / SAMPLE_RATE as f32;

    // Setup de custo único (filterbank + carga do modelo) — FORA da janela de RTFx,
    // que mede o custo POR-utterance (o que importa para RNF-07): sob streaming o
    // modelo carrega uma vez e processa muitas utterances. Incluir o load aqui
    // inflaria o tempo e mediria algo que não é o RTFx (honestidade — Regra 3).
    let cache = KaldiFbankCache::new();
    // Modelo padrão int8; override via MACAW_MODEL (usado pelo EXP-01 int8-vs-fp32).
    let model_name =
        std::env::var("MACAW_MODEL").unwrap_or_else(|_| "model.int8.onnx".to_string());
    let mut engine = AsrEngine::load(&model_dir.join(&model_name))
        .map_err(|e| TranscribeError::Asr(e.to_string()))?;
    let vocab =
        Vocab::load(&model_dir.join("tokens.txt")).map_err(|e| TranscribeError::Asr(e.to_string()))?;

    // Identidade do vocabulário, não só cardinalidade (M9/T1.2b). `[MEDIDO]` os dois artefatos
    // do repositório têm 500 tokens emitíveis CADA e 492 dos 500 ids mapeiam tokens diferentes:
    // a checagem de dimensão passa nos dois e a transcrição sai integralmente errada. Degrada
    // silenciosamente quando não há `model_card.json`.
    macaw_asr::validate_against_model_card(model_dir, &vocab)
        .map_err(|e| TranscribeError::Asr(e.to_string()))?;

    let t0 = Instant::now();
    let (mel, n_frames) =
        extract_utterance(&cache, &samples).map_err(|e| TranscribeError::Features(e.to_string()))?;
    let text = engine
        .transcribe(&mel, n_frames, &vocab)
        .map_err(|e| TranscribeError::Asr(e.to_string()))?;
    let decode_ms = t0.elapsed().as_secs_f32() * 1000.0;

    let metrics = TranscribeMetrics {
        n_frames,
        audio_secs,
        decode_ms,
        rtfx: if decode_ms > 0.0 { audio_secs / (decode_ms / 1000.0) } else { 0.0 },
        tokens: text.split_whitespace().count(),
    };
    Ok((text, metrics))
}
