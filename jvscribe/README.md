# `jvscribe/` — as pipelines

Tudo aqui roda **offline, em CPU**, sobre o modelo entregue: Zipformer-CTC 64M com cabeça de
fonema, ONNX int8 — WER 15,99% em FLEURS pt_br. Organizado por **pipeline**: cada pasta é um
estágio nítido do ciclo de vida do modelo.

| Pipeline | Pasta | Problema que resolve | Rode isto |
|---|---|---|---|
| **Batch** | [`batch/`](batch/) | transcrever pastas de áudio e medir WER em benchmark público | `batch/batch_transcribe.py --input-dir <in> --out-dir <out>` |
| **Realtime** | [`realtime/`](realtime/) | transcrever os **dois lados** de uma ligação ao vivo, com rótulo de falante | `realtime/live_transcribe.py --duracao 60` |
| **Finetune** | [`finetune/`](finetune/) | preparar corpus (CORAA/TAGARELA) e treinar/fine-tunar | `finetune/run_zipformer_ctc.sh` · `finetune/prep_coraa.py` |
| **Corpus** | [`corpus/`](corpus/) | pseudo-labeling, filtro por concordância, augmentação telefônica | `corpus/run_pipeline.py` |
| **Eval** | [`eval/`](eval/) | WER telefônico 8 kHz honesto (real-codec + call center real) | `eval/measure_realcodec.py`, `eval/measure_callcenter.py` |

| Transversal | Pasta | Papel |
|---|---|---|
| **Shared kernel** | [`common/`](common/) | o que **não** pode divergir entre pipelines: resolução de artefato, colapso CTC, normalização, topologia de CPU, estatística |
| **Ferramentas** | [`tools/`](tools/) | medição e diagnóstico — calibração, benchmark, soak, comparação de modelos |
| **Testes** | [`tests/`](tests/) | `python3 -m pytest jvscribe/tests` de qualquer diretório, graças ao [`conftest.py`](conftest.py) |
| **Resultados** | [`results/`](results/) | medições com hipótese, evidência e limitações separadas |

## Ferramentas de medição

| ferramenta | responde |
|---|---|
| [`bench/calibrate.py`](bench/calibrate.py) | qual janela e quantas threads nesta máquina — **rode ao trocar de CPU** |
| [`bench/runtime_bench.py`](bench/runtime_bench.py) | qual configuração de sessão ONNX é melhor, com bootstrap pareado |
| [`bench/stress_test.py`](bench/stress_test.py) | o RTFx do minuto 30 é o do minuto 1? (RNF-04) |
| [`eval/compare_models.py`](eval/compare_models.py) | qual de dois modelos é melhor, com IC |
| [`bench/finetune_smoke.py`](bench/finetune_smoke.py) | este checkpoint carrega, codifica PT-BR e treina? |

## Convenções

**O `model_card.json` decide qual peso roda — nunca o nome do arquivo.**
[`common/artifact.py`](common/artifact.py) é o **único** resolvedor, e todos os entrypoints o
consomem. Dois pesos coabitaram o diretório canônico com WER 15,99% e 17,32%, e a ordem
alfabética selecionava o segundo: nada falhava, a transcrição só ficava pior. A variável de
ambiente é `JVSCRIBE_MODEL_DIR` (a antiga `MACAW_MODEL_DIR` ainda funciona, com aviso).

**Imports por nome dentro de uma pipeline.** Módulos que se importam vivem na mesma pasta. O
`conftest.py` expõe cada pipeline ao `sys.path` para os testes; rodando standalone, o diretório
do próprio script já entra no path — e os scripts fazem o `sys.path.insert` explícito para
`common/`, porque sem ele quebram fora do pytest.

**`common/` é o único destino de import cross-pipeline.** Sem ele, a regra "nenhum import
cross-pipeline" empurrava para a cópia: o colapso CTC acabou replicado 7× e a normalização 5×,
com semânticas incompatíveis.

**Nada de script solto na raiz.** [`tests/test_pipeline_layout.py`](tests/test_pipeline_layout.py)
falha se um `.py`/`.sh` aparecer solto, se um módulo importar por nome outro de pipeline
diferente, ou se um entrypoint documentado deixar de rodar standalone.

## O que os testes guardam

A suíte tem **287 testes**, e boa parte existe por um defeito que passou:

| guarda | defeito que a originou |
|---|---|
| `test_pipeline_layout.py` | um import que só resolvia sob pytest — a suíte inteira passava e o script quebrava em produção |
| `test_model_dir_contract.py` | renomear o artefato quebrou o tempo real enquanto o lote seguia funcionando, porque cada script resolvia o modelo por conta própria |
| `test_streaming_features.py` | o cache de fbank divergindo em silêncio, trocando CPU por WER |
| `test_stress_invariants.py` | estado do motor crescendo sem teto numa ligação longa |
| `test_readme_links.py` | 5 de 5 links do README apontando para arquivos removidos |
| `test_wiki_okf.py` | documentação sem guarda apodrece |

## Onde está o resto

| assunto | onde |
|---|---|
| Como o modelo e o motor funcionam | [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) |
| Calibrar ao trocar de CPU | [`../docs/CALIBRATION.md`](../docs/CALIBRATION.md) |
| Base de conhecimento (OKF) | [`../wiki/index.md`](../wiki/index.md) |
| Retomar o treino | `models/current/finetune/README.md` |

> O runtime de inferência em Rust foi **removido** em 2026-07-30 — não por performance (a
> comparação justa deu Python 6,7× contra Rust 6,9×, indistinguíveis), mas por foco de time.
> Ver [`../wiki/decisoes/0004-remocao-do-runtime-rust.md`](../wiki/decisoes/0004-remocao-do-runtime-rust.md).
