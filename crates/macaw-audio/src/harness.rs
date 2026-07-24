//! Harness de medição de M1 — os 5 critérios de "real-time verdadeiro"
//! (`PRD.md` § 6). Infraestrutura de medição do domínio de áudio: mede o
//! `AsrEngine` (adapter) pela API pública, sem acoplar ao backend.
//!
//! A agregação é **pura**: recebe tempos por-iteração já medidos, para que o
//! teste seja determinístico (`.claude/rules/testing.md` § 6). A cronometragem
//! real com `Instant` fica no chamador (modo `bench`).
//!
//! Terminologia fixada (blueprint ADR D3): **RTFx = duração_do_áudio ÷
//! tempo_de_parede** (maior = mais rápido), nunca o "RTF" inverso dos peers.

use std::collections::VecDeque;
use std::time::Duration;

use crate::metrics::nearest_rank_percentile;

/// Cap padrão da janela de latência — memória limitada (review H4, mesmo
/// racional do `BacklogCounter`).
const DEFAULT_LATENCY_CAP: usize = 4096;

/// Erros tipados do harness. Nunca panic, nunca `inf`/`NaN` silencioso —
/// `.claude/rules/error-handling.md` § 2.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HarnessError {
    /// Tempo de parede total foi zero — RTFx seria infinito.
    ZeroWallTime,
    /// `warmup_iters` ≥ número de iterações medidas (EC-1): não sobra amostra.
    WarmupExceedsTotal { warmup: usize, total: usize },
    /// RTFx de referência (min1) foi zero — razão térmica seria divisão por zero (EC-3).
    ZeroThermalBaseline,
}

impl std::fmt::Display for HarnessError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            HarnessError::ZeroWallTime => {
                write!(f, "tempo de parede total foi zero; RTFx seria infinito")
            }
            HarnessError::WarmupExceedsTotal { warmup, total } => write!(
                f,
                "warmup ({warmup}) >= iterações medidas ({total}); nada a medir"
            ),
            HarnessError::ZeroThermalBaseline => write!(
                f,
                "RTFx de referência (min1) foi zero; razão térmica indefinida"
            ),
        }
    }
}

impl std::error::Error for HarnessError {}

/// Mede RTFx sustentado descartando as iterações de warmup (blueprint ADR D2).
///
/// O warmup existe porque o 1º run é frio (cache/turbo) e mente sobre o regime
/// sustentado (falácia § 3 #4 de `asr-evidence-discipline.md`).
pub struct RtfxMeter {
    warmup_iters: usize,
}

impl RtfxMeter {
    /// Cria um medidor que descarta as primeiras `warmup_iters` iterações.
    pub fn new(warmup_iters: usize) -> Self {
        Self { warmup_iters }
    }

    /// RTFx sobre os tempos por-iteração, descartando o warmup.
    ///
    /// `audio_secs` é a duração de áudio processada por iteração. RTFx =
    /// (audio_secs × nº_medidas) ÷ soma_dos_tempos_de_parede_medidos.
    pub fn rtfx(&self, audio_secs: f64, iter_wall_times: &[Duration]) -> Result<f64, HarnessError> {
        if self.warmup_iters >= iter_wall_times.len() {
            return Err(HarnessError::WarmupExceedsTotal {
                warmup: self.warmup_iters,
                total: iter_wall_times.len(),
            });
        }
        let measured = &iter_wall_times[self.warmup_iters..];
        let total_wall: Duration = measured.iter().sum();
        let total_wall_secs = total_wall.as_secs_f64();
        if total_wall_secs <= 0.0 {
            return Err(HarnessError::ZeroWallTime);
        }
        let total_audio = audio_secs * measured.len() as f64;
        Ok(total_audio / total_wall_secs)
    }
}

/// Histograma de latência com janela limitada — reporta p50/p95/p99 (RNF-02).
///
/// Reusa `nearest_rank_percentile` de `metrics.rs` (DRY) e o padrão de janela
/// limitada por `VecDeque` (review H4). Armazena micros para preservar a cauda.
pub struct LatencyHistogram {
    samples: VecDeque<u64>,
    cap: usize,
}

impl LatencyHistogram {
    /// Histograma com o cap padrão.
    pub fn new() -> Self {
        Self::with_capacity(DEFAULT_LATENCY_CAP)
    }

    /// Histograma com cap explícito de janela.
    pub fn with_capacity(cap: usize) -> Self {
        Self {
            samples: VecDeque::with_capacity(cap),
            cap: cap.max(1),
        }
    }

    /// Registra uma latência (armazenada em micros).
    pub fn record(&mut self, latency: Duration) {
        if self.samples.len() == self.cap {
            self.samples.pop_front();
        }
        self.samples.push_back(latency.as_micros() as u64);
    }

    /// Nº de amostras na janela.
    pub fn len(&self) -> usize {
        self.samples.len()
    }

    /// True se não há amostras.
    pub fn is_empty(&self) -> bool {
        self.samples.is_empty()
    }

    /// p50/p95/p99 em micros, ou `None` se vazio (EC-2 — nunca `(0,0,0)`, que
    /// se confunde com latência zero).
    pub fn percentiles(&self) -> Option<(u64, u64, u64)> {
        if self.samples.is_empty() {
            return None;
        }
        let mut sorted: Vec<u64> = self.samples.iter().copied().collect();
        sorted.sort_unstable();
        Some((
            nearest_rank_percentile(&sorted, 50.0),
            nearest_rank_percentile(&sorted, 95.0),
            nearest_rank_percentile(&sorted, 99.0),
        ))
    }
}

impl Default for LatencyHistogram {
    fn default() -> Self {
        Self::new()
    }
}

/// Razão de estabilidade térmica (RNF-04): RTFx(min30) ÷ RTFx(min1).
///
/// O i7-1355U é um chip U de 15 W — não sustenta turbo sob carga contínua. A
/// razão < 1 mede o quanto o throttling degrada o RTFx ao longo do soak.
pub struct ThermalRatio;

impl ThermalRatio {
    /// Razão min30/min1. Erro tipado se o baseline (min1) for zero (EC-3).
    pub fn ratio(rtfx_min1: f64, rtfx_min30: f64) -> Result<f64, HarnessError> {
        if rtfx_min1 <= 0.0 {
            return Err(HarnessError::ZeroThermalBaseline);
        }
        Ok(rtfx_min30 / rtfx_min1)
    }
}
