"""Teste da parte pura do harness de penalidade telefônica (experimento #1).
A cadeia telefônica em si é testada em jvscribe/corpus/tests; aqui cobrimos o
`_resample` (o glue de volta a 16 kHz) e o reuso do apply_telephone_channel."""

from __future__ import annotations


import numpy as np
import pytest


pytest.importorskip("scipy", reason="scipy não instalado")
pytest.importorskip("lhotse", reason="lhotse não instalado")
import make_telephone_test as M  # noqa: E402


def test_resample_identidade_quando_mesma_sr():
    x = np.linspace(-1, 1, 1000).astype(np.float32)
    y = M._resample(x, 16000, 16000)
    assert y is x  # short-circuit sem recalcular


def test_resample_dobra_comprimento_ao_dobrar_sr():
    x = np.zeros(800, dtype=np.float32)
    y = M._resample(x, 8000, 16000)
    assert len(y) == 1600  # 8k → 16k = 2×


def test_resample_metade_comprimento_ao_metade_sr():
    x = np.zeros(1600, dtype=np.float32)
    y = M._resample(x, 16000, 8000)
    assert len(y) == 800


def test_reusa_apply_telephone_channel_do_m3_sem_duplicar():
    import telephone_channel
    assert M.apply_telephone_channel is telephone_channel.apply_telephone_channel
