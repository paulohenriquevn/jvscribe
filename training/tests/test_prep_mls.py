"""Contrato do prep_mls (M4 fase 1). A correção de I/O (download+prepare_mls+fbank) é
verificada por execução real na instância; aqui garantimos o contrato do módulo e o
reuso (não duplicação) do normalize_ptbr."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("lhotse", reason="lhotse não instalado")
pytest.importorskip("lhotse.recipes", reason="lhotse.recipes indisponível")
import prep_mls  # noqa: E402


def test_mls_url_bem_formada():
    assert prep_mls.MLS_URL.startswith("https://")
    assert prep_mls.MLS_URL.endswith(".tar.gz")
    assert "portuguese" in prep_mls.MLS_URL


def test_reusa_normalize_do_prep_icefall_sem_duplicar():
    # audit D2: normalize_ptbr NÃO deve ser reimplementado aqui — vem do prep_icefall
    import prep_icefall
    assert prep_mls.PI is prep_icefall
    assert not hasattr(prep_mls, "normalize_ptbr")  # não redefinido no prep_mls


def test_funcoes_do_contrato_existem():
    for fn in ("download_extract_mls", "mls_train", "fleurs_split", "main"):
        assert callable(getattr(prep_mls, fn))
