//! Testes do harness de medição (M1 — T1.1, T1.2, T1.3).
//!
//! A agregação é **pura e determinística**: recebe tempos por-iteração já
//! medidos (não dorme de verdade), por `.claude/rules/testing.md` § 6 — sem
//! aleatoriedade/tempo não injetado. A cronometragem real com `Instant` fica no
//! modo `bench` (validação de integração), não no teste unitário.

use std::time::Duration;

use macaw_audio::harness::{HarnessError, LatencyHistogram, RtfxMeter, ThermalRatio};

// ---------------------------------------------------------------------
// T1.1 — RtfxMeter
// ---------------------------------------------------------------------

#[test]
fn test_rtfx_discards_warmup() {
    // 1º run frio (1s), dois runs quentes (0,1s cada). audio_secs = 1,0.
    // Descartando o warmup: RTFx = (1,0 × 2) / 0,2 = 10,0.
    // Sem descartar seria (1,0 × 3) / 1,2 ≈ 2,5 — o que o warmup mascara.
    let meter = RtfxMeter::new(1);
    let times = [
        Duration::from_millis(1000),
        Duration::from_millis(100),
        Duration::from_millis(100),
    ];
    let rtfx = meter.rtfx(1.0, &times).expect("deve medir");
    assert!(
        (rtfx - 10.0).abs() < 0.01,
        "RTFx deveria ignorar o warmup e dar ≈10,0, obteve {rtfx}"
    );
}

#[test]
fn test_rtfx_zero_wall_time_is_typed_error() {
    // Subject instantâneo (wall ≈ 0) não pode virar RTFx infinito.
    let meter = RtfxMeter::new(0);
    let times = [Duration::ZERO, Duration::ZERO];
    match meter.rtfx(1.0, &times) {
        Err(HarnessError::ZeroWallTime) => {}
        other => panic!("esperava Err(ZeroWallTime), obteve {other:?}"),
    }
}

#[test]
fn test_rtfx_warmup_ge_total_is_typed_error() {
    // EC-1: warmup >= total deixa a medição sem nenhuma iteração.
    let meter = RtfxMeter::new(3);
    let times = [Duration::from_millis(100), Duration::from_millis(100)];
    match meter.rtfx(1.0, &times) {
        Err(HarnessError::WarmupExceedsTotal { warmup, total }) => {
            assert_eq!(warmup, 3);
            assert_eq!(total, 2);
        }
        other => panic!("esperava Err(WarmupExceedsTotal), obteve {other:?}"),
    }
}

// ---------------------------------------------------------------------
// T1.2 — LatencyHistogram
// ---------------------------------------------------------------------

#[test]
fn test_latency_percentiles_known_distribution() {
    let mut h = LatencyHistogram::new();
    for ms in 1..=100u64 {
        h.record(Duration::from_millis(ms));
    }
    let (p50, p95, p99) = h.percentiles().expect("100 amostras não é vazio");
    // Percentil por nearest-rank sobre micros; 50 ms = 50_000 µs.
    assert_eq!(p50, 50_000, "p50 esperado 50 ms");
    assert_eq!(p95, 95_000, "p95 esperado 95 ms");
    assert_eq!(p99, 99_000, "p99 esperado 99 ms");
}

#[test]
fn test_latency_window_is_bounded() {
    // Review H4: a janela não cresce sem limite.
    let cap = 128;
    let mut h = LatencyHistogram::with_capacity(cap);
    for ms in 0..(cap as u64 * 3) {
        h.record(Duration::from_millis(ms));
    }
    assert_eq!(h.len(), cap, "histograma não deve exceder o cap");
}

#[test]
fn test_latency_percentiles_empty_is_unambiguous() {
    // EC-2: sem amostras, retornar None — nunca (0,0,0) que se confunde com
    // "latência zero".
    let h = LatencyHistogram::new();
    assert!(h.percentiles().is_none(), "vazio deve ser None, não (0,0,0)");
}

// ---------------------------------------------------------------------
// T1.3 — ThermalRatio
// ---------------------------------------------------------------------

#[test]
fn test_thermal_ratio_computes_min30_over_min1() {
    // RNF-04: RTFx(min30) ÷ RTFx(min1). min1=6,0, min30=5,0 → 0,833.
    let ratio = ThermalRatio::ratio(6.0, 5.0).expect("baseline não-zero");
    assert!(
        (ratio - 0.8333).abs() < 0.001,
        "razão térmica esperada ≈0,833, obteve {ratio}"
    );
}

#[test]
fn test_thermal_ratio_zero_baseline_is_typed_error() {
    // EC-3: RTFx(min1)=0 não pode virar divisão por zero.
    match ThermalRatio::ratio(0.0, 5.0) {
        Err(HarnessError::ZeroThermalBaseline) => {}
        other => panic!("esperava Err(ZeroThermalBaseline), obteve {other:?}"),
    }
}

// Nota de concorrência (review W1/TEST-M1-03): o harness de M1 é usado
// **single-threaded** — o modo `bench` roda o encoder em laço sequencial. A
// coleta concorrente de amostras a partir das threads de captura (M0) só existe
// no soak ao vivo, que ainda não está ligado ao harness (trabalho futuro). Um
// contador atômico foi removido por ser export sem caller de produção (YAGNI);
// quando o soak concorrente for cabeado, o teste de corrida volta com ele.
