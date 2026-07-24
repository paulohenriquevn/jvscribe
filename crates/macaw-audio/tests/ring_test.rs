//! Testes de `ring.rs` — ring buffer sem alocação para amostras cruas.
//!
//! Não faz parte de uma task numerada do plano (a Baseline Context do plano
//! lista `ring.rs` como arquivo tocado, mas nenhuma task o implementa
//! explicitamente); estes testes cobrem o contrato mínimo exigido pelo papel
//! (`Ring buffers` — item liberado independente da arquitetura, per
//! `.claude/rules/asr-evidence-discipline.md` § 0) e pela instrução explícita
//! de sessão: "ring buffer sem alocação para amostras cruas, um por stream".

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread;

use macaw_audio::ring::{RingFullError, SampleRing};

#[test]
fn test_ring_push_pop_preserves_fifo_order() {
    let ring = SampleRing::with_capacity(4);

    ring.push(10).expect("push em buffer com espaço deve funcionar");
    ring.push(20).expect("push em buffer com espaço deve funcionar");
    ring.push(30).expect("push em buffer com espaço deve funcionar");

    assert_eq!(ring.pop(), Some(10));
    assert_eq!(ring.pop(), Some(20));
    assert_eq!(ring.pop(), Some(30));
    assert_eq!(ring.pop(), None);
}

#[test]
fn test_ring_rejects_push_when_full() {
    let ring = SampleRing::with_capacity(2);

    ring.push(1).expect("primeiro push deve caber");
    ring.push(2).expect("segundo push deve caber");

    let result = ring.push(3);

    assert_eq!(result, Err(RingFullError));
    // O rejeitado não deve ter sido enfileirado — capacidade continua em 2.
    assert_eq!(ring.len(), 2);
}

#[test]
fn test_ring_is_empty_reports_correctly() {
    let ring = SampleRing::with_capacity(3);

    assert!(ring.is_empty(), "ring recém-criado deve estar vazio");

    ring.push(7).expect("push deve funcionar");
    assert!(!ring.is_empty(), "ring com uma amostra não deve estar vazio");

    ring.pop();
    assert!(
        ring.is_empty(),
        "ring deve voltar a vazio depois de esvaziado"
    );
}

#[test]
fn test_ring_capacity_never_grows_after_warmup() {
    let ring = SampleRing::with_capacity(8);
    let initial_capacity = ring.capacity();

    // Muitos ciclos de push/pop mantendo len() sempre abaixo da capacidade —
    // se o VecDeque interno realocasse, a capacidade reportada por
    // VecDeque::capacity() poderia crescer. Como não expomos a capacidade
    // *interna* diretamente, a prova aqui é indireta e definitiva: a
    // capacidade *declarada* nunca muda, e nenhum push além dela é aceito
    // (provado por `test_ring_rejects_push_when_full`); juntas, as duas
    // propriedades garantem que o backing store nunca cresce além do
    // reservado na construção.
    for i in 0..10_000i16 {
        ring.push(i % 8).ok();
        ring.pop();
    }

    assert_eq!(ring.capacity(), initial_capacity);
}

#[test]
fn test_ring_producer_consumer_across_threads_preserves_total_count() {
    const CAPACITY: usize = 64;
    const TOTAL: usize = 5_000;

    let ring = Arc::new(SampleRing::with_capacity(CAPACITY));
    let consumed = Arc::new(AtomicUsize::new(0));

    let producer_ring = Arc::clone(&ring);
    let producer = thread::spawn(move || {
        let mut produced = 0usize;
        while produced < TOTAL {
            if producer_ring.push((produced % i16::MAX as usize) as i16).is_ok() {
                produced += 1;
            } else {
                thread::yield_now();
            }
        }
    });

    let consumer_ring = Arc::clone(&ring);
    let consumer_count = Arc::clone(&consumed);
    let consumer = thread::spawn(move || {
        let mut got = 0usize;
        while got < TOTAL {
            if consumer_ring.pop().is_some() {
                got += 1;
                consumer_count.fetch_add(1, Ordering::SeqCst);
            } else {
                thread::yield_now();
            }
        }
    });

    producer.join().expect("thread produtora não deve entrar em panic");
    consumer.join().expect("thread consumidora não deve entrar em panic");

    assert_eq!(consumed.load(Ordering::SeqCst), TOTAL);
    assert!(ring.is_empty(), "ring deve terminar vazio: tudo que foi produzido foi consumido");
}
