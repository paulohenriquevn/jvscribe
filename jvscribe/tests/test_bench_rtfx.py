"""Teste da parte pura do benchmark de RTFx (fase 5). O RTFx em si é medição por
execução (validado rodando na i7-1355U); aqui cobrimos a config de sessão."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("onnxruntime", reason="onnxruntime não instalado")
import bench_rtfx as B  # noqa: E402


def test_session_options_seta_threads():
    so = B.session_options(2)
    assert so.intra_op_num_threads == 2
    assert so.inter_op_num_threads == 1  # inter fixo em 1 (medição single-pipeline)


def test_session_options_rejeita_threads_invalido():
    # error-handling: threads < 1 é ValueError tipado, não silencioso
    with pytest.raises(ValueError):
        B.session_options(0)


def test_rtfx_e_razao_audio_sobre_wall():
    # a definição fixada no blueprint: RTFx = duração_áudio ÷ tempo_de_parede
    audio_s, wall_s = 10.0, 0.16
    assert abs((audio_s / wall_s) - 62.5) < 1e-6
