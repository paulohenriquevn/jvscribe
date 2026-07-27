"""Núcleo de distância de edição — puro, sem I/O nem deps de áudio (numpy/soundfile).

Extraído de `eval_runtime_wer.py` (que importa numpy/pyarrow/soundfile no topo) para que
os tools de TEXTO puro — `cer_from_recogs.py`, `bootstrap_wer_ci.py` — e seus testes não
arrastem o stack de áudio só para computar Levenshtein (review M4: acoplamento indevido).
"""
from __future__ import annotations


def word_edit_distance(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein (S+D+I) sobre sequências — o numerador do WER/CER."""
    m, n = len(ref), len(hyp)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[n]
