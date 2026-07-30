# `training/` — as três pipelines do jvscribe

Tudo aqui roda **offline, em CPU**, sobre o modelo entregue em M5 (Zipformer-CTC 64M + fonema,
ONNX int8). Organizado por **pipeline**: cada pasta é um estágio nítido do ciclo de vida do modelo.

| Pipeline | Pasta | Problema que resolve | Entrada (rode isto) |
|---|---|---|---|
| **Finetune** | [`finetune/`](finetune/) | preparar corpus (CORAA/TAGARELA) e treinar/fine-tunar o modelo | `finetune/run_zipformer_ctc.sh` (treino) · `finetune/prep_coraa.py`, `finetune/prep_tagarela.py` (corpus) |
| **Batch** | [`batch/`](batch/) | transcrever pastas de áudio offline e medir WER em benchmark público | `batch/batch_transcribe.py <pasta_in> <pasta_out>` · `batch/eval_public_hf.py` (FLEURS) |
| **Realtime** | [`realtime/`](realtime/) | inferência ao vivo do microfone (demo; o runtime de produção é Rust em `crates/`) | `realtime/mic_transcribe.py` |
| **Eval** (transversal) | [`eval/`](eval/) | medir WER telefônico 8 kHz honesto (real-codec + call center real) | `eval/measure_realcodec.py`, `eval/measure_callcenter.py` |

Outras pastas: [`tests/`](tests/) (suíte pytest — rode `python3 -m pytest training/tests` de
qualquer diretório, graças a [`conftest.py`](conftest.py)), `results/` (registros medidos, com rótulo
de proveniência), `scripts/` (utilitários de análise WER/CER), `smoke/` (cluster M4 de smoke —
registro histórico, ver `smoke/README.md`).

## Convenções

- **Imports por nome dentro de uma pipeline.** Módulos que se importam vivem na mesma pasta
  (ex.: `batch/eval_public_hf.py` importa `batch_transcribe`). O `conftest.py` expõe cada pipeline ao
  `sys.path` para os testes; rodando um script standalone, o diretório dele já entra no path.
- **Nada de script solto na raiz.** Um teste-guarda (`tests/test_pipeline_layout.py`) falha se algum
  `.py`/`.sh` aparecer solto na raiz de `training/` ou se um módulo importar por nome outro de pipeline
  diferente (quebraria standalone).
- **Deps de canal telefônico** (`telephone_channel`, `codec_pool`) vivem em `scripts/corpus/` (nível
  repo) — os scripts de `eval/` as acessam via `sys.path`.

Estrutura decidida em `knowledge-base/plans/repo-faang-reorg-plan.md` (package-by-feature, ADR D1).
