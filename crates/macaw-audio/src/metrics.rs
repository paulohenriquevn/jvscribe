//! Instrumentação de primeira classe do pipeline de áudio (Fase T5).
//!
//! RNF-03 exige backlog zero em 99,9% das amostras, e o blueprint
//! `m0-walking-skeleton-blueprint.md` registrou que **nenhum peer mede isso**
//! — sem instrumentação aqui, o DoD de M0 não é provável, é apenas afirmado
//! (`.claude/rules/asr-evidence-discipline.md` § 2). Métricas entram desde a
//! primeira task (ADR D4 do plano), não como retrofit.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Calcula o percentil pelo método "nearest rank" sobre um slice já ordenado.
///
/// `pct` em `[0.0, 100.0]`. Retorna `0` para slice vazio — não há amostra
/// para reportar, e `0` é o valor neutro de backlog.
fn nearest_rank_percentile(sorted: &[u64], pct: f64) -> u64 {
    if sorted.is_empty() {
        return 0;
    }
    let rank = ((pct / 100.0) * sorted.len() as f64).ceil() as usize;
    let idx = rank.saturating_sub(1).min(sorted.len() - 1);
    sorted[idx]
}

/// Contador de backlog — amostras produzidas e ainda não consumidas.
///
/// Backlog é exposto como **contador de primeira classe** (RNF-03), não como
/// linha de log: `p50`/`p95`/`p99` vêm de `backlog_percentiles()` e podem ser
/// lidos a qualquer momento, inclusive sob produção/consumo concorrente.
pub struct BacklogCounter {
    produced: AtomicU64,
    consumed: AtomicU64,
    /// Série temporal de leituras de backlog — uma amostra por chamada de
    /// `record_produced`/`record_consumed`, na ordem em que ocorreram.
    history: Mutex<Vec<u64>>,
}

impl Default for BacklogCounter {
    fn default() -> Self {
        Self::new()
    }
}

impl BacklogCounter {
    /// Cria um contador zerado.
    pub fn new() -> Self {
        Self {
            produced: AtomicU64::new(0),
            consumed: AtomicU64::new(0),
            history: Mutex::new(Vec::new()),
        }
    }

    /// Registra `n` amostras produzidas e amostra o backlog resultante.
    pub fn record_produced(&self, n: u64) {
        self.produced.fetch_add(n, Ordering::SeqCst);
        self.sample_backlog();
    }

    /// Registra `n` amostras consumidas e amostra o backlog resultante.
    pub fn record_consumed(&self, n: u64) {
        self.consumed.fetch_add(n, Ordering::SeqCst);
        self.sample_backlog();
    }

    fn sample_backlog(&self) {
        let backlog = self.backlog();
        if let Ok(mut guard) = self.history.lock() {
            guard.push(backlog);
        }
        // Mutex envenenado: perde-se esta amostra, mas o contador em si
        // (produced/consumed, atômicos) segue correto — nunca panic aqui.
    }

    /// Backlog atual: produzido menos consumido.
    ///
    /// Lê `consumed` **antes** de `produced`: como todo consumo é
    /// necessariamente precedido por uma produção, essa ordem garante que o
    /// valor de `produced` lido é sempre >= o `consumed` já observado,
    /// eliminando a janela de corrida em que a subtração poderia parecer
    /// negativa. `saturating_sub` é uma segunda rede de segurança.
    pub fn backlog(&self) -> u64 {
        let consumed = self.consumed.load(Ordering::SeqCst);
        let produced = self.produced.load(Ordering::SeqCst);
        produced.saturating_sub(consumed)
    }

    /// `true` quando a tendência recente do backlog é de crescimento.
    ///
    /// Compara a média da segunda metade da série temporal com a da primeira
    /// metade: crescente quando a segunda é estritamente maior que a primeira
    /// e o backlog atual é > 0. Com menos de 4 amostras, não há série
    /// suficiente para uma tendência — retorna `false`.
    pub fn is_growing(&self) -> bool {
        let history = match self.history.lock() {
            Ok(guard) => guard.clone(),
            Err(poisoned) => poisoned.into_inner().clone(),
        };
        if history.len() < 4 {
            return false;
        }
        let mid = history.len() / 2;
        let (first_half, second_half) = history.split_at(mid);
        let mean = |xs: &[u64]| -> f64 { xs.iter().sum::<u64>() as f64 / xs.len() as f64 };
        let first_mean = mean(first_half);
        let second_mean = mean(second_half);
        second_mean > first_mean && self.backlog() > 0
    }

    /// Percentis p50/p95/p99 da série temporal de backlog observada até agora.
    pub fn backlog_percentiles(&self) -> (u64, u64, u64) {
        let mut sorted: Vec<u64> = match self.history.lock() {
            Ok(guard) => guard.clone(),
            Err(poisoned) => poisoned.into_inner().clone(),
        };
        sorted.sort_unstable();
        (
            nearest_rank_percentile(&sorted, 50.0),
            nearest_rank_percentile(&sorted, 95.0),
            nearest_rank_percentile(&sorted, 99.0),
        )
    }
}

/// Uma leitura de deriva entre dois streams, com o instante em que foi tomada.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DriftSample {
    /// Tempo decorrido desde a criação do `DriftMeter`.
    pub at: Duration,
    /// Deriva medida nesse instante, em milissegundos.
    pub drift_ms: f64,
}

/// Mede a deriva temporal entre dois streams de áudio ao longo do tempo (R1 /
/// risco R-M0-1 do blueprint) — reportada como **série temporal**, nunca só o
/// valor final, porque a pergunta de produto (U1 do plano) é se a deriva
/// compromete o roteamento de falante em turnos rápidos, e isso só aparece
/// olhando a evolução, não um número isolado.
///
/// `record()` recebe contagens de amostras já lidas de contadores atômicos
/// mantidos pelas próprias threads de captura — nunca lê da fonte de áudio
/// diretamente, então não pode bloquear nem perturbar essas threads.
pub struct DriftMeter {
    started_at: Instant,
    reference_rate_hz: u32,
    history: Mutex<Vec<DriftSample>>,
}

impl DriftMeter {
    /// Cria um medidor para dois streams que deveriam progredir à mesma
    /// `reference_rate_hz` (amostras por segundo).
    pub fn new(reference_rate_hz: u32) -> Self {
        Self {
            started_at: Instant::now(),
            reference_rate_hz,
            history: Mutex::new(Vec::new()),
        }
    }

    /// Registra uma leitura de progresso dos dois streams e calcula a deriva
    /// instantânea entre eles, em milissegundos.
    ///
    /// Deriva positiva significa que `stream_a` está adiantado em relação a
    /// `stream_b` (progrediu um tempo de áudio maior para a mesma taxa de
    /// referência).
    pub fn record(&self, stream_a_samples: u64, stream_b_samples: u64) -> f64 {
        let elapsed = self.started_at.elapsed();
        let rate = self.reference_rate_hz.max(1) as f64;
        let expected_a_secs = stream_a_samples as f64 / rate;
        let expected_b_secs = stream_b_samples as f64 / rate;
        let drift_ms = (expected_a_secs - expected_b_secs) * 1000.0;

        if let Ok(mut guard) = self.history.lock() {
            guard.push(DriftSample {
                at: elapsed,
                drift_ms,
            });
        }

        drift_ms
    }

    /// Série temporal completa de leituras de deriva.
    pub fn history(&self) -> Vec<DriftSample> {
        match self.history.lock() {
            Ok(guard) => guard.clone(),
            Err(poisoned) => poisoned.into_inner().clone(),
        }
    }
}
