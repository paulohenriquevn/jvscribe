//! T5.3 — custo de CPU do VAD por janela de 512 amostras.
//!
//! O blueprint registrou o custo do VAD como `[DESCONHECIDO]` (nenhum peer
//! declara — § Coverage Corner 4). Este teste o mede: média ± desvio sobre ≥ 1000
//! repetições, com a CPU declarada, e o compara com o orçamento de 32 ms (a
//! duração de áudio de uma janela de 512 amostras a 16 kHz).

use std::time::Instant;

use macaw_audio::vad::{EnergyZcrVad, SpeechDetector, VadConfig};
use macaw_audio::VAD_WINDOW;

fn cpu_model() -> String {
    std::fs::read_to_string("/proc/cpuinfo")
        .ok()
        .and_then(|s| {
            s.lines()
                .find(|l| l.starts_with("model name"))
                .and_then(|l| l.split(':').nth(1))
                .map(|v| v.trim().to_string())
        })
        .unwrap_or_else(|| "CPU desconhecida".to_string())
}

#[test]
fn test_vad_cost_is_measured_and_reported() {
    const REPS: usize = 5_000;
    let mut vad = EnergyZcrVad::new(VadConfig::default());

    // Janela representativa: uma senoide, não silêncio (exercita RMS e ZCR).
    let window: Vec<i16> = (0..VAD_WINDOW)
        .map(|i| {
            let t = i as f32 / 16_000.0;
            (16_000.0 * (2.0 * std::f32::consts::PI * 440.0 * t).sin()) as i16
        })
        .collect();

    // Aquecimento — descarta efeitos de cache frio.
    for _ in 0..500 {
        let _ = vad.process_window(&window);
    }

    // Mede cada chamada individualmente para poder computar desvio-padrão.
    let mut samples_ns: Vec<f64> = Vec::with_capacity(REPS);
    for _ in 0..REPS {
        let t = Instant::now();
        let r = vad.process_window(&window);
        samples_ns.push(t.elapsed().as_nanos() as f64);
        assert!(r.is_ok(), "process_window não deveria falhar em janela válida");
    }

    let n = samples_ns.len() as f64;
    let mean = samples_ns.iter().sum::<f64>() / n;
    let var = samples_ns.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n;
    let std = var.sqrt();

    // Cauda: p99 e máximo. Para um custo por janela que decide se o backlog cresce
    // sob carga, o pior caso importa mais que a média — uma preempção do scheduler
    // pode inflar uma janela isolada (review MEDIUM-2).
    let mut sorted = samples_ns.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let p99 = sorted[((0.99 * n).ceil() as usize).saturating_sub(1).min(sorted.len() - 1)];
    let max = *sorted.last().expect("há amostras");

    let mean_us = mean / 1000.0;
    let std_us = std / 1000.0;
    let p99_us = p99 / 1000.0;
    let max_us = max / 1000.0;
    // Uma janela de 512 amostras a 16 kHz = 32 ms de áudio.
    let window_budget_us = VAD_WINDOW as f64 / 16_000.0 * 1_000_000.0;
    let rt_mean = window_budget_us / mean_us;
    let rt_worst = window_budget_us / max_us;

    eprintln!(
        "[MEDIDO] VAD (energia+ZCR) por janela de {VAD_WINDOW} amostras: \
         média {mean_us:.2} ± {std_us:.2} µs · p99 {p99_us:.2} µs · max {max_us:.2} µs \
         (n={REPS}) em \"{}\"",
        cpu_model()
    );
    eprintln!(
        "[MEDIDO] orçamento da janela = {window_budget_us:.0} µs (32 ms de áudio) \
         → VAD roda a {rt_mean:.0}× real-time na média, {rt_worst:.0}× no pior caso"
    );

    // A margem é avaliada no PIOR CASO, não na média — é o pior caso que ameaça o
    // orçamento de CPU do pipeline (RNF-07). ≥ 10× real-time mesmo no máximo
    // observado é o mínimo aceitável.
    assert!(
        rt_worst >= 10.0,
        "VAD no pior caso custa {max_us:.2}µs/janela = apenas {rt_worst:.0}× real-time (esperado ≥ 10×)"
    );
}
