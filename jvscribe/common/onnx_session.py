"""Uma configuração de sessão ONNX, medida, para todos os entrypoints.

Antes disto cada script montava a sua: `batch/` inteiro usava `enable_cpu_mem_arena = False`
enquanto `realtime/live_transcribe.py` usava `True`. A diferença foi medida com bootstrap
pareado (25 repetições, round-robin — a carga entra igual nos candidatos):

| mudança | delta pareado (IC95%) |
|---|---|
| arena LIGADA sozinha | **−6,7%** [−18,3; −3,9] ms |
| arena + `inter_op` + threads da topologia | **−17,1%** [−36,9; −17,8] ms |
| `graph_optimization_level = BASIC` | **+6,6%** [+0,2; +20,8] ms — **piora** |

A arena estava desligada sem justificativa registrada. O `inter_op` nem era configurado — o
`sherpa-onnx`, runtime CPU de referência, seta os dois
([`csrc/session.cc:149,156`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/session.cc#L149)).

Config divergente entre entrypoints significa que uma medição feita num não vale no outro.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpu import detectar  # noqa: E402


def opcoes_de_sessao(threads: int | None = None, *, memoria_restrita: bool = False):
    """`SessionOptions` com a configuração medida.

    `threads=None` deixa a topologia decidir — numa CPU híbrida, threads a mais gastam
    instruções esperando o E-core em barreira (medido: 90,9 G contra 30,9 G para o mesmo
    trabalho, com o cache miss idêntico).

    `memoria_restrita=True` desliga a arena. Existe porque `decode_onnx_local` a desligava por
    OOM em manifest grande — motivo real, que merece uma opção em vez de config solta.
    """
    import onnxruntime as ort

    if threads is not None and threads < 1:
        raise ValueError(
            f"threads tem de ser >= 1, veio {threads}. Zero faz o ONNX Runtime escolher "
            "sozinho, em silêncio — e a contagem certa depende da topologia da CPU."
        )

    n = threads if threads is not None else detectar().threads_recomendadas
    so = ort.SessionOptions()
    so.intra_op_num_threads = n
    so.inter_op_num_threads = max(1, n // 2)
    so.enable_cpu_mem_arena = not memoria_restrita
    return so


def criar_sessao(modelo: str, threads: int | None = None, *, memoria_restrita: bool = False):
    """Sessão de inferência em CPU com a configuração acima."""
    import onnxruntime as ort

    return ort.InferenceSession(
        modelo,
        opcoes_de_sessao(threads, memoria_restrita=memoria_restrita),
        providers=["CPUExecutionProvider"],
    )
