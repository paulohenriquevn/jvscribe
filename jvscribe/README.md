# `jvscribe/` — as pipelines

Tudo aqui roda **offline, em CPU**, sobre o modelo entregue: Zipformer-CTC 64M com cabeça de
fonema, ONNX int8 — WER 15,99% em FLEURS pt_br. Organizado por **pipeline**: cada pasta é um
estágio nítido do ciclo de vida do modelo.

| Pipeline | Pasta | Problema que resolve | Rode isto |
|---|---|---|---|
| **Batch** | [`batch/`](batch/) | transcrever pastas de áudio e medir WER em benchmark público | `batch/batch_transcribe.py --input-dir <in> --out-dir <out>` |
| **Realtime** | [`realtime/`](realtime/) | transcrever os **dois lados** de uma ligação ao vivo, com rótulo de falante | `realtime/live_transcribe.py --duracao 60` |
| **Finetune** | [`finetune/`](finetune/) | preparar corpus (CORAA/TAGARELA) e treinar/fine-tunar | `finetune/run_zipformer_ctc.sh` · `finetune/prep_coraa.py` |
| **Corpus** | [`corpus/`](corpus/) | pseudo-labeling, filtro por concordância, manifests Lhotse | `corpus/run_pipeline.py` |
| **Eval** | [`eval/`](eval/) | WER honesto — telefônico 8 kHz, call center real, benchmark público | `eval/measure_realcodec.py`, `eval/measure_callcenter.py` |
| **Bench** | [`bench/`](bench/) | quanto custa rodar isto **nesta** máquina, e se aguenta | `bench/calibrate.py`, `bench/stress_test.py` |
| **Probes** | [`probes/`](probes/) | hipóteses de pesquisa — resultado NULO vale tanto quanto o positivo | `probes/blank_penalty_probe.py` |
| **Audit** | [`audit/`](audit/) | integridade do dado: vazamento de locutor, ruído de pseudo-rótulo | `audit/coraa_speaker_overlap.py` |

| Transversal | Pasta | Papel |
|---|---|---|
| **Shared kernel** | [`common/`](common/) | o que **não** pode divergir entre pipelines — e o **único** destino legal de import cross-pipeline |
| **Testes** | [`tests/`](tests/) | `python3 -m pytest jvscribe/tests` de qualquer diretório, graças ao [`conftest.py`](conftest.py) |

### Dentro do kernel

| módulo | domínio |
|---|---|
| `artifact` | resolve o artefato canônico **e** verifica/gera o `model_card.json` |
| `engine` | a sequência de carga — resolver → **validar o par** → sessão → vocabulário |
| `ctc` | colapso greedy |
| `text` | as duas réguas de normalização PT-BR, nomeadas pelo contrato |
| `metrics` | edit distance, parse de recogs, bootstrap **pareado de WER**, gravação que recusa sobrescrever evidência |
| `stats` | comparação pareada de medições **escalares** (latência) — vizinho, não gêmeo de `metrics` |
| `cpu` | o que a máquina tem, o que cabe nela, e **se ela está ociosa o bastante para medir** (`LIMIAR_LOAD`) |
| `onnx_session` | a configuração de sessão medida |
| `streaming` | motor de decode incremental (janela + LocalAgreement-2) |
| `report` | ambiente de template dos relatórios, com `StrictUndefined` |
| `audio/` | canal telefônico — é **sinal**, não corpus |

A regra: **cross-pipeline só a partir de `common/`.** Duas guardas, complementares:
[`tests/test_pipeline_layout.py`](tests/test_pipeline_layout.py) cuida do **layout** (nada solto
na raiz, sem basename duplicado, entrypoint roda standalone) e
[`tests/test_dominios.py`](tests/test_dominios.py) das **invariantes de desenho** — a que enumera
as nove pipelines, a que exige um caminho de import por símbolo do kernel, e as que impedem
constante de domínio ou sequência de carga duplicadas. Hoje há **zero** violações.

## Ferramentas de medição

| ferramenta | responde |
|---|---|
| [`bench/calibrate.py`](bench/calibrate.py) | qual janela e quantas threads nesta máquina — **rode ao trocar de CPU** |
| [`bench/runtime_bench.py`](bench/runtime_bench.py) | qual configuração de sessão ONNX é melhor, com bootstrap pareado |
| [`bench/stress_test.py`](bench/stress_test.py) | o RTFx do minuto 30 é o do minuto 1? (RNF-04) |
| [`eval/compare_models.py`](eval/compare_models.py) | qual de dois modelos é melhor, com IC |
| [`bench/finetune_smoke.py`](bench/finetune_smoke.py) | este checkpoint carrega, codifica PT-BR e treina? — **em CPU**, sem GPU |

O `finetune_smoke` precisa de um clone do icefall e de [`finetune/k2stub/`](finetune/k2stub/): o
`k2` instalado costuma ter ABI de outra build do PyTorch, e o `scaling.py` do icefall o importa
**só** para a ativação Swoosh. O stub a reimplementa em PyTorch puro, com as fórmulas extraídas
do próprio `scaling.py` — uma ativação parecida não falharia, apenas produziria uma loss sobre
outra rede. Qualquer outro nome de `k2` resolve (o icefall os usa em anotações) mas **levanta ao
ser usado**.

