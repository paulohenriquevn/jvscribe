"""Testes do manifest Lhotse + augmentação telefônica on-the-fly (M3 — T4.1).

Usa `importorskip` para degradar de forma explícita (não silenciosa) se lhotse/torch
não estiverem instalados. Fixtures WAV são senos escritos em tmp_path — a augmentação
telefônica em si NUNCA é escrita em disco (é o que provamos).
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("lhotse", reason="lhotse (torch) não instalado — manifest test pulado")
import soundfile as sf  # noqa: E402

from corpus.build_manifest import build_cutset, load_telephone_audio  # noqa: E402


def _write_wav(path: str, freq: float, sr: int = 16000, dur: float = 1.0) -> None:
    t = np.arange(int(sr * dur)) / sr
    sf.write(path, (0.8 * np.sin(2 * np.pi * freq * t)).astype("float32"), sr)


def test_manifest_has_text_supervision(tmp_path):
    _write_wav(str(tmp_path / "a.wav"), 1000.0)
    cuts = build_cutset(str(tmp_path), {"a": "bom dia senhor"})
    cut = list(cuts)[0]
    assert cut.supervisions[0].text == "bom dia senhor"


def test_telephone_applied_lazily(tmp_path):
    """load_telephone_audio aplica a cadeia on-the-fly e retorna 8 kHz."""
    _write_wav(str(tmp_path / "a.wav"), 1000.0)
    cuts = build_cutset(str(tmp_path), {"a": "x"})
    audio, sr = load_telephone_audio(list(cuts)[0])
    assert sr == 8000, f"esperado 8 kHz on-the-fly, veio {sr}"
    assert audio.dtype == np.float32 and np.all(np.isfinite(audio))


def test_no_disk_materialization(tmp_path):
    """Construir o manifest + aplicar o telephone não escreve WAV aumentado em disco."""
    _write_wav(str(tmp_path / "a.wav"), 1000.0)
    sysroot = tempfile.gettempdir()
    before = set(os.listdir(sysroot))
    cuts = build_cutset(str(tmp_path), {"a": "x"})
    load_telephone_audio(list(cuts)[0])
    after = set(os.listdir(sysroot))
    assert before == after, f"materializou em disco: {after - before}"
