//! Decode CTC greedy + detokenização BPE — domínio puro (sem `ort`/ONNX), unit-testável.
//!
//! Algoritmo portado de `knowledge-base/references/sherpa-onnx/.../offline-ctc-greedy-search-decoder.cc:42`
//! (blueprint `m6-runtime`): por frame, `argmax`; emite o token só se ≠ blank E ≠ token anterior
//! (colapsa blanks e repetições — a semântica do CTC).

use crate::Vocab;

/// Índice do maior valor de um frame de log-probs. Frame vazio → 0 (fail-safe).
#[must_use]
pub fn argmax(frame: &[f32]) -> usize {
    frame
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
        .map_or(0, |(i, _)| i)
}

/// CTC greedy collapse. `log_probs` é o tensor `(T, vocab)` achatado; processa `t_len`
/// frames de `vocab` classes cada; `blank` é o id do blank (0 no icefall). Retorna os ids
/// de token após colapso (sem blank, sem repetições consecutivas).
///
/// Não entra em pânico com entrada curta: para no último frame completo disponível
/// (`rules/error-handling.md` — fail-safe em vez de índice fora de faixa).
#[must_use]
pub fn ctc_greedy(log_probs: &[f32], t_len: usize, vocab: usize, blank: usize) -> Vec<usize> {
    let mut out = Vec::new();
    if vocab == 0 {
        return out;
    }
    let mut prev = usize::MAX;
    for t in 0..t_len {
        let start = t * vocab;
        if start + vocab > log_probs.len() {
            break; // entrada mais curta que o declarado — para sem panicar
        }
        let y = argmax(&log_probs[start..start + vocab]);
        if y != blank && y != prev {
            out.push(y);
        }
        prev = y;
    }
    out
}

/// Detokenização BPE (sentencepiece): mapeia ids → pieces via `Vocab`, junta, troca o
/// marcador de fronteira de palavra `▁` (U+2581) por espaço e apara as bordas.
#[must_use]
pub fn detok(ids: &[usize], vocab: &Vocab) -> String {
    let mut s = String::new();
    for &id in ids {
        if let Some(piece) = vocab.decode(id) {
            s.push_str(piece);
        }
    }
    s.replace('\u{2581}', " ").trim().to_string()
}
