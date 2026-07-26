"""Teste da parte pura do conversor de corpus p/ manifest NeMo (fase 4)."""

from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("lhotse", reason="lhotse não instalado")
import prep_nemo as N  # noqa: E402


def _mock_rec(source: str, duration: float):
    src = types.SimpleNamespace(source=source)
    return types.SimpleNamespace(sources=[src], duration=duration)


def test_entry_formato_nemo():
    e = N._entry(_mock_rec("/a/x.opus", 3.14159), "Olá MUNDO")
    assert e == {"audio_filepath": "/a/x.opus", "duration": 3.142, "text": "olá mundo"}


def test_entry_none_quando_texto_vazio():
    # texto que normaliza para vazio → None (não vira linha de manifest inválida)
    assert N._entry(_mock_rec("/a/x.wav", 1.0), "!!!") is None
    assert N._entry(_mock_rec("/a/x.wav", 1.0), "") is None


def test_entry_preserva_diacriticos():
    e = N._entry(_mock_rec("/a/y.wav", 2.0), "São João coração")
    assert e["text"] == "são joão coração"
