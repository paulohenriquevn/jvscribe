"""Teste do greedy CTC do probe DISC-05 (colapso blank+repetição + detok BPE).

É a única lógica algorítmica do probe (o resto é medição). Protege o decode que
sustenta os 3 WERs do probe.
"""
import sys
from pathlib import Path

import numpy as np
import pytest


pytest.importorskip("lhotse")  # o módulo instancia um Fbank no import
from tta_feature_align_probe import greedy  # noqa: E402


def _logp_from_argmax(seq: list[int], vocab: int) -> np.ndarray:
    """Constrói log-probs (T,V) cujo argmax por frame é `seq` (one-hot -inf/0)."""
    lp = np.full((len(seq), vocab), -9.0, dtype=np.float32)
    for t, i in enumerate(seq):
        lp[t, i] = 0.0
    return lp


def test_greedy_colapsa_blank_e_repeticao_e_detok():
    id2tok = {0: "<blk>", 1: "▁ca", 2: "sa", 3: "▁azul"}
    # argmax por frame: ca, ca(repete), blank, sa, sa(repete), blank, azul
    lp = _logp_from_argmax([1, 1, 0, 2, 2, 0, 3], vocab=4)
    # colapso -> [1,2,3] -> "▁ca"+"sa"+"▁azul" -> "▁casa▁azul" -> "casa azul"
    assert greedy(lp, id2tok) == "casa azul"


def test_greedy_tudo_blank_da_vazio():
    id2tok = {0: "<blk>", 1: "▁a"}
    assert greedy(_logp_from_argmax([0, 0, 0], vocab=2), id2tok) == ""
