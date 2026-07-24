//! Testes de `metrics.rs` — backlog (T5.1) e deriva entre streams (T5.2).
//!
//! Todos os testes aqui são puros (sem I/O de áudio real) — rodam sempre,
//! independente do ambiente ter ou não um servidor de áudio disponível.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use macaw_audio::metrics::{BacklogCounter, DriftMeter};

/// Produz `n` itens a `rate_hz`, chamando `record_produced(1)` a cada item.
fn run_producer(counter: &BacklogCounter, rate_hz: u64, duration: Duration) {
    let interval = Duration::from_secs_f64(1.0 / rate_hz as f64);
    let start = Instant::now();
    while start.elapsed() < duration {
        counter.record_produced(1);
        thread::sleep(interval);
    }
}

/// Consome `n` itens a `rate_hz`, chamando `record_consumed(1)` a cada item.
fn run_consumer(counter: &BacklogCounter, rate_hz: u64, duration: Duration) {
    let interval = Duration::from_secs_f64(1.0 / rate_hz as f64);
    let start = Instant::now();
    while start.elapsed() < duration {
        counter.record_consumed(1);
        thread::sleep(interval);
    }
}

#[test]
fn test_backlog_counter_reports_zero_when_consumer_keeps_up() {
    let counter = BacklogCounter::new();

    // Interleaving determinístico (sem `sleep` de parede — review MEDIUM-3): cada
    // produção é seguida imediatamente pelo consumo correspondente. Modela um
    // consumidor que sempre alcança o produtor.
    //
    // A propriedade RNF-03 relevante aqui é que o backlog **não acumula** — não que
    // o valor instantâneo nunca pisque para 1. Como `sample_backlog()` é chamado
    // após cada produção E cada consumo, a série alterna 1,0,1,0 (o backlog É 1 no
    // instante entre produzir e consumir); logo o p99 dessa amostragem é 1, e
    // afirmá-lo 0 testaria um artefato da amostragem, não a propriedade física.
    // O que importa: a tendência não é de crescimento e o backlog volta a 0.
    for _ in 0..1_000 {
        counter.record_produced(1);
        counter.record_consumed(1);
    }

    assert!(
        !counter.is_growing(),
        "backlog não deveria crescer quando o consumidor acompanha o produtor"
    );
    assert_eq!(
        counter.backlog(),
        0,
        "backlog em regime deve voltar a 0 quando o consumidor acompanha"
    );
}

#[test]
fn test_backlog_counter_detects_growth_when_consumer_is_slow() {
    let counter = BacklogCounter::new();
    let duration = Duration::from_secs(1);

    // Produtor a 200/s, consumidor a 100/s — o backlog cresce continuamente.
    thread::scope(|scope| {
        scope.spawn(|| run_producer(&counter, 200, duration));
        scope.spawn(|| run_consumer(&counter, 100, duration));
    });

    assert!(
        counter.backlog() > 0,
        "backlog final deveria ser > 0 quando o consumidor é mais lento"
    );
    assert!(
        counter.is_growing(),
        "is_growing() deveria ser true quando o consumidor é mais lento"
    );
}

