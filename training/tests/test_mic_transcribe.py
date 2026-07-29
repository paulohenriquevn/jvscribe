"""Testes do núcleo do streaming do mic_transcribe (lógica pura, sem I/O).

Cobre o LocalAgreement-2 (longest_common_prefix) e o colapso CTC→palavras
(ctc_words) — a lógica de negócio que decide o que é confirmado e onde cada
palavra começa no tempo. Determinístico; não abre mic nem carrega ONNX.
"""
import numpy as np
import pytest

from mic_transcribe import longest_common_prefix, ctc_words


# --- LocalAgreement-2: prefixo comum entre duas hipóteses ------------------

def test_lcp_confirma_prefixo_parcial():
    # duas rodadas concordam em "o lula", divergem depois → confirma 2
    assert longest_common_prefix(["o", "lula", "e"], ["o", "lula", "foi"]) == 2


def test_lcp_lista_vazia_nao_confirma_nada():
    assert longest_common_prefix([], ["a"]) == 0
    assert longest_common_prefix(["a"], []) == 0


def test_lcp_concordancia_total():
    assert longest_common_prefix(["a", "b"], ["a", "b"]) == 2


def test_lcp_divergencia_no_inicio():
    assert longest_common_prefix(["x", "y"], ["a", "y"]) == 0


# --- Colapso CTC → palavras com timestamp ----------------------------------

def _id2tok():
    return {0: "<blk>", 1: "▁o", 2: "▁lu", 3: "la", 4: "▁bom"}


def test_ctc_colapsa_repeticoes_e_blanks_e_divide_palavras():
    # ▁o ▁o <blk> ▁lu ▁lu la <blk> ▁bom  → "o", "lula", "bom"
    path = np.array([1, 1, 0, 2, 2, 3, 0, 4])
    words, times = ctc_words(path, _id2tok(), stride=0.04, t0=0.0)
    assert words == ["o", "lula", "bom"]


def test_ctc_timestamps_no_inicio_de_cada_palavra():
    path = np.array([1, 1, 0, 2, 2, 3, 0, 4])   # o@frame0, lula@frame3, bom@frame7
    _, times = ctc_words(path, _id2tok(), stride=0.04, t0=0.0)
    assert times == pytest.approx([0.0, 0.12, 0.28])


def test_ctc_aplica_offset_t0_absoluto():
    path = np.array([1, 0, 4])                    # o@frame0, bom@frame2
    _, times = ctc_words(path, _id2tok(), stride=0.04, t0=10.0)
    assert times == pytest.approx([10.0, 10.08])


def test_ctc_tudo_blank_nao_gera_palavra():
    assert ctc_words(np.array([0, 0, 0]), _id2tok(), 0.04, 0.0) == ([], [])


def test_ctc_subpalavra_sem_word_start_anexa_a_anterior():
    # "la" (sem ▁) no início vira parte da 1ª palavra emitida
    words, _ = ctc_words(np.array([3, 0, 4]), _id2tok(), 0.04, 0.0)
    assert words == ["la", "bom"]
