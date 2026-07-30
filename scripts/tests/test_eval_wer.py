"""Testes de WER+IC e do normalizador PT-BR (M1 — T3.1).

Determinísticos: valores conhecidos e seed fixa. Rodam com
`python3 -m pytest scripts/tests/test_eval_wer.py`.
"""

from __future__ import annotations

import os
import sys

import pytest

# Permite importar os scripts (mesmo dir pai).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval_wer import WerError, wer_with_ci  # noqa: E402
from text_normalize_ptbr import normalize_for_wer_compare as normalize_ptbr  # noqa: E402


# ---------------------------------------------------------------------
# Normalizador PT-BR
# ---------------------------------------------------------------------

def test_ptbr_normalizer_currency():
    assert normalize_ptbr("Custa R$ 100 hoje") == "custa 100 reais hoje"


def test_ptbr_normalizer_colloquial_and_accents():
    # "pra" -> "para"; acentos removidos; pontuação vira espaço.
    assert normalize_ptbr("Pra você, é já!") == "para voce e ja"


def test_ptbr_normalizer_is_deterministic():
    s = "Ligue pra R$ 50, tá?"
    assert normalize_ptbr(s) == normalize_ptbr(s)


# ---------------------------------------------------------------------
# WER com valores conhecidos
# ---------------------------------------------------------------------

def test_wer_known_pairs_one_substitution():
    # 1 substituição em 4 palavras = 25%.
    pairs = [("o gato subiu no", "o cachorro subiu no")]
    r = wer_with_ci(pairs, seed=1, n_boot=200)
    assert abs(r.wer - 0.25) < 1e-9, f"WER esperado 0,25, obteve {r.wer}"


def test_wer_perfect_match_is_zero():
    pairs = [("bom dia tudo bem", "bom dia tudo bem")]
    r = wer_with_ci(pairs, seed=1, n_boot=100)
    assert r.wer == 0.0


# ---------------------------------------------------------------------
# Bootstrap IC
# ---------------------------------------------------------------------

def test_bootstrap_ci_brackets_wer():
    # Vários pares; o IC deve conter o WER pontual.
    pairs = [
        ("um dois tres", "um dois tres"),
        ("quatro cinco seis", "quatro cinco erro"),
        ("sete oito nove", "sete oito nove"),
        ("dez onze doze", "dez erro doze"),
    ]
    r = wer_with_ci(pairs, seed=42, n_boot=1000)
    assert r.ci_low <= r.wer <= r.ci_high, f"IC [{r.ci_low},{r.ci_high}] deve conter WER {r.wer}"


def test_bootstrap_ci_single_utterance_degenerate():
    # EC-4: N=1 -> IC degenerado (low == high == wer), sem crash.
    pairs = [("o gato subiu", "o cachorro subiu")]
    r = wer_with_ci(pairs, seed=7, n_boot=500)
    assert r.n == 1
    assert r.ci_low == r.ci_high == r.wer, "N=1 dá IC sem informação (degenerado)"


def test_bootstrap_seed_is_reproducible():
    pairs = [("a b c d", "a x c d"), ("e f g h", "e f g z")]
    r1 = wer_with_ci(pairs, seed=99, n_boot=500)
    r2 = wer_with_ci(pairs, seed=99, n_boot=500)
    assert (r1.ci_low, r1.ci_high) == (r2.ci_low, r2.ci_high)


# ---------------------------------------------------------------------
# Casos negativos (error-handling)
# ---------------------------------------------------------------------

def test_wer_empty_list_is_error():
    # Negative (testing.md § 4.1): match= fixa a condição específica, não só a classe.
    with pytest.raises(WerError, match="nenhuma utterance"):
        wer_with_ci([], seed=1)


def test_wer_empty_reference_is_error():
    with pytest.raises(WerError, match="referência vazia"):
        wer_with_ci([("", "")], seed=1, normalize=False)


def test_bootstrap_ci_wider_for_smaller_n():
    # TEST-M1-04: o IC deve ser mais largo para N pequeno (mesma taxa de erro).
    # Padrão: 1 erro a cada 4 palavras. Repetimos a mesma utterance para variar N.
    base = ("um dois tres quatro", "um dois tres erro")  # WER 25%
    small = [base] * 4
    large = [base] * 40
    w_small = wer_with_ci(small, seed=5, n_boot=1000)
    w_large = wer_with_ci(large, seed=5, n_boot=1000)
    width_small = w_small.ci_high - w_small.ci_low
    width_large = w_large.ci_high - w_large.ci_low
    assert width_small >= width_large, (
        f"IC de N pequeno ({width_small}) deveria ser ≥ IC de N grande ({width_large})"
    )