`[MEDIDO]` 2026-07-31 sobre `avg-124k-112k.pt`: `faltando=0`, CTC loss **0,86** contra **21,96**
de um modelo aleatório no mesmo lote, e 8 passos de Adam levando a loss de **0,861 a 0,159**. O
caso negativo também foi exercitado — contra o `.corrupt.pt` guardado ao lado, o script sai com
erro de domínio.

## Convenções

**O `model_card.json` decide qual peso roda — nunca o nome do arquivo.**
[`common/artifact.py`](common/artifact.py) é o **único** resolvedor, e todos os entrypoints o
consomem. Dois pesos coabitaram o diretório canônico com WER 15,99% e 17,32%, e a ordem
alfabética selecionava o segundo: nada falhava, a transcrição só ficava pior. A variável de
ambiente é `JVSCRIBE_MODEL_DIR` (a antiga `MACAW_MODEL_DIR` ainda funciona, com aviso).

Como CLI, `artifact.py` **verifica por padrão** e só escreve com `--write`. O card guarda
`model_sha256` e `vocab_fingerprint` justamente para denunciar um peso trocado; enquanto
regravava por padrão, rodá-lo — a coisa natural a fazer — recomputava os dois a partir do disco
e abençoava o peso novo. A ferramenta que detecta adulteração a lavava.

**Medição publicada não é sobrescrita por acidente.** `common/metrics.escrever_relatorio` recusa
substituir um relatório existente, e cada corrida do pipeline de corpus grava em
`wiki/medicoes/dados-brutos/` com o nome derivado da **configuração que a define** — `--n 200` e
`--n 5` são experimentos diferentes e deixam de competir por um arquivo. A **mesma** configuração
ainda colide, de propósito: re-medir é ato explícito (`--force`), não efeito colateral.

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

A suíte tem **501 testes**, e boa parte existe por um defeito que passou:

| guarda | defeito que a originou |
|---|---|
| `test_pipeline_layout.py` | um import que só resolvia sob pytest — a suíte inteira passava e o script quebrava em produção |
| `test_dominios.py` | `SR = 16000` em sete arquivos, a régua de WER errada sobrevivendo por ter dois caminhos de import, a sequência de carga remontada em treze entrypoints — com a **validação** presente em só quatro |
| `test_model_dir_contract.py` | renomear o artefato quebrou o tempo real enquanto o lote seguia funcionando, porque cada script resolvia o modelo por conta própria |
| `test_audit_vazamento.py` | os detectores de **vazamento treino/teste** não tinham teste nenhum — e um falso negativo ali não faz nada falhar, só deixa o WER publicado subir |
| `test_entrypoints_argparse.py` | três entrypoints liam `sys.argv` na mão: pedir `--help` respondia `ValueError: invalid literal for int()`, de onde ninguém deduz a interface |
| `test_k2stub_swoosh.py` | um stub de ativação com a fórmula ligeiramente errada não falha — só produz uma loss sobre outra rede |
| `test_relatorio_baseline.py` | o rótulo `[MEDIDO]` sumia da tabela **renderizada** (5 células para 4 colunas; o GFM ignora a excedente) — invisível no fonte |
| `test_relatorio_ao_vivo.py` | a tabela de vereditos estampava ❌ na mesma corrida em que a prosa declarava a medição indeterminada |
| `test_composicao_do_erro.py` | `max(subs, 1)` fabricava denominador: com zero substituições saía "0,0% atacável" sob rótulo `[MEDIDO]` |
| `test_streaming_features.py` | o cache de fbank divergindo em silêncio, trocando CPU por WER |
| `test_stress_invariants.py` | estado do motor crescendo sem teto numa ligação longa |
| `test_erros_nao_engolidos.py` | `except Exception` engolindo defeito de programação junto com a falha esperada |
| `test_readme_links.py` | 5 de 5 links do README apontando para arquivos removidos |
| `test_wiki_okf.py` | documentação sem guarda apodrece |

⚠️ **Uma guarda que checa texto reprova o conserto do que ela vigia.** Aconteceu quatro vezes
nesta base: guardas exigiam os literais `"IC95"`, `"getloadavg"`, `"WER ="` e um limiar copiado
entre arquivos, e cada uma falhou quando o defeito correspondente foi corrigido. Ao escrever uma
guarda, asserte a **intenção** — o mesmo objeto, o comportamento observável — não a string.

## Onde está o resto

| assunto | onde |
|---|---|
| Como o modelo e o motor funcionam | [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) |
| Calibrar ao trocar de CPU | [`../docs/CALIBRATION.md`](../docs/CALIBRATION.md) |
| Base de conhecimento (OKF) | [`../wiki/index.md`](../wiki/index.md) |
| Retomar o treino | [`../wiki/treino/retomar-o-treino.md`](../wiki/treino/retomar-o-treino.md) |

> Os patchers do icefall ancoram em trechos literais do upstream e param de casar a partir de
> `693d84a` (2024-10-21, Consistency-Regularized CTC). A revisão testada é **`f84270c`** —
> registrada em `finetune/prep_phoneme_head.ICEFALL_REV_TESTADO`, e a mensagem de erro dá o
> comando de saída. Sem o pino, a falha aparecia só ao preparar o treino: numa GPU alugada, com
> a instância já faturando.

> O runtime de inferência em Rust foi **removido** em 2026-07-30 — não por performance (a
> comparação justa deu Python 6,7× contra Rust 6,9×, indistinguíveis), mas por foco de time.
> Ver [`../wiki/decisoes/0004-remocao-do-runtime-rust.md`](../wiki/decisoes/0004-remocao-do-runtime-rust.md).