#[test]
fn test_backlog_counter_is_accurate_under_concurrent_producer_consumer() {
    for run in 0..10 {
        let counter = Arc::new(BacklogCounter::new());
        let duration = Duration::from_millis(500);
        let produced_total = Arc::new(AtomicU64::new(0));
        let consumed_total = Arc::new(AtomicU64::new(0));
        let observed_impossible = Arc::new(AtomicU64::new(0));

        let producer_counter = Arc::clone(&counter);
        let producer_total = Arc::clone(&produced_total);
        let producer = thread::spawn(move || {
            let interval = Duration::from_micros(500);
            let start = Instant::now();
            let mut n = 0u64;
            while start.elapsed() < duration {
                producer_counter.record_produced(1);
                n += 1;
                thread::sleep(interval);
            }
            producer_total.store(n, Ordering::SeqCst);
        });

        let consumer_counter = Arc::clone(&counter);
        let consumer_total = Arc::clone(&consumed_total);
        let consumer = thread::spawn(move || {
            let interval = Duration::from_micros(700);
            let start = Instant::now();
            let mut n = 0u64;
            while start.elapsed() < duration {
                consumer_counter.record_consumed(1);
                n += 1;
                thread::sleep(interval);
            }
            consumer_total.store(n, Ordering::SeqCst);
        });

        // 1000 leituras concorrentes do contador enquanto produtor/consumidor
        // rodam — nenhuma pode ser "impossível" (maior que tudo que já foi
        // produzido).
        let reader_counter = Arc::clone(&counter);
        let reader_impossible = Arc::clone(&observed_impossible);
        let reader = thread::spawn(move || {
            for _ in 0..1000 {
                let backlog = reader_counter.backlog();
                // u64 nunca é negativo por construção; a checagem real é que
                // o valor não excede um teto plausível (aqui, um valor bem
                // acima de qualquer taxa usada no teste).
                if backlog > 10_000 {
                    reader_impossible.fetch_add(1, Ordering::SeqCst);
                }
            }
        });

        producer.join().expect("thread produtora não deve panicar");
        consumer.join().expect("thread consumidora não deve panicar");
        reader.join().expect("thread leitora não deve panicar");

        assert_eq!(
            observed_impossible.load(Ordering::SeqCst),
            0,
            "run {run}: nenhuma leitura de backlog deveria ser impossível"
        );

        let p = produced_total.load(Ordering::SeqCst);
        let c = consumed_total.load(Ordering::SeqCst);
        assert_eq!(
            counter.backlog(),
            p.saturating_sub(c),
            "run {run}: produzido - consumido deve igualar o backlog final"
        );
    }
}

#[test]
fn test_drift_is_zero_for_identical_synthetic_streams() {
    let meter = DriftMeter::new(16_000);

    let mut last_drift = 0.0;
    for i in 1..=1000u64 {
        // Dois streams sintéticos avançando exatamente na mesma cadência.
        last_drift = meter.record(i, i);
    }

    assert!(
        last_drift.abs() < 1.0,
        "drift deveria ser ~0 para streams idênticos, obteve {last_drift}"
    );
}

#[test]
fn test_drift_detects_injected_skew() {
    let meter = DriftMeter::new(16_000);

    // Simula ~3 s de captura (48.000 amostras a 16 kHz) em chunks de 512 (a janela
    // do VAD), com stream_b avançando 5% mais devagar que stream_a. Contagens
    // reais representam duração real: só assim o drift alcança magnitude de
    // produto. A contagem é inteira, logo há jitter de quantização de ±1 amostra
    // passo a passo — a propriedade física correta é a **tendência crescente**,
    // medida por janelas onde o jitter se cancela, não monotonicidade estrita.
    const CHUNK: u64 = 512;
    let mut a_cum = 0u64;
    let mut b_cum = 0u64;
    let mut drift_at = Vec::new();
    for step in 1..=94u64 {
        // 94 * 512 ≈ 48.128 amostras ≈ 3 s
        a_cum += CHUNK;
        b_cum += (CHUNK as f64 * 0.95) as u64;
        let d = meter.record(a_cum, b_cum);
        if step % 10 == 0 {
            drift_at.push(d);
        }
    }

    // Tendência estritamente crescente entre janelas de ~10 chunks (o jitter de
    // ±1 amostra é desprezível frente ao crescimento de ~256 amostras/janela).
    for w in drift_at.windows(2) {
        assert!(
            w[1] > w[0],
            "a deriva deveria crescer entre janelas com desvio de cadência constante: {drift_at:?}"
        );
    }

    let last_drift = *drift_at.last().expect("deve haver leituras de janela");
    assert!(
        last_drift > 10.0,
        "drift deveria ultrapassar 10ms com 5% de desvio de cadência sobre ~3s, obteve {last_drift}"
    );
}
