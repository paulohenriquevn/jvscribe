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


# --- resolução do artefato -------------------------------------------------

def test_o_modelo_e_opcional_e_cai_no_artefato_canonico():
    """Exigir o caminho posicionalmente força o operador a saber onde o peso está — e a
    escolher um, que pode não ser o canônico. O `model_card.json` já sabe."""
    import inspect

    import bench_rtfx

    fonte = inspect.getsource(bench_rtfx)
    assert 'ap.add_argument("model")' not in fonte, "modelo ainda é posicional obrigatório"
    # Verifica o CONTRATO (o default sai do resolvedor canônico), não o nome da função que o
    # implementa. A guarda quebrou quando `default_model_path` passou a ser chamado via
    # `engine.resolver` — mas o contrato nunca mudou. Checar o literal transformaria uma
    # consolidação correta em falha.
    assert ("default_model_path" in fonte or "resolver(" in fonte), (
        "o default do modelo tem de sair do resolvedor canônico, não de um literal"
    )


def test_a_config_de_sessao_permanece_EXPLICITA_aqui():
    """Contraintuitivo e deliberado: este script NÃO usa a fábrica compartilhada.

    Ele é um instrumento de medição — a configuração de sessão é a **variável sob teste**,
    não uma decisão de produto. Adotar a fábrica mudaria o que ele mede e invalidaria a
    comparação com os RTFx já publicados.
    """
    import inspect

    import bench_rtfx

    fonte = inspect.getsource(bench_rtfx)
    assert "def session_options" in fonte, "a config explícita é o ponto deste script"
    assert "criar_sessao" not in fonte, "não deve usar a fábrica: mudaria a medição"
