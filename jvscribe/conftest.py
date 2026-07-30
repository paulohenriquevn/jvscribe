"""Expõe os módulos das pipelines ao `sys.path` para que os testes os importem por nome.

Estrutura (uma árvore só desde 2026-07-30 — antes havia `scripts/` e `jvscribe/tools/`,
duas pastas-lixeira com o mesmo nome genérico):

    common/    shared kernel — ctc, texto, artefato de modelo
    corpus/    preparação de dados (era jvscribe/corpus)
    finetune/  treino
    batch/     transcrição offline
    realtime/  captura dual + streaming
    eval/      medição de WER e baselines
    tools/     one-offs de análise (era jvscribe/tools)

`common/` é o único destino permitido para import cross-pipeline — a guarda
`tests/test_pipeline_layout.py` verifica isso.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).parent
for _pipe in ("common", "corpus", "finetune", "batch", "realtime", "eval", "tools"):
    _p = str(_ROOT / _pipe)
    if _p not in sys.path:
        sys.path.insert(0, _p)
