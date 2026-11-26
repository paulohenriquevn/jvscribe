"""Testes do núcleo do streaming do mic_transcribe (lógica pura, sem I/O).

Cobre o LocalAgreement-2 (longest_common_prefix) e o colapso CTC→palavras
(ctc_words) — a lógica de negócio que decide o que é confirmado e onde cada
palavra começa no tempo. Determinístico; não abre mic nem carrega ONNX.
"""
import pytest

# Dependência de ambiente, não do produto: em runner limpo o módulo pode faltar.
# `importorskip` transforma isso em SKIP VISÍVEL em vez de erro de coleta, que
# derrubaria a suíte inteira (M9 — descoberto rodando o CI).
pytest.importorskip("sounddevice")

import numpy as np
import pytest

from mic_transcribe import longest_common_prefix, ctc_words, commit_localagreement


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


# --- commit_localagreement: confirmação + dedup de costura ------------------

def test_commit_confirma_prefixo_comum_sem_committed():
    # 2ª rodada concorda em "o lula"; "é" ainda não confirma
    newly, prev = commit_localagreement(
        ["o", "lula", "é"], [0.1, 0.5, 0.9], committed=[], prev_unc=["o", "lula"])
    assert [w for w, _ in newly] == ["o", "lula"]
    assert prev == ["é"]


def test_commit_dedup_costura_nao_reemite_ultima_confirmada():
    # "de" já confirmada em t=1.0 reaparece no left-context re-decodado (t=1.03)
    newly, prev = commit_localagreement(
        ["de", "colocação", "funcionava"], [1.03, 1.4, 1.9],
        committed=[("de", 1.0)], prev_unc=["colocação"])
    assert [w for w, _ in newly] == ["colocação"]   # NÃO re-emite "de"
    assert prev == ["funcionava"]


def test_commit_nao_dedup_quando_palavra_difere():
    # palavra na fronteira difere da última confirmada → sem dedup, nada confirma
    newly, prev = commit_localagreement(
        ["outro", "colocação"], [1.1, 1.5],
        committed=[("de", 1.0)], prev_unc=["colocação"])
    assert newly == []
    assert prev == ["outro", "colocação"]


def test_commit_descarta_palavras_antes_do_ultimo_confirmado():
    # palavras com tempo <= último confirmado são ignoradas
    newly, prev = commit_localagreement(
        ["ja", "confirmado", "novo"], [0.2, 0.6, 1.5],
        committed=[("confirmado", 0.6)], prev_unc=["novo"])
    assert [w for w, _ in newly] == ["novo"]
