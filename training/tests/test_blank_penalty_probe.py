"""Teste do greedy com blank penalty (DISC-06 probe).

β=0 deve reproduzir o greedy padrão; β>0 deve suprimir blanks que venceriam por
pouca margem (a alavanca de decoder-space que o probe testa).
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
pytest.importorskip("lhotse")
pytest.importorskip("onnxruntime")
from blank_penalty_probe import greedy_penalized  # noqa: E402


def _lp(seq_or_rows, vocab=None):
    if vocab is None:  # já é matriz de logits
        return np.asarray(seq_or_rows, dtype=np.float32)
    lp = np.full((len(seq_or_rows), vocab), -9.0, dtype=np.float32)
    for t, i in enumerate(seq_or_rows):
        lp[t, i] = 0.0
    return lp


def test_beta_zero_e_greedy_padrao():
    id2tok = {0: "<blk>", 1: "▁ca", 2: "sa"}
    # argmax [ca, ca(rep), blank, sa] -> colapso -> "▁ca"+"sa" -> "casa"
    assert greedy_penalized(_lp([1, 1, 0, 2], vocab=3), id2tok, 0.0) == "casa"


def test_penalidade_suprime_blank_marginal():
    id2tok = {0: "<blk>", 1: "▁a"}
    # 1 frame: blank(0.0) vence 'a'(-1.0) por 1.0 de margem.
    lp = _lp([[0.0, -1.0]])
    assert greedy_penalized(lp, id2tok, 0.0) == ""      # β=0 -> blank -> vazio
    assert greedy_penalized(lp, id2tok, 2.0) == "a"     # β=2 derruba o blank -> 'a'
