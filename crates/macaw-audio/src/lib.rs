//! Captura dual, detecção de voz e extração de features para ASR em CPU.
//!
//! Este crate é o **domínio** do pipeline de áudio: DSP puro e captura, sem
//! qualquer dependência da arquitetura do modelo — que segue pendente até o ADR
//! de M2 (`PRD.md` § 8.1). Nada aqui precisa mudar quando o encoder for escolhido.
//!
//! Organização conforme `.claude/rules/architecture.md`:
//! - [`capture`] é adapter de infraestrutura (libpulse)
//! - [`features`], [`vad`] e [`metrics`] são domínio puro

pub mod capture;
pub mod features;
pub mod harness;
pub mod metrics;
pub mod vad;

/// Taxa de amostragem usada em todo o pipeline de M0.
///
/// Fixada em 16 kHz porque é a taxa esperada pelo modelo emprestado
/// (`models/m0-borrowed/config.json`) e a exigida pelo VAD Silero, cujo
/// `window_size` de 512 amostras equivale a 32 ms apenas nessa taxa.
///
/// Produção usará 8 kHz (padrão de call center brasileiro), mas isso pertence a
/// M5 — M0 prova encanamento, não o domínio final.
pub const SAMPLE_RATE: u32 = 16_000;

/// Número de bins mel produzidos pela extração de features.
///
/// Valor lido de `models/m0-borrowed/config.json` (`features_size: 128`).
pub const MEL_BINS: usize = 128;

/// Tamanho de janela do VAD, em amostras.
///
/// Invariante do modelo Silero — o código de referência do sherpa-onnx marca
/// este valor com "please don't change"
/// (`silero_vad_remove_silence.rs:66`).
pub const VAD_WINDOW: usize = 512;
