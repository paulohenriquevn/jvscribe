"""Testes do manifest Lhotse + augmentação telefônica on-the-fly (M3 — T4.1).

Usa `importorskip` para degradar de forma explícita (não silenciosa) se lhotse/torch
não estiverem instalados. Fixtures WAV são senos escritos em tmp_path — a augmentação
telefônica em si NUNCA é escrita em disco (é o que provamos).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("lhotse", reason="lhotse (torch) não instalado — manifest test pulado")
import soundfile as sf  # noqa: E402

from unittest import mock  # noqa: E402

from corpus.build_manifest import build_cutset, filter_cutset, load_telephone_audio  # noqa: E402


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
    """Aplicar o telephone on-the-fly NÃO chama nenhuma escrita de áudio em disco.

    Review L1: mocka `soundfile.write` e assere que não foi chamado — prova a
    propriedade "nunca em disco" de forma robusta, não pelo proxy frágil de contar /tmp.
    """
    _write_wav(str(tmp_path / "a.wav"), 1000.0)
    cuts = build_cutset(str(tmp_path), {"a": "x"})
    cut = list(cuts)[0]
    with mock.patch("soundfile.write") as sf_write:
        audio, sr = load_telephone_audio(cut)
    sf_write.assert_not_called()
    assert sr == 8000


def test_filter_cutset_keeps_only_approved(tmp_path):
    """Review B-1: o manifest filtrado contém SÓ os cuts aprovados pelo filtro."""
    for cid in ("keep_a", "drop_b", "keep_c"):
        _write_wav(str(tmp_path / f"{cid}.wav"), 1000.0)
    full = build_cutset(str(tmp_path), {"keep_a": "x", "drop_b": "y", "keep_c": "z"})
    assert len(full) == 3
    kept = filter_cutset(full, {"keep_a", "keep_c"})
    ids = {c.recording_id for c in kept}
    assert ids == {"keep_a", "keep_c"}
    assert len(kept) == 2, "o cut descartado pelo filtro não pode estar no manifest"
