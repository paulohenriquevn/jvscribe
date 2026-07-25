"""Testes DSP da augmentação telefônica on-the-fly (M3 — T1.1).

Determinísticos: sinais analíticos (senos), sem RNG. Invariantes DSP com
tolerância explícita (testing.md § 3, § 4.1). Rodam com
`python3 -m pytest scripts/tests/test_corpus_telephone.py`.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from corpus.telephone_channel import apply_telephone_channel, TELEPHONE_SR  # noqa: E402


def _sine(freq: float, sr: int, dur: float = 1.0) -> np.ndarray:
    t = np.arange(int(sr * dur)) / sr
    return (0.8 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def test_downsample_to_8k():
    """Edge: entrada 16 kHz sai a 8 kHz com ~metade das amostras."""
    x = _sine(1000.0, 16000, 1.0)  # 16000 amostras
    y, sr = apply_telephone_channel(x, 16000)
    assert sr == TELEPHONE_SR == 8000
    assert abs(len(y) - 8000) <= 8, f"esperado ~8000 amostras, veio {len(y)}"


def test_bandpass_attenuates_out_of_band():
    """Um tom a 100 Hz (abaixo da banda 300-3400) é atenuado vs 1000 Hz (dentro)."""
    inside, _ = apply_telephone_channel(_sine(1000.0, 16000), 16000)
    outside, _ = apply_telephone_channel(_sine(100.0, 16000), 16000)
    # o de fora da banda deve ter energia bem menor
    assert _rms(outside) < 0.5 * _rms(inside), (
        f"banda não atenuou: rms_fora={_rms(outside):.4f} rms_dentro={_rms(inside):.4f}"
    )


def test_alaw_roundtrip_preserves_shape_within_tolerance():
    """A-law é lossy mas preserva a forma: correlação alta com um seno 1 kHz @ 8 kHz."""
    y, sr = apply_telephone_channel(_sine(1000.0, 16000), 16000)
    ref = _sine(1000.0, sr, len(y) / sr)[: len(y)]
    # correlação de Pearson entre saída e referência de mesma frequência
    corr = float(np.corrcoef(y, ref)[0, 1])
    assert corr >= 0.8, f"forma degradada demais pela cadeia: corr={corr:.3f}"


def test_no_tempfile_created(tmp_path, monkeypatch):
    """A augmentação é on-the-fly: não escreve em disco (DoD 'nunca em disco').

    Review L1: usa um tempdir ISOLADO (monkeypatch), não o /tmp compartilhado (que
    tornaria o teste flaky sob outros processos). A garantia de fundo é que
    `apply_telephone_channel` é numpy/scipy/audioop puro — sem I/O de arquivo.
    """
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    before = set(os.listdir(tmp_path))
    apply_telephone_channel(_sine(1000.0, 16000), 16000)
    after = set(os.listdir(tmp_path))
    assert before == after, f"criou arquivo(s) em disco: {after - before}"


def test_rejects_empty_array():
    """Negativo: array vazio → ValueError tipado com mensagem clara (error-handling.md § 2)."""
    with pytest.raises(ValueError, match="vazio"):
        apply_telephone_channel(np.array([], dtype=np.float32), 16000)


def test_output_is_float32_finite():
    """A saída é float32 finito (sem NaN/inf do filtro ou do codec)."""
    y, _ = apply_telephone_channel(_sine(1000.0, 16000), 16000)
    assert y.dtype == np.float32
    assert np.all(np.isfinite(y)), "saída tem NaN/inf"
