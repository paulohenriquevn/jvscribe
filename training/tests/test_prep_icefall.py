"""Testes da parte pura do adaptador prep_icefall (M4). Determinísticos, sem I/O/GPU.

A parte de download/fbank é validada por execução real (smoke local + na instância);
aqui testamos a normalização de texto (o alvo de treino) e a estrutura das fontes.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("lhotse", reason="lhotse (torch) não instalado")
from prep_icefall import SOURCES, normalize_ptbr  # noqa: E402


def test_normalize_lower_and_collapse_space():
    assert normalize_ptbr("  Bom   DIA  ") == "bom dia"


def test_normalize_preserva_acentos_ptbr():
    # NUNCA remover diacríticos (regra de ortografia pt)
    assert normalize_ptbr("Você está São João coração") == "você está são joão coração"


def test_normalize_remove_pontuacao_mas_mantem_palavras():
    assert normalize_ptbr("olá, tudo bem? sim!") == "olá tudo bem sim"


def test_normalize_vazio_e_none():
    assert normalize_ptbr("") == ""
    assert normalize_ptbr(None) == ""  # fonte pode ter transcrição nula


def test_normalize_numeros_e_hifen():
    # dígitos preservados (palavra), hífen vira separador
    assert normalize_ptbr("caso-limite 2024") == "caso limite 2024"


def test_sources_tem_fleurs_e_mls_com_campos():
    for src in ("fleurs", "mls"):
        assert src in SOURCES
        cfg = SOURCES[src]
        assert {"repo", "path", "splits", "text_col"} <= set(cfg)
        # o datamodule do icefall usa train/dev/test
        assert set(cfg["splits"]) == {"train", "dev", "test"}


def test_sources_path_tem_placeholder_split():
    for src in SOURCES.values():
        assert "{split}" in src["path"]  # o download formata por split
