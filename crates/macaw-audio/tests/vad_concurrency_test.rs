//! Teste de concorrência de T2.1 — duas instâncias de `EnergyZcrVad`, uma por
//! stream, processando em threads separadas não podem compartilhar estado.
//!
//! Executado sob `cargo test -- --test-threads=8`, repetido manualmente 10×
//! consecutivas na validação (ver nota do plano em § T2.1 Concurrency tests)
//! para expor não-determinismo de ordenação.

use macaw_audio::vad::{EnergyZcrVad, SpeechDetector, SpeechState, VadConfig};
use macaw_audio::VAD_WINDOW;
use std::thread;

/// Tom sintético de amplitude alta e frequência fixa — não depende da
/// fixture em disco, para que o teste seja autocontido.
fn tone_window() -> Vec<i16> {
    (0..VAD_WINDOW)
        .map(|i| {
            let phase = i as f32 * 0.2;
            (phase.sin() * 16_000.0) as i16
        })
        .collect()
}

#[test]
fn test_vad_instances_are_independent_across_threads() {
    let handle_a = thread::spawn(|| {
        let mut vad = EnergyZcrVad::new(VadConfig::default());
        let window = tone_window();
        let mut states = Vec::with_capacity(1000);
        for _ in 0..1000 {
            states.push(
                vad.process_window(&window)
                    .expect("janela de tamanho correto não deve falhar"),
            );
        }
        states
    });

    let handle_b = thread::spawn(|| {
        let mut vad = EnergyZcrVad::new(VadConfig::default());
        let silence = vec![0i16; VAD_WINDOW];
        let mut states = Vec::with_capacity(1000);
        for _ in 0..1000 {
            states.push(
                vad.process_window(&silence)
                    .expect("janela de tamanho correto não deve falhar"),
            );
        }
        states
    });

    let states_a = handle_a.join().expect("thread A não deve entrar em panic");
    let states_b = handle_b.join().expect("thread B não deve entrar em panic");

    assert!(
        states_a.iter().all(|&s| s == SpeechState::Speech),
        "instância A (tom) foi afetada pela instância B (silêncio)"
    );
    assert!(
        states_b.iter().all(|&s| s == SpeechState::Silence),
        "instância B (silêncio) foi afetada pela instância A (tom)"
    );
}
