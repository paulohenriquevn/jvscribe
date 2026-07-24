//! Ring buffer pré-alocado para amostras cruas de um stream de áudio.
//!
//! Um `SampleRing` por stream (mic e loopback) — nunca compartilhado entre
//! streams, para não introduzir cross-talk entre falantes
//! (`.claude/rules/architecture.md` § 3). A capacidade é reservada **uma
//! única vez**, na construção; `push`/`pop` nunca realocam depois disso — ver
//! `test_ring_capacity_never_grows_after_warmup` em
//! `tests/ring_test.rs`.
//!
//! Baixa contenção via `Mutex` de seção crítica curta (empilha/retira uma
//! amostra e libera), adequado ao desenho de uma thread produtora e uma
//! consumidora por stream — não lock-free, mas o suficiente para o walking
//! skeleton de M0; um desenho lock-free fica para quando a medição (T5.1/T5.3)
//! mostrar que a contenção do Mutex é o gargalo.

use std::collections::VecDeque;
use std::sync::Mutex;

/// Erro de capacidade excedida — o produtor está mais rápido que o consumidor.
///
/// Não é tratado como pânico: quem chama decide a política de descarte. O
/// crescimento de backlog em si é responsabilidade de `metrics.rs` (RNF-03),
/// não deste módulo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RingFullError;

impl std::fmt::Display for RingFullError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "ring buffer cheio — consumidor mais lento que o produtor")
    }
}

impl std::error::Error for RingFullError {}

/// Ring buffer de baixa contenção para amostras `i16` de um único stream.
///
/// Capacidade fixa, reservada inteiramente na construção via
/// `VecDeque::with_capacity`. `push`/`pop` nunca alocam depois disso, desde
/// que a capacidade não seja excedida (nesse caso `push` retorna
/// `Err(RingFullError)` em vez de crescer o buffer).
pub struct SampleRing {
    capacity: usize,
    buf: Mutex<VecDeque<i16>>,
}

impl SampleRing {
    /// Cria um ring buffer com `capacity` amostras reservadas antecipadamente.
    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            capacity,
            buf: Mutex::new(VecDeque::with_capacity(capacity)),
        }
    }

    /// Capacidade fixa do buffer, em amostras.
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Amostras atualmente enfileiradas.
    pub fn len(&self) -> usize {
        match self.buf.lock() {
            Ok(guard) => guard.len(),
            Err(poisoned) => poisoned.into_inner().len(),
        }
    }

    /// `true` quando não há amostras enfileiradas.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Empilha uma amostra.
    ///
    /// Retorna `Err(RingFullError)` sem bloquear e sem alocar quando a
    /// capacidade está esgotada — nunca cresce o `VecDeque` além da reserva
    /// inicial.
    pub fn push(&self, sample: i16) -> Result<(), RingFullError> {
        let mut guard = match self.buf.lock() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };
        if guard.len() >= self.capacity {
            return Err(RingFullError);
        }
        guard.push_back(sample);
        Ok(())
    }

    /// Retira a amostra mais antiga, ou `None` se o buffer está vazio.
    pub fn pop(&self) -> Option<i16> {
        let mut guard = match self.buf.lock() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };
        guard.pop_front()
    }
}
