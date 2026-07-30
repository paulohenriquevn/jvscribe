"""Colapso CTC greedy — implementação única para todas as pipelines (M9/T3.1).

Consolida o que estava replicado em `batch/batch_transcribe.py`, `batch/decode_onnx_local.py`,
`eval/measure_callcenter.py`, `eval/measure_realcodec.py` e `scripts/tta_feature_align_probe.py`.

A consolidação só foi feita DEPOIS de medir a equivalência (`training/tests/test_ctc_equivalence.py`):
o laço de colapso é idêntico entre as cópias; o que divergia era a **detokenização** — quatro
usam `join + replace("▁", " ")` e `measure_realcodec` usa `sp.decode()`. Por isso as duas
convenções são funções distintas e nomeadas aqui, em vez de uma unificação cega que mudaria um
número já publicado.

Conformidade com o Rust: `crates/macaw-asr/src/decode.rs::ctc_greedy` implementa a mesma regra;
`training/tests/test_ctc_equivalence.py` compara as duas.
"""
from __future__ import annotations

from typing import Iterable, Sequence

BLANK = 0
WORD_START = "▁"


def collapse(ids: Iterable[int], blank: int = BLANK) -> list[int]:
    """Remove blank e colapsa repetição adjacente — a regra canônica do CTC greedy.

    >>> collapse([0, 5, 5, 0, 5, 3, 3])
    [5, 5, 3]
    """
    out: list[int] = []
    prev = -1
    for i in ids:
        i = int(i)
        if i != prev and i != blank:
            out.append(i)
        prev = i
    return out


def greedy_ids(log_probs_row, valid_len: int | None = None, blank: int = BLANK) -> list[int]:
    """`(T, V)` → ids colapsados, usando só os `valid_len` frames válidos."""
    row = log_probs_row[:valid_len] if valid_len is not None else log_probs_row
    return collapse(row.argmax(-1), blank=blank)


def detok_pieces(ids: Sequence[int], id2tok: dict[int, str]) -> str:
    """Detokenização por concatenação de pieces — convenção de 4 das 5 cópias originais."""
    return "".join(id2tok.get(i, "") for i in ids).replace(WORD_START, " ").strip()


def greedy_text(log_probs_row, id2tok: dict[int, str], valid_len: int | None = None) -> str:
    """Atalho `(T,V) → texto` com a convenção `join + replace`."""
    return detok_pieces(greedy_ids(log_probs_row, valid_len), id2tok)
