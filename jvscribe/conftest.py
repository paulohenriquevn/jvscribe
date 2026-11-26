"""Expõe os módulos das pipelines ao `sys.path` para que os testes os importem por nome.

Estrutura (uma árvore só desde 2026-07-30 — antes havia `scripts/` e `jvscribe/tools/`,
duas pastas-lixeira com o mesmo nome genérico):

    common/    shared kernel — ctc, texto, métrica, artefato, sessão ONNX, motor de
               streaming e `audio/` (canal telefônico). ÚNICO destino legal de
               import cross-pipeline.
    corpus/    preparação de dados (manifests, pseudo-label, filtro de concordância)
    finetune/  treino — patches do icefall + preparo do que vai para a GPU
    batch/     transcrição offline
    realtime/  captura dual + app ao vivo
    eval/      harness de medição de WER
    bench/     benchmark e calibração de runtime      (era parte de tools/)
    probes/    experimentos de pesquisa               (era parte de tools/)
    audit/     auditoria de integridade de corpus     (era parte de tools/)

`common/` é o único destino permitido para import cross-pipeline — a guarda
`tests/test_pipeline_layout.py` verifica isso.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).parent
for _pipe in ('common', 'corpus', 'finetune', 'batch', 'realtime', 'eval', 'bench', 'probes', 'audit'):
    _p = str(_ROOT / _pipe)
    if _p not in sys.path:
        sys.path.insert(0, _p)
