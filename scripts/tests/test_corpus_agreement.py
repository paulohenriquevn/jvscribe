"""Testes do filtro por concordância CER par-a-par (M3 — T2.1, T3.1).

Determinísticos: pares de texto conhecidos, sem I/O. O teste de carga sequencial
dos 2 whisper (T3.1) usa mock — a run real é a Integration Validation.
"""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from corpus.agreement_filter import (  # noqa: E402
    agree,
    calibrate_tau,
    pairwise_cer,
)


def test_cer_identical_is_zero():
    assert pairwise_cer("bom dia senhor", "bom dia senhor") == 0.0


def test_cer_totally_different_is_high():
    assert pairwise_cer("bom dia", "xyzqw kjhg") > 0.5


def test_cer_normalizes_ptbr():
    """'voce' vs 'você' (só acento/caixa) → CER baixo após normalização PT-BR."""
    assert pairwise_cer("VOCE esta bem", "você está bem") < 0.15


def test_agree_respects_tau():
    # par com discordância pequena
    h1, h2 = "o cliente ligou hoje", "o cliente ligou ontem"
    cer = pairwise_cer(h1, h2)
    assert agree(h1, h2, tau=cer + 0.01) is True
    assert agree(h1, h2, tau=cer - 0.01) is False


def test_calibrate_tau_matches_distribution():
    """τ = percentil que mantém keep_fraction dos segmentos mais concordantes."""
    cers = [0.0, 0.1, 0.2, 0.3, 0.9]
    # manter 80% → τ no percentil-80 (~0.3), descartando só o pior (0.9)
    tau = calibrate_tau(cers, keep_fraction=0.8)
    assert 0.25 <= tau <= 0.35, f"τ fora do esperado: {tau}"
    kept = [c for c in cers if c <= tau]
    assert len(kept) == 4


def test_calibrate_empty_raises():
    """Negativo: distribuição vazia → ValueError tipado."""
    with pytest.raises(ValueError, match="vazia"):
        calibrate_tau([], keep_fraction=0.8)


def test_calibrate_rejects_bad_fraction():
    with pytest.raises(ValueError, match="keep_fraction"):
        calibrate_tau([0.1, 0.2], keep_fraction=1.5)


def test_transcribe_pair_loads_sequentially():
    """T3.1: prova que o modelo #1 é liberado (del) ANTES de instanciar o #2 (RAM-safe).

    Rastreia a ordem de instanciação vs liberação via um contador de instâncias vivas.
    """
    from corpus import pseudo_label

    live = {"count": 0, "max": 0}

    class FakeModel:
        def __init__(self, size, **kw):
            live["count"] += 1
            live["max"] = max(live["max"], live["count"])

        def transcribe(self, path, **kw):
            seg = mock.Mock()
            seg.text = f"hyp de {os.path.basename(path)}"
            return [seg], mock.Mock()

        def __del__(self):
            live["count"] -= 1

    with mock.patch.object(pseudo_label, "WhisperModel", FakeModel):
        out = pseudo_label.transcribe_pair(
            {"a": "/tmp/a.wav", "b": "/tmp/b.wav"}, sizes=("small", "medium")
        )

    # nunca dois modelos vivos ao mesmo tempo (carga sequencial, EC-3 RAM)
    assert live["max"] == 1, f"carregou {live['max']} modelos ao mesmo tempo (esperado 1)"
    assert set(out.keys()) == {"a", "b"}
    for _id, (h1, h2) in out.items():
        assert isinstance(h1, str) and isinstance(h2, str)
