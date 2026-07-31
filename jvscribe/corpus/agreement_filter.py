"""Filtro por concordância CER par-a-par (M3 — T2.1, ADR-2).

O filtro é um predicado `segmento → bool` (contrato `CutSet.filter`, igual ao
padrão de `icefall/.../filter_cuts.py:124` `[FONTE-REPO]`): descarta o segmento
quando os 2 transcritores discordam além de τ. O threshold τ é **calibrado pela
distribuição empírica** de CER, nunca fixado a priori (o peer icefall instrui
calibrar pela distribuição — `filter_cuts.py:76-78`; `asr-evidence-discipline § 1`).

Invariante inviolável (`asr-evidence-discipline § 3 #10`): opera SÓ sobre o pool de
treino/val pseudo-rotulado — o test set nunca passa por concordância entre máquinas.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

import jiwer
import numpy as np

# Aponta para `common/`, o shared kernel. Antes apontava para `..` (a raiz de `jvscribe/`),
# de onde `text_normalize_ptbr` saiu na migração do kernel (M9/T3.1) — o insert ficou obsoleto
# e só o `conftest.py` mantinha o import de pé. Resultado: passava na suíte inteira e
# `corpus/run_pipeline.py` quebrava standalone.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))

from text_normalize_ptbr import normalize_for_wer_compare as normalize_ptbr  # noqa: E402


def pairwise_cer(hyp1: str, hyp2: str) -> float:
    """CER de `hyp2` contra `hyp1` (referência), ambas normalizadas para PT-BR.

    É **direcional** (jiwer.cer divide por len(hyp1) e pode exceder 1.0), não
    simétrica — o pipeline usa sempre `hyp1` (modelo #1) como referência, o que o
    mantém internamente consistente para calibrar τ. Usada como medida de discordância:
    ordena por magnitude, que é o que o filtro consome (review M1).
    """
    a = normalize_ptbr(hyp1)
    b = normalize_ptbr(hyp2)
    if not a and not b:
        return 0.0
    if not a or not b:
        # uma hipótese vazia (silêncio / VAD / falha do modelo — dado real, não input
        # inválido) e a outra não → discordância máxima; descarta o segmento (review H1).
        return 1.0
    return float(jiwer.cer(a, b))


def agree(hyp1: str, hyp2: str, tau: float) -> bool:
    """True se os transcritores concordam o bastante (CER ≤ τ) — mantém o segmento."""
    return pairwise_cer(hyp1, hyp2) <= tau


def calibrate_tau(cer_values: Sequence[float], keep_fraction: float) -> float:
    """τ tal que **aproximadamente** `keep_fraction` dos segmentos (os mais
    concordantes) sejam mantidos.

    Deriva o threshold da distribuição empírica (não a priori). `method='lower'`
    escolhe um valor observado; para n pequeno a fração mantida é ≥ `keep_fraction`
    (empates em τ podem reter um pouco mais). Fail-fast em entrada inválida
    (error-handling.md § 2). Review L-2.
    """
    if cer_values is None or len(cer_values) == 0:
        raise ValueError("calibrate_tau: distribuição de CER vazia — nada a calibrar")
    if not (0.0 < keep_fraction <= 1.0):
        raise ValueError(
            f"calibrate_tau: keep_fraction deve estar em (0, 1], veio {keep_fraction}"
        )
    return float(np.percentile(np.asarray(cer_values, dtype=float),
                               keep_fraction * 100.0, method="lower"))
