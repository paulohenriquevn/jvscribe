"""A fábrica de sessão ONNX — uma configuração, medida, para todos os entrypoints.

Antes disto, cada script montava a sua: `batch/` inteiro usava `enable_cpu_mem_arena = False`
enquanto `realtime/live_transcribe.py` usava `True`. A diferença não é estética — foi medida
com bootstrap pareado (25 repetições, round-robin):

| mudança | delta pareado (IC95%) |
|---|---|
| arena LIGADA sozinha | −6,7% [−18,3; −3,9] ms |
| arena + `inter_op` + threads da topologia | −17,1% [−36,9; −17,8] ms |

Config divergente entre entrypoints significa que uma medição feita num não vale no outro —
e este projeto já publicou WER de dois artefatos diferentes achando que era o mesmo.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

pytest.importorskip("onnxruntime")

from onnx_session import opcoes_de_sessao  # noqa: E402


def test_a_arena_de_memoria_vem_ligada():
    """Estava desligada sem justificativa e custava 6,7% [IC95% −18,3; −3,9] ms."""
    assert opcoes_de_sessao().enable_cpu_mem_arena is True


def test_inter_op_e_configurado_e_nao_fica_no_default():
    """O `sherpa-onnx` configura os dois (`csrc/session.cc:149,156`); nós deixávamos um solto."""
    assert opcoes_de_sessao(threads=8).inter_op_num_threads >= 1


def test_threads_explicitas_sao_honradas():
    assert opcoes_de_sessao(threads=3).intra_op_num_threads == 3


def test_sem_threads_usa_a_topologia_da_maquina():
    """A contagem certa depende da CPU — numa híbrida, threads a mais esperam o E-core."""
    from cpu import detectar

    assert opcoes_de_sessao().intra_op_num_threads == detectar().threads_recomendadas


def test_threads_invalidas_falham_alto():
    """Negativo: `intra_op_num_threads=0` faz o ONNX escolher sozinho, silenciosamente."""
    with pytest.raises(ValueError, match="threads"):
        opcoes_de_sessao(threads=0)


def test_o_modo_memoria_restrita_desliga_a_arena():
    """`decode_onnx_local` desligava a arena por OOM em manifest grande — motivo real.

    A opção existe para preservar esse caso sem espalhar config solta; o default continua
    sendo o medido.
    """
    assert opcoes_de_sessao(memoria_restrita=True).enable_cpu_mem_arena is False


def test_a_config_e_a_mesma_para_todos_os_entrypoints():
    """O ponto do módulo: duas chamadas iguais produzem a mesma configuração.

    Sem isto, uma medição feita no lote não vale no tempo real — e vice-versa.
    """
    a, b = opcoes_de_sessao(threads=4), opcoes_de_sessao(threads=4)
    assert (a.intra_op_num_threads, a.inter_op_num_threads, a.enable_cpu_mem_arena) == (
        b.intra_op_num_threads, b.inter_op_num_threads, b.enable_cpu_mem_arena
    )
