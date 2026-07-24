//! Prova de zero-alocação no caminho quente de `extract` (T3.1, ADR D3).
//!
//! O blueprint mediu que `parakeet-rs/src/audio.rs` aloca 5× por chunk.
//! Copiar aquele código repetiria o defeito que este teste existe para
//! medir. Usa `stats_alloc` como allocator global **apenas deste binário de
//! teste** — cada arquivo em `tests/` compila como um binário separado, então
//! isto não interfere com os demais testes do crate — para contar
//! alocações reais do heap em vez de inferir por leitura de código.

use macaw_audio::features::{FeatureCache, StreamState};
use stats_alloc::{Region, StatsAlloc, INSTRUMENTED_SYSTEM};
use std::alloc::System;

#[global_allocator]
static GLOBAL: &StatsAlloc<System> = &INSTRUMENTED_SYSTEM;

fn synthetic_chunk() -> Vec<i16> {
    (0..macaw_audio::VAD_WINDOW as i32)
        .map(|i| (((i * 37) % 2000) - 1000) as i16)
        .collect()
}

#[test]
fn test_extract_does_not_allocate_after_warmup() {
    let cache = FeatureCache::new();
    let mut state = StreamState::new(&cache);
    let chunk = synthetic_chunk();

    // Aquecimento: a primeira chamada pode tocar caminhos de inicialização
    // internos que o construtor de StreamState não cobre. Não é contada.
    state
        .extract(&cache, &chunk)
        .expect("aquecimento não deve falhar em chunk válido");

    let region = Region::new(GLOBAL);
    for _ in 0..100 {
        state
            .extract(&cache, &chunk)
            .expect("extract não deve falhar em chunk válido");
    }
    let stats = region.change();

    assert_eq!(
        stats.allocations, 0,
        "extract() alocou {} vezes em 100 chamadas após aquecimento — ADR D3 exige zero [MEDIDO]",
        stats.allocations
    );
}
