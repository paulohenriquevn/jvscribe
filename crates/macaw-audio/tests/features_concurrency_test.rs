//! Testes de concorrência de T3.1 — `FeatureCache` compartilhado via `Arc`
//! entre `StreamState`s independentes não pode produzir cross-talk nem
//! panics. Executados sob `cargo test -- --test-threads=8`, repetidos
//! manualmente 10× consecutivas na validação (ver nota do plano em § T3.1
//! Concurrency tests).

use macaw_audio::features::{FeatureCache, StreamState};
use macaw_audio::VAD_WINDOW;
use std::sync::Arc;
use std::thread;

fn synthetic_chunk(seed: i32) -> Vec<i16> {
    (0..VAD_WINDOW as i32)
        .map(|i| (((i + seed) * 37) % 2000 - 1000) as i16)
        .collect()
}

#[test]
fn test_feature_cache_is_shared_safely_across_streams() {
    let cache = Arc::new(FeatureCache::new());
    let chunk = synthetic_chunk(0);

    // Referência sequencial: mesma entrada processada fora de threads.
    let mut sequential_state = StreamState::new(&cache);
    let expected: Vec<f32> = sequential_state
        .extract(&cache, &chunk)
        .expect("chunk válido não deve falhar")
        .to_vec();

    let mut handles = Vec::new();
    for _ in 0..2 {
        let cache = Arc::clone(&cache);
        let chunk = chunk.clone();
        handles.push(thread::spawn(move || {
            let mut state = StreamState::new(&cache);
            let mut last = Vec::new();
            for _ in 0..1000 {
                last = state
                    .extract(&cache, &chunk)
                    .expect("chunk válido não deve falhar")
                    .to_vec();
            }
            last
        }));
    }

    for handle in handles {
        let result = handle.join().expect("thread não deve entrar em panic");
        assert_eq!(
            result, expected,
            "espectrograma produzido em thread divergiu do processamento sequencial"
        );
    }
}

#[test]
fn test_stream_states_do_not_share_working_buffers() {
    let cache = Arc::new(FeatureCache::new());
    let chunk_a = synthetic_chunk(0);
    let chunk_b = synthetic_chunk(777);

    let mut state_a_seq = StreamState::new(&cache);
    let expected_a = state_a_seq
        .extract(&cache, &chunk_a)
        .expect("chunk válido não deve falhar")
        .to_vec();
    let mut state_b_seq = StreamState::new(&cache);
    let expected_b = state_b_seq
        .extract(&cache, &chunk_b)
        .expect("chunk válido não deve falhar")
        .to_vec();

    let cache_a = Arc::clone(&cache);
    let chunk_a_t = chunk_a.clone();
    let handle_a = thread::spawn(move || {
        let mut state = StreamState::new(&cache_a);
        state
            .extract(&cache_a, &chunk_a_t)
            .expect("chunk válido não deve falhar")
            .to_vec()
    });

    let cache_b = Arc::clone(&cache);
    let chunk_b_t = chunk_b.clone();
    let handle_b = thread::spawn(move || {
        let mut state = StreamState::new(&cache_b);
        state
            .extract(&cache_b, &chunk_b_t)
            .expect("chunk válido não deve falhar")
            .to_vec()
    });

    let result_a = handle_a.join().expect("thread A não deve entrar em panic");
    let result_b = handle_b.join().expect("thread B não deve entrar em panic");

    assert_eq!(
        result_a, expected_a,
        "stream A recebeu dado cruzado de outra thread"
    );
    assert_eq!(
        result_b, expected_b,
        "stream B recebeu dado cruzado de outra thread"
    );
}
