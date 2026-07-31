# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

> **Nota sobre referências.** A Regra 6 exige que toda entrada cite o ticket/issue/PR
> de origem. O repositório ainda não está sob controle de versão nem tem tracker
> configurado — as entradas abaixo referenciam os artefatos em disco que as
> originaram. As referências `(#N)` passam a ser obrigatórias assim que o tracker
> existir; nenhum número foi inventado retroativamente.

## [Unreleased]

### Fixed
- **Um teste rápido apagava uma medição publicada.** `eval/baseline_fleurs_ptbr.py` gravava num
  caminho fixo dentro de `wiki/medicoes/`; rodá-lo com `n=2` durante o live test **substituiu o
  baseline real de M1** (12 utterances, 3 modelos) por uma corrida de duas. Só o git salvou.
  `common/metrics.escrever_relatorio` agora recusa sobrescrever; `JVSCRIBE_REPORT` redireciona e
  `JVSCRIBE_REPORT_FORCE=1` autoriza deliberadamente. Mesmo tratamento em `baseline_minds14.py`
  (que ainda apontava para `jvscribe/results/`, removida) e `corpus/run_pipeline.py`.
- **`corpus/run_pipeline.py` tinha o mesmo defeito destrutivo e ficou de fora da correção
  acima.** O commit anterior afirmou que ele recebera o mesmo tratamento; recebeu só o
  redirecionamento por `JVSCRIBE_REPORT`, não a recusa — a gravação continuava `write_text`
  direto. Consequência: `--n 5` sobrescrevia em silêncio uma corrida publicada de `--n 200`.
  Agora recusa, e ao recusar **imprime o relatório** em vez de descartar N transcrições com dois
  whisper. Verificado nos três caminhos: recusa com md5 do publicado inalterado, grava em destino
  novo, e `FORCE=1` sobrescreve.

### Fixed
- **O relatório de corrida do pipeline de corpus se contradizia sobre a própria configuração.**
  O caveat H-1 é prosa **condicional** — só vale quando a corrida se desvia do par de
  transcritores que o ADR-3 especifica (`small`+`medium`). Escrito como f-string, era emitido
  sempre: rodar exatamente o par do ADR produzia *"esta run usou `small`+`medium`, não o
  `small`+`medium` do ADR-3"*, e seguia analisando `base`, que não participou. O documento de
  evidência negava a configuração que a própria corrida usou. Corrigido com regressão primeiro
  (`tests/test_corpus_relatorio.py`, RED antes do fix).

### Changed
- **O corpo do relatório sai do código para um template** (`corpus/templates/*.md.j2`, Jinja2).
  A motivação não é estética: f-string com prosa condicional **esconde a condição** — nada no
  código dizia "esta frase só vale se o par for outro". Em template a condição é `{% if %}`,
  visível e revisável, e a prosa dos caveats passa a ser editável sem tocar em Python.
  `write_report` cai de 59 para 40 linhas e passa a calcular contexto, não a montar texto.
  `StrictUndefined` ligado de propósito: no default do Jinja uma variável com nome errado
  renderiza **vazio**, o que num documento de evidência é um número que some sem ninguém notar.
  `jinja2` promovido de transitivo a declarado em `requirements-eval.txt`.
- **O artefato de uma corrida do pipeline de corpus passa a ser nomeado pela configuração que a
  define** (`corpus/run_pipeline.py`). O destino era fixo — `wiki/medicoes/m3-cer-distribution.md`
  — e isso somava dois defeitos: corridas **incomparáveis** disputavam um arquivo (`--n 200`
  contra `--n 5`), e o script escrevia no lugar da **conclusão curada por humano**. Agora cada
  corrida grava em `wiki/medicoes/dados-brutos/` como `m3-cer-n{N}-keep{K}-{a}+{b}.md`, seguindo
  a convenção que já existia lá (`small-idle.json`, `medium-load.json` — nomear pela condição).
  O corolário é o ponto: a **mesma** configuração continua colidindo de propósito, e recusar é a
  resposta certa — repetir um experimento idêntico é ato explícito (`--force`). Caminho ancorado
  no repositório em vez de relativo ao CWD; `--out` e `--force` substituem as variáveis de
  ambiente neste script (os dois baselines as mantêm — lá o artefato é conclusão única, não
  evidência por corrida). Invariante guardada por `tests/test_corpus_run_path.py`.
- **Quatro scripts falhavam com traceback cru da biblioteca** em vez de erro que diz o que
  buscar (`error-handling.md` § 2): `measure_callcenter`, `make_callcenter_cuts`,
  `coraa_speaker_overlap`, `tagarela_coraa_leak_check`.
- **`audit/tagarela_noise_audit.py` tinha interface posicional não documentada** na ordem
  `[amostra] [manifesto]`, parseada em nível de módulo — importar o arquivo já lia `sys.argv`, e
  passar o caminho primeiro dava `ValueError: invalid literal for int()`. Agora `argparse`.
- **`realtime/live_transcribe.py` emitia veredito de RNF sem registrar a carga da máquina** —
  marcou RNF-02 ❌ com load 11,8. Mesma classe já corrigida em `bench/stress_test.py`. O
  relatório agora declara `INDETERMINADO` acima do limiar e aponta o que continua válido.

### Added
- **`docs/LIVE-TEST.md`** — os 37 entrypoints executados de verdade, com argumentos reais.
  Mapeia: testado sim/não · funcional ou não · utilidade real ou ruído. A prova mais forte é o
  `live_transcribe` transcrevendo fala ao vivo pelos dois canais — nenhum teste unitário
  demonstra isso.

### Fixed
- **Nove entrypoints carregavam modelo e vocabulário sem validar se o par combina.** É a
  proteção declarada fechada na revisão anterior, e ela existia em apenas **4 dos 13** lugares
  que carregam o motor. As duas gerações do artefato têm 500 tokens emitíveis e **492 dos 500
  ids mapeiam tokens diferentes**: o par errado transcreve português **plausível e errado**,
  sem erro nenhum.

  | | antes | depois |
  |---|---|---|
  | Entrypoints que validam o par | 4/13 | **8/8** |
  | Implementações do parser de `tokens.txt` | 6 | **1** |
  | Sequência de carga remontada à mão | 13 | **0** |

  Afetados: `bench/bench_rtfx`, `bench/calibrate`, `bench/runtime_bench`, `bench/stress_test`,
  `eval/measure_callcenter`, `probes/blank_penalty_probe`, `probes/tta_feature_align_probe`,
  `realtime/mic_transcribe`.

  **A causa foi fragmentação, não esquecimento**: a sequência `resolver → validar → sessão →
  vocabulário` estava replicada em 13 entrypoints, então a validação só existia onde alguém
  lembrou. A contagem de `def main()` foi o que revelou — 37 entrypoints, com `--model` e
  `--tokens` declarados à mão em 8 deles.

  ⚠️ **E a guarda que deveria ter pego isso enumerava 4 caminhos à mão.** Terceira vez nesta
  sessão que uma lista escrita à mão esconde justamente o que deveria vigiar. Agora descobre
  por AST.

### Added
- **`common/engine.py` — a sequência de carga do motor, uma vez.** `Motor.carregar` faz a
  sequência completa; `resolver` só resolve e valida, para `bench_rtfx` e `runtime_bench`,
  onde a configuração de sessão **é** a variável sob teste e a sessão não pode vir da fábrica.
  Validar não é opcional; montar a sessão à mão, quando justificado, é.
- Duas guardas em `tests/test_dominios.py`: a sequência de carga não pode ser remontada à mão,
  e existe **um só** parser de `tokens.txt`. As 6 implementações anteriores eram equivalentes
  `[MEDIDO]` — o que é o perigo, não o alívio: equivalentes hoje, nada garante amanhã, e só a
  do kernel recusa vocabulário vazio (que decodifica para string vazia em silêncio).

### Changed
- **Reorganização por domínio — o sistema tinha 7 pipelines para 15 domínios.** A divisão por
  pastas não era a divisão por domínio, e a medição mostrou o custo: **5 violações** da regra
  "cross-pipeline apenas a partir de `common/`", **3 símbolos** alcançáveis por dois caminhos
  de import, e duas pastas-lixeira (`tools/` com 7 domínios, `common/` com 5).

  | | antes | depois |
  |---|---|---|
  | Violações de fronteira | 5 | **0** |
  | Pastas com ≥ 4 domínios | 2 | **0** |
  | Símbolo por 2 caminhos de import | 3 | **0** |
  | Arquivos-fragmento **sem razão** | 4 | **0** |
  | Constante de domínio duplicada (`SR = 16000`) | 7 | **1** |

  > ⚠️ Correção: uma versão anterior desta entrada dizia "arquivos < 55 LoC: 4 → 0". Continuam
  > **quatro** (`common/ctc.py`, `finetune/patch_ctc_decode.py` e os dois CLIs finos de
  > `eval/`) — o que mudou é que todos têm razão declarada. O fragmento sem razão era
  > `text.py`, uma fachada de 47 linhas.
  | Pipelines | 7 | 9 — mais, e cada uma com **um** domínio |

  - `tools/` **dissolvida** em `bench/` (custo de rodar), `probes/` (hipótese de pesquisa) e
    `audit/` (integridade do dado); os 4 harness de medição foram para `eval/`.
  - Canal telefônico `corpus/` → **`common/audio/`** — é sinal, não corpus, e três pipelines
    o consumiam furando a fronteira.
  - `realtime/streaming.py` → `common/` (o soak precisa do motor para medir);
    `batch/bench_rtfx.py` → `bench/`.
  - Fusões de domínio partido: `text` + `text_normalize_ptbr` → **`text`**;
    `wer_core` + `bootstrap_wer_ci` + `cer_from_recogs` → **`metrics`**;
    `cpu_topology` + `calibracao` → **`cpu`**; `make_model_card` → **`artifact`**.

  ⚠️ **Uma fusão foi CANCELADA pela medição.** O mapa que eu mesmo escrevi afirmava que
  `bootstrap_wer_ci` e `stats` "fazem a mesma coisa". Medido no mesmo par de utterances:
  razão de somas dá **4,76 p.p.**, média de diferenças pareadas dá **26,25 p.p.** Não se faz
  média de WERs por utterance. Fundir teria mudado em silêncio todo delta publicado. Os dois
  módulos ficam vizinhos e separados, com o motivo escrito no topo de `metrics.py`.

  Nenhum número mudou: equivalência provada antes de cada fusão (3.000 strings para a régua de
  texto; 4.000 pares para `word_edit_distance` × `jiwer`). Suíte 391 → 391.

- **A guarda de fronteira só vigiava 4 das 7 pipelines** — `corpus` e `tools` ficavam de fora
  sem motivo documentado, e foi por isso que as 5 violações passaram. Agora enumera as nove.

### Added
- `docs/FRAGMENTACAO.md` — o mapa domínio × arquivo com o método, o resultado e as duas
  armadilhas de método que ele registrou.
- **`tests/test_dominios.py` — as quatro invariantes de desenho viram teste.** Reorganizar é
  barato; manter reorganizado não é. Cada guarda corresponde a um defeito que existiu:
  cross-pipeline só a partir do kernel · um símbolo, um caminho de import · toda pipeline
  declara o domínio que a une · nenhuma constante de domínio duplicada.
  Ao ser escrita, a guarda **imediatamente achou dois defeitos novos**: `BLANK = 0` declarado
  em 5 arquivos, e quatro pipelines sem `__init__.py` que dissesse o que as une.

### Fixed
- **`runtime_bench.py` documentava um método de decisão que não era o implementado.** O
  docstring dizia "reporta mediana e IQR; o veredito sai quando o IQR não se sobrepõe ao do
  baseline" — mas o veredito vem de bootstrap **pareado** com IC95%. O método real é mais
  forte, porém numa ferramenta cujo propósito É rigor de método, descrever o errado faria
  alguém citar a técnica errada num artefato de decisão. A função `_iqr`, que sustentava a
  descrição antiga, tinha zero chamadores e foi removida.
- **`calibrate.py` não distinguia "não sei" de "máquina ociosa".** `_carga_media` devolvia
  `-1.0` como sentinela de falha, e esse `-1.0` **passava** no `if carga > 1.0` do chamador:
  numa plataforma sem `getloadavg` o calibrate nunca avisaria sobre carga. Valor mágico para
  sinalizar falha viola `error-handling.md` § 2 — agora devolve `None` e o chamador decide.
  O parâmetro `base`, nunca usado (o único chamador passava `0`), saiu junto.
- **27 imports mortos removidos**, em boa parte órfãos deixados pela revisão de código
  anterior ao remover as linhas de `sys.path` dos testes.

### Notes
- **Auditoria de código morto (`/loop-deadcode-audit`)**: 665 símbolos cruzados contra 2.914
  referências; **zero implementações órfãs**. Os 373 símbolos sem referência de entrada
  explicam-se integralmente — 357 são testes coletados pelo pytest, 10 são dunders, 3 são
  passados por valor, 1 é `@property`, 1 é protocolo do Lhotse. **Cobertura de inspeção 100%**
  (113 arquivos: 109 `.py` + 4 `.sh`). Os shells não têm ferramenta de dead-code, então a
  cobertura foi fechada com análise de alcance manual — nenhum script órfão, nenhuma
  referência quebrada. `deadcode-output/` é trilha local, gitignorada como `code-review-output/`.

### Added
- **RNF-04 exercitado pela primeira vez — soak de 30 min** (`wiki/medicoes/m6-soak-30min-rnf04.md`).
  Nenhuma corrida do projeto tinha chegado a 30 minutos; `RNF-04`/`RNF-05` eram `[DESCONHECIDO]`
  por ausência de dado. A corrida **não** fecha o RNF-04 (a máquina hospeda a sessão do usuário
  e o load ficou entre 5 e 14 — `asr-evidence-discipline.md` § 5), mas fecha duas perguntas que
  estavam abertas junto e **não dependem de tempo de relógio**: o motor **não vaza memória** em
  30 min (RSS em platô) e o **teto de estado do motor segura** (`commit = 64` constante nos 30
  minutos, em ambos os canais — antes havia só teste de unidade).
- **WER do FLEURS re-medido com a régua canônica: 16,14% → 15,83%** `[MEDIDO]`
  (`wiki/medicoes/benchmarks-publicos.md`, n=100, 2.552 palavras-ref).

### Fixed
- **`stress_test.py` emitia veredito de RNF sem olhar a carga.** A corrida de 30 min produziu
  "RNF-04: FALHA" com o load entre 5 e 14 — um veredito autoritativo tirado de dado que a
  própria disciplina do projeto rejeita, e a ferramenta que emite o veredito era a única cega
  (o `calibrate.py` avisa acima de 1,0 desde sempre). Agora registra a carga por janela, marca
  `INDETERMINADO (carga)` acima do limiar e devolve **exit 2** — indeterminado não é reprovado,
  para que um CI ocupado não vire "regressão de produto".

### Added
- **Fail-fast do par (modelo, vocabulário) — DoD#2 de M9, que estava aberto.** Nenhum dos 4
  entrypoints validava o `tokens.txt` contra o modelo. É o defeito mais perigoso do projeto
  porque a saída é português **plausível**: sem exceção, sem caractere estranho, só um WER pior
  inexplicável. `common/artifact.py::validar_par_modelo_vocabulario` compara pelo
  `vocab_fingerprint` do `model_card.json` — **nunca pela contagem**, já que as duas gerações
  têm 500 tokens e 492 dos 500 ids divergem. Cobre também o `--tokens` passado à mão, que é
  onde o erro é mais provável. Provado contra o caso real: rejeita o vocabulário M4
  (`4e145aad`) sobre o modelo M5 (`9fcb45e4`). Guarda de fiação impede que um entrypoint novo
  esqueça de chamar.

### Fixed
- **`eval_runtime_wer.py` e `analyze_error_composition.py` mediam WER com a régua de TREINO.**
  Ela **preserva** acento, então cada acento errado contava como palavra errada. `[MEDIDO]`:
  numa frase em que só o acento difere, a régua de treino dá **62,5%** de WER onde a canônica
  dá **0%**. ⚠️ **O WER de runtime publicado (29,92%) precisa ser re-medido** — não é
  comparável com nenhum número medido pela canônica. A régua de treino continua correta e
  agora exclusiva de `prep_icefall.py`, que prepara o corpus.
- **WER de call center passou a usar a régua única do projeto.** `measure_callcenter.py` tinha
  normalização própria que **preservava acento**, enquanto a régua canônica remove — o mesmo
  defeito já corrigido em `eval_public_hf.py`. ⚠️ **O WER de call center publicado precisa ser
  re-medido**: o número anterior não é comparável com os demais recortes. A limpeza específica
  do domínio (máscaras de PII, marcador `⚠️`) foi preservada, agora compondo com a canônica.
- **Dois probes voltaram a rodar por linha de comando.** `tta_feature_align_probe.py` e
  `blank_penalty_probe.py` apontavam para `jvscribe/scripts/`, pasta extinta na reorganização —
  quebravam em `ModuleNotFoundError` no único modo de uso que têm. Uma entrada morta em
  `sys.path` não levanta erro, então a suíte seguia verde (o `conftest.py` cobria o import).
- **`tta_feature_align_probe.py` levantava `NameError`** ao imprimir o resultado, depois de todo
  o decode das 3 condições — a parte cara do probe.
- **`measure_realcodec.py` não depende mais de `/workspace` hardcoded.** `codec_pool` e
  `telephone_channel` são resolvidos no próprio repositório; a recipe do icefall virou
  `--icefall-root` / `ICEFALL_ROOT`, com erro que diz o que configurar.
- **`baseline_fleurs_ptbr.py` estava quebrado** — apontava para `jvscribe/scripts/telephone_augment.sh`,
  pasta extinta, e a constante `REPO` na verdade resolvia para `jvscribe/`. É o módulo que
  produziu o baseline de M1.
- **`run_zipformer_ctc.sh` engolia falha de decode** com `|| true`: um decode quebrado dava
  script com exit 0 e nenhum WER — silêncio num script de MEDIÇÃO. Agora cada falha aparece,
  as duas variantes de averaging seguem independentes, e ausência total de `%WER` é erro.
- **`prep_tagarela.py` contava bug de programação como "áudio corrompido"** (`except Exception`
  sobre `sf.read`), descartando dado do corpus de TREINO em silêncio. Estreitado para
  `sf.LibsndfileError`; perda acima de 5% do total agora falha alto (shard truncado no
  download seguiria montando corpus com o que sobrou).
- **`ICEFALL_ROOT` configurável** em `run_ft_codec.sh` e `run_ft_freeze.sh`, mesma convenção de
  `measure_realcodec.py`.
- **Fallback de codec deixou de engolir bug real.** `except Exception` em `codec_pool.py` trocava
  o codec aplicado ao **dado de treino** em silêncio quando qualquer defeito ocorria; agora só a
  família "backend indisponível" (`ImportError`/`RuntimeError`/`OSError`) cai para ffmpeg, e
  avisando.

### Added
- **`tests/test_sys_path_vivo.py`** — nenhuma entrada de `sys.path` pode apontar para diretório
  inexistente, e os probes standalone são verificados **em subprocesso** (dentro do pytest eles
  herdariam o path do `conftest.py` e passariam mesmo quebrados).
- Testes de que o fallback de codec propaga defeito de programação e avisa ao cair para ffmpeg.

### Removed
- **`jvscribe/results/` removida.** Eram 933 MB, dos quais **927 MB não eram resultado**:
  6 pesos de modelo da geração M4 e 407 MB de áudio FLEURS. O conhecimento real eram 20
  documentos, e 6 deles ainda **não estavam na wiki**.

### Changed
- **Cada coisa foi para um lugar honesto**, em vez de tudo ficar sob "results":
  | o que era | onde está |
  |---|---|
  | 6 pesos ONNX da geração M4 (vocab `4e145aad`) | `models/m4-legacy-onnx/` — peso não se apaga |
  | 1.039 wavs do FLEURS + `fleurs_one.f32` | `data/eval/fleurs/` (gitignored, público) |
  | `tokens.txt`, `model_card.json`, `fleurs_one.txt` (fixtures versionados) | `jvscribe/tests/fixtures/` |
  | 20 documentos de medição | `wiki/medicoes/` |
  | soak JSONs + dumps de eval por utterance | `wiki/medicoes/dados-brutos/` |
- **6 medições migradas para a wiki** que ainda não estavam lá: a ablação da cabeça de fonema
  no medium, o piloto FLEURS, o smoke de M4, a primeira medição de tempo real, o int8 vs fp32
  do runtime Rust, e o **soak que decidiu o tamanho do modelo** (evidência do ADR 0003).
- `wiki/medicoes/dados-brutos/` preserva a evidência recomputável — os soak JSONs por condição
  (ocioso vs sob carga) e os dumps de eval por utterance.
- CI e 8 arquivos repontados: `.github/workflows/ci.yml` extrai para `models/ci-artifact/`;
  `test_make_model_card` lê o golden de `tests/fixtures/tokens-m4.txt`.


### Added
- **`jvscribe/common/onnx_session.py`** — uma configuração de sessão ONNX, medida, para todos
  os entrypoints. Havia **quatro divergentes**: `batch/` inteiro com a arena DESLIGADA
  enquanto `realtime/` a usava ligada. Medido com bootstrap pareado: arena ligada rende −6,7%
  [IC95% −18,3; −3,9] ms, e a config completa −17,1%. 7 testes.
  `bench_rtfx` e `runtime_bench` mantêm config explícita **de propósito** — neles a
  configuração é a variável sob teste, e adotá-la invalidaria comparação com RTFx publicado.
- Testes para `decode_onnx_local` (5) e `eval_public_hf` (7) — **nenhum dos dois tinha teste**.

### Fixed
- **`eval_public_hf.py` estava QUEBRADO**: apontava para `m5_avg.int8.onnx`, renomeado na
  reorganização. Nenhum teste cobria o arquivo, então a suíte seguia verde.
- **O WER publicado saiu de uma régua diferente do resto do projeto.** `eval_public_hf` tinha
  `norm()` própria, que **preservava acentos**, enquanto `normalize_for_wer_compare` os remove.
  Os **16,14%** de `results/public-benchmarks.md` vieram dela; os **15,99%** medidos no mesmo
  subconjunto vieram da régua canônica. A diferença **não era ruído de amostra** — era régua
  diferente, e os dois números nunca foram comparáveis.
- **`decode_onnx_local.py` reimplementava o colapso CTC** (`load_tokens`, `ids_to_text`,
  `greedy_ctc`). Delegado a `common/ctc.py`; a guarda que comparava cópias virou uma que
  **proíbe a cópia voltar**.
- **`eval_public_hf.py` não tinha guarda `__main__`** — importar o módulo baixava o FLEURS e
  rodava inferência. Era o único dos 4 entrypoints sem ela.
- Defaults de modelo relativos ao `cwd` em `decode_onnx_local` e modelo posicional obrigatório
  em `bench_rtfx` — os dois passam a resolver pelo `model_card.json`.
- `tempfile.mkdtemp` sem cleanup e `int(sys.argv[1])` sem validação em `eval_public_hf`.
- Três imports de `onnxruntime` que ficaram mortos após a delegação à fábrica.

### Notes
- Nove dos onze achados eram **a mesma classe**: conhecimento que deveria estar no shared
  kernel, reimplementado localmente — três cópias do colapso CTC, duas réguas de normalização,
  quatro configs de sessão. Nenhum derrubava um teste: **passavam na suíte e quebravam em
  produção**.
- ⚠️ `wiki/medicoes/benchmarks-publicos.md` precisa ser **re-medido** com a régua canônica.


### Changed
- **`jvscribe/README.md` reescrito** — estava induzindo a erro: dizia que "o runtime de produção
  é Rust em `crates/`" (removido em 2026-07-30), citava pastas que não existem (`scripts/`,
  `smoke/`), omitia `common/`, `tools/` e `corpus/`, e trazia a sintaxe errada do
  `batch_transcribe` (posicional, quando é `--input-dir`/`--out-dir`).
  Agora traz as 5 pipelines com o comando certo, as ferramentas de medição, e a tabela
  "o que os testes guardam" — cada guarda ao lado do defeito que a originou.

### Fixed
- **`corpus/run_pipeline.py` quebrava standalone** com `ModuleNotFoundError: No module named
  'text_normalize_ptbr'`. O `sys.path.insert` de `agreement_filter.py` apontava para `..`, de
  onde o módulo saiu na migração do shared kernel (M9/T3.1) — o insert ficou obsoleto e só o
  `conftest.py` mantinha o import de pé. Passava na suíte inteira e falhava em produção.
  É o mesmo defeito de M9/T3.1, num diretório que a guarda não cobria: `corpus/` não estava na
  lista de `test_entrypoints_de_pipeline_rodam_standalone`. Agora está.


### Removed
- **`train_phoneme_small.log` (55 MB) removido** — o GitHub avisou no push que passa do limite
  recomendado de 50 MB. Eram **480.955 linhas**, das quais **49,2% eram `FutureWarning`
  repetidos** do torch e apenas **1.410 (0,29%) carregavam métrica**.
  O sinal foi extraído para `train_phoneme_small.metrics.log` (356 KB) antes de descartar o
  resto — não é apagar evidência, é separar sinal de ruído. Nenhuma conclusão dependia das
  479.545 linhas restantes: o que sustenta o número da ablação são os `recogs-*`, dos quais
  WER e CER são recomputáveis.
  Diretório: 56 MB → 1,3 MB. Documentado em
  `wiki/medicoes/m4-cabeca-de-fonema-no-medium.md` (os `recogs-*` em
  `wiki/medicoes/dados-brutos/`).

### Added
- Regra no `.gitignore` para `train_*.log` — logs de treino brutos não são versionados; versione
  as métricas extraídas.

### Notes
- ⚠️ **A remoção não apaga o arquivo do histórico.** Todo clone continua baixando os 55 MB do
  commit que o introduziu. Apagar de verdade exige `git filter-repo` + force-push, que as
  regras do projeto proíbem em `develop`.


### Changed
- **Todas as menções a "macaw" passam a ser "jvscribe"** — 25 arquivos. Duas eram interface,
  não texto, e receberam tratamento próprio:
  - **`MACAW_MODEL_DIR` → `JVSCRIBE_MODEL_DIR`**, com o nome antigo **ainda funcionando** e
    emitindo `DeprecationWarning`. Renomear sem rede faria quem a tem exportada cair em
    silêncio para `models/current` — o mesmo modo de falha que já entregou o modelo errado
    aqui. A nova tem precedência, para a migração terminar. 4 testes.
  - **`macaw-model-card/1` → `jvscribe-model-card/1`** no `model_card.json`, com
    `SCHEMAS_ACEITOS` reconhecendo os dois na leitura: o schema mudou de **nome**, não de
    formato, e cards já gerados (inclusive o publicado) trazem o antigo. Card do artefato
    canônico regenerado e republicado no HuggingFace.

### Notes
- **Nomes de artefatos que EXISTIRAM não foram renomeados** — `crates/macaw-asr`,
  `macaw-cli`, `MACAW_MODEL`, `MACAW_THREADS`. São citações a um runtime Rust real, e
  reescrevê-las criaria caminho que nunca existiu — fabricação de evidência, que as regras do
  projeto tratam como hard cap. Ficam como registro histórico.

### Fixed
- **A própria varredura de renomeação quebrou três coisas em silêncio**, todas pegas pela
  suíte:
  - trocou `MACAW_MODEL_DIR` dentro dos **testes que existem para testar o nome antigo** — as
    duas variáveis viraram a mesma e o teste de precedência passou a comparar a variável
    consigo mesma;
  - trocou o **valor** de `VAR_MODEL_DIR_OBSOLETA`, fazendo a compatibilidade virar no-op;
  - invalidou silenciosamente duas edições minhas cujo padrão de busca continha o nome antigo.
  Os três pontos ganharam comentário `⚠️` explicando por que citam o nome antigo de propósito.
- **Dependência de ordem entre testes**: a primeira versão do aviso de obsolescência guardava
  "já avisei" num global de módulo — passava isolado e falhava na suíte. Trocado por
  `warnings.warn(DeprecationWarning)`, que deduplica sem estado mutável nosso.


### Added
- **`wiki/` — o conhecimento do projeto em Open Knowledge Format (OKF v0.1).** 43 documentos:
  markdown com frontmatter YAML, um conceito por arquivo, links markdown, `index.md` por
  diretório e `log.md` na raiz. Organizado por `modelo/`, `motor/`, `treino/`, `otimizacao/`,
  `medicoes/`, `decisoes/`, `disciplina/` e `referencias/`.
  Guardado por 8 testes (`test_wiki_okf.py`): frontmatter, campo `type` obrigatório, links
  internos, `index.md` por diretório, vocabulário de campos da spec, e nenhum conceito sem
  corpo — porque documentação sem guarda apodrece em silêncio.

### Removed
- **`knowledge-base/` removida — 52 MB, 5.265 arquivos.** O conhecimento real eram **15
  documentos**; os outros 5.250 eram o clone do `sherpa-onnx`.
  - Os 15 viraram conceitos OKF em `wiki/`, com a verificação de que cada um sobreviveu.
  - O clone virou **permalinks fixados no commit `116a44e72c5b`** — as citações `[FONTE-REPO]`
    em `docs/ARCHITECTURE.md` e nos results passaram a apontar para o GitHub, o que as torna
    verificáveis por **qualquer pessoa**, não só por quem tem o clone. Contexto em
    `wiki/referencias/sherpa-onnx.md`.

### Fixed
- **Três arquivos ESCREVIAM dentro de `knowledge-base/`** — `baseline_fleurs_ptbr.py`,
  `baseline_minds14.py` e `run_pipeline.py` agora escrevem em `wiki/medicoes/`.
- **Quatro docstrings citavam arquivos já removidos antes** (`plans/m5-scale-model-wer-plan.md`,
  `blueprints/m3-corpus-blueprint.md`, `plans/repo-faang-reorg-plan.md`, `audits/`) —
  apontadas para a wiki.
- Links do README, ROADMAP e CLAUDE.md para `knowledge-base/` → `wiki/`. O
  `test_readme_links.py` pegou a quebra no ato.


### Changed
- **`CLAUDE.md` reescrito com foco em arquitetura, otimização, treino e disciplina de
  medição.** Ele é carregado em toda sessão, então cada linha precisa se pagar. O anterior
  ainda anunciava M4 como estado corrente e o WER de 27,49% (uma geração atrás), e não
  registrava nada do que foi aprendido depois. Agora traz:
  - o entregável real (**15,99% WER**, publicado e reproduzido a partir do HF);
  - os três fatos que a intuição erra — **o modelo não é streaming** (10,6× de retrabalho por
    hop), o matmul é só 24,4% do custo, e o par (modelo, vocabulário) não é intercambiável;
  - a tabela de otimizações com o que **não se aplica** e por quê (FLToP mede contra beam
    search; blank-skip acelera joiner de transducer) — com as fontes;
  - o que é **portável** entre CPUs e o que precisa ser recalibrado;
  - as armadilhas de treino que já custaram run inteiro (LR de cabeça fresca, fp16, codec-aug)
    e as três alavancas contra o overfitting, com o checkpoint averaging promovido de
    `[ESTIMATIVA]` a `[MEDIDO]`;
  - **as regras de medição que este projeto pagou para aprender** — nunca concluir de corrida
    única (3 erros documentados), benchmark de componente não transfere, máquina sob carga não
    mede, harness ao vivo valida mas não compara.


### Added
- **`docs/CALIBRATION.md` — runbook de calibração ao trocar de CPU.** Separa o que é portável
  (cache de fbank, dreno da captura, backpressure, teto de estado — são correções algorítmicas)
  do que **precisa ser remedido** (contagem de threads e janela de decode, que saem da
  topologia e da ocupação de CPU). Traz o procedimento em 5 passos, como interpretar cada
  sintoma, e o que a calibração **não** resolve.
- **`jvscribe/tools/calibrate.py`** — mede a curva `janela → custo` na máquina-alvo, calcula a
  ocupação com N canais e emite a maior janela que cabe no orçamento, mais o comando pronto.
  Avisa quando o load average passa de 1,0, porque sob carga a medição não separa.
- **`jvscribe/common/calibracao.py`** — o núcleo determinístico (`ocupacao`, `janela_maxima`),
  com 12 testes: máquina mais rápida permite janela maior, mais lenta devolve `None` em vez de
  chutar, curva não-monotônica não quebra a escolha, hop zero falha alto.

### Changed
- **A janela de 6 s deixa de ser constante e passa a ser calibrada.** Com `intra=2` + arena
  ligada, o custo caiu de 172 ms para **112 ms** na janela de 6 s; a de 10 s, que antes pedia
  **104,9%** da CPU, agora cabe em **63,5%**. Janela maior é acurácia de graça (mais contexto
  para o LocalAgreement-2 confirmar), então o runbook manda recalibrar em vez de herdar o 6.


### Added
- **`jvscribe/common/cpu_topology.py`** — detecta CPU híbrida (P-cores vs E-cores) pelo sysfs
  e recomenda contagem de threads. Nesta máquina: 12 lógicos, rápidos `0-3` a 5000 MHz,
  recomenda `intra=2`. 14 testes, incluindo CPU homogênea, boost por núcleo (que **não** é
  hibridez), sysfs ausente e nunca recomendar zero threads.
- **`jvscribe/common/stats.py`** — `comparar_pareado()` com IC95% por bootstrap. Devolve
  `melhor=None` quando o intervalo cruza zero e **recusa** amostras < 3. O `runtime_bench`
  passou a consumi-lo em vez da própria cópia. 9 testes, incluindo "configurações idênticas
  nunca produzem vencedor".
- `wiki/medicoes/m6-topologia-de-cpu.md` — a rodada completa, com o `perf` liberado.

### Changed
- **`intra_op_num_threads` passa a vir da topologia** (2 nesta máquina, era 6). Em inferência
  isolada é `[MEDIDO]`: 70,2 ms contra 94,0 ms, com mecanismo confirmado por `perf` — IPC 1,87
  vs 1,22 e **30,9 G contra 90,9 G de instruções** para o mesmo trabalho (spin-wait em
  barreira; o cache miss é idêntico, ~26%, então não é limite de memória).
  No nível de **sistema** o ganho é `[DESCONHECIDO]` — ver Fixed. O default fica pelo argumento
  que não depende de velocidade: ocupar 2 dos 12 lógicos em vez de 6 deixa CPU para o
  softphone que o RNF-05 exige.

### Fixed
- **Fixar afinidade nos P-cores foi aplicado, medido e REVERTIDO.** Isolado dava 25% de ganho;
  no app ao vivo derrubou o RTFx de **4,60× para 2,33×**. Causa verificada:
  `sched_setaffinity` **é herdado pelos processos filhos**, então os `parec` da captura
  passavam a disputar os mesmos 2 P-cores com a inferência. No soak sem subprocessos a
  afinidade é neutra (6,49× vs 6,88×). Ganho zero, modo de falha real → removida.
  Teste de regressão falha se alguém reintroduzir qualquer função que mute afinidade.

### Notes
- **O instrumento não separa o que se queria comparar.** Harness ao vivo, config idêntica,
  quatro corridas: 3,51× · 2,90× · 2,82× · 2,50×. Determinístico, 3 repetições por config:
  intra=2 → 4,20/3,95/6,31, intra=6 → 2,92/4,54/5,03 — **indistinguíveis**. Com a máquina em
  load 3–4 não há separação para contagem de threads no nível de sistema. Um soak limpo exige
  a máquina ociosa.
- RNF-04 e RNF-05 seguem **não exercitados**: nenhuma corrida chegou a 30 min nem teve
  softphone ativo.


### Changed
- **README raiz atualizado** — estava parado em 2026-07-30, antes da renomeação, da publicação
  e das medições de M6. Corrigido:
  - **M9 marcado como pendente quando o ROADMAP diz `[x]`**; M6 passa a "em medição" com link
    para a evidência.
  - **O número anunciado era 27,49%, o entregável de M4** — uma geração atrás. Agora traz o
    modelo M5 publicado: WER **15,99%** / CER 7,30% / RTFx 40,0×, com a condição de medição
    ao lado e o link para a verificação feita a partir do download do HuggingFace.
  - **Faltava "como rodar"** — um README sem quickstart obriga o leitor a garimpar. Adicionadas
    as invocações de lote e de tempo real, a dependência de `pulseaudio-utils` e a tabela de
    ferramentas de medição.
  - Link para `docs/ARCHITECTURE.md` e para `wiki/medicoes/`.
  - Declarados os limites: 8 kHz e call center seguem `[DESCONHECIDO]`, e o modelo **não é
    streaming**.
- `test_pipeline_layout.py` passa a exercitar também os entrypoints que o README documenta
  (`live_transcribe`, `runtime_bench`, `stress_test`, `compare_models`, `finetune_smoke`).
  Comando documentado que não roda é a mesma classe de falha que link quebrado.


### Added
- **`docs/ARCHITECTURE.md` — arquitetura do modelo e do motor de inferência.** Todo número foi
  extraído do artefato ou do código, não da memória: estrutura via `onnx.load` e `state_dict`;
  custo via profiler por operador. Cobre o grafo (subamostragem 4,1× medida → um frame de
  saída a cada ~41 ms), a distribuição de parâmetros por stack (o stack 3 concentra 48% do
  encoder), o contraste entre peso e custo (`encoder_embed` tem 1,0% dos parâmetros e 22,0%
  do custo), a ativação Swoosh expandida em elementwise pelo export, o pipeline de lote, o de
  tempo real com LocalAgreement-2, e o envelope operacional medido.
  Os fatores de downsampling foram confirmados **nos pesos** (`encoders.N.downsample.bias` com
  shapes 2/4/8/4/2 e `downsample_output.bias` 2), não assumidos do default do icefall.


### Added
- **Profile por operador do runtime** (`wiki/medicoes/m6-profile-por-operador.md`),
  usando o profiler embutido do ONNX Runtime — que estava disponível desde sempre e não vinha
  sendo usado. Ele mostra o que cronometrar blocos não mostra: `encoder` 75,6%,
  `encoder_embed` 22,0%, **`ctc_output` 0,3%**; e que o matmul quantizado é só 24,4% do custo,
  com mais de 40% em elementwise — `Log`/`Exp` com 84 nós cada em `/encoder_embed/conv/*`,
  que é a ativação Swoosh expandida pelo export em vez de fundida.
- `jvscribe/tools/runtime_bench.py` — varredura de configuração com **bootstrap pareado**.
  Sem pareamento, tudo dava inconclusivo; e uma varredura de corrida única chegou a reportar
  158,8 ms e 169,1 ms para configurações **idênticas** (ruído de 35 ms, maior que os efeitos).
- `jvscribe/tools/stress_test.py` — soak com o modelo real, medindo RTFx, p99, RSS e estado
  do motor minuto a minuto.
- `jvscribe/realtime/streaming.py::FeatureCache` — fbank incremental. A extração por pedaço
  só equivale à completa com offset **múltiplo do frame shift** e retendo 2 frames da borda
  direita; sem isso divergia em 6,57 (desalinhado) e 6,27 (último frame de cada pedaço),
  silenciosamente. 6 testes cobrem a equivalência.
- 8 testes de invariante de ligação longa (`test_stress_invariants.py`) e 3 de backpressure.

### Changed
- **Sessão ONNX seguindo o `sherpa-onnx`** (`csrc/session.cc:149,156`): arena de memória
  LIGADA e `inter_op` configurado. Medido com bootstrap pareado (25 reps, round-robin):
  **−17,1%** de tempo de inferência, IC95% [−36,9; −17,8] ms. A arena estava desligada sem
  justificativa e sozinha custava −6,7%. `graph_optimization_level=BASIC` **piora** (+6,6%).
- Ganho combinado (config + cache de fbank) em `StreamingCTC.update()`: **379,3 → 315,1 ms**,
  delta pareado −55,1 ms IC95% [−81,1; −30,2] → **−14,5%**.

### Fixed
- **O model card publicado afirmava que o modelo é causal. É falso.** Três fontes provam o
  contrário: o metadado do artefato diz `comment: "non-streaming zipformer2 CTC"`, o grafo
  ONNX não tem tensor de estado, e os scripts de treino nunca passam `--causal`. Corrigido e
  republicado em `paulohenriquevn/jvscribe`.
- **`committed` no `StreamingCTC` crescia sem teto** — 2.128 entradas em 3 min de soak
  (~28 mil numa ligação de 40 min) quando o motor só consulta a última. Limitado a 64.
- **O laço de tempo real não tinha backpressure**: ao ficar atrasado nunca recuperava — o
  atraso medido subiu de 392 ms para 18.798 ms e ficou lá. Agora descarta áudio antigo acima
  de um teto, preservando a cauda, e o descarte aparece no relatório.

### Notes
- **Duas otimizações do DoD do M6 não se aplicam a este pipeline**, com fonte:
  FLToP CTC (`arXiv:2510.09085`) mede 10,5% contra **beam search beam=1000** e o próprio paper
  diz que não vale para greedy argmax — nosso decode é greedy e custa 0,3%; blank
  layer-skipping (`arXiv:2305.11558`) acelera o **joiner do transducer**, e somos CTC puro.
  A alavanca de ordem de grandeza é treinar com `--causal 1`: medido, reprocessar 6 s custa
  121 ms contra 11 ms de processar só os 0,5 s novos — **10,6× de retrabalho por hop**.


### Added
- **`jvscribe/realtime/live_transcribe.py` — app de transcrição ao vivo dos dois canais.**
  Captura mic (ATENDENTE) e loopback (CLIENTE) em paralelo, transcreve com um motor
  `StreamingCTC` por canal e imprime o diálogo rotulado, medindo os critérios do `PRD.md § 6`
  em tempo real. Sem diarização por construção: no caso 1:1 o papel vem da origem do stream.
  Verificado ao vivo contra referência conhecida tocada nas caixas.
- `jvscribe/realtime/streaming.py` — motor de janela + LocalAgreement-2 extraído de
  `mic_transcribe.py`, que agora tem um segundo consumidor. Sem dependência de captura.
- `wiki/medicoes/m6-rnf-ao-vivo.md` — primeira medição de RNF sobre o pipeline
  completo, com a curva de custo de decode por janela e a varredura de configuração.

### Fixed
- **`DualCapture.read()` devolvia UM chunk por stream por chamada** enquanto o `parec` produz
  ~30/s por canal — o consumo era estruturalmente menor que a produção e o backlog crescia sem
  limite (medido: 101 → 227 chunks em 4,4 s). A app de tempo real reprovava RNF-02 e RNF-03
  por encanamento, e diagnosticar como "modelo lento" teria levado a otimizar a coisa errada.
  Agora drena a fila com teto **por stream** — o teto global da primeira tentativa deixava um
  canal cheio matar o outro de fome, o que na prática perderia metade da conversa.
  Backlog caiu de **100% para 2,5%** das amostras.

### Changed
- Defaults de `live_transcribe` passam a ser **medidos**: janela 6 s / hop 0,5 s. A janela de
  10 s custa 262 ms de decode e, com dois canais a cada 0,5 s, pede **104,9% da CPU** — satura
  por construção.


### Added
- **Modelo publicado em `paulohenriquevn/jvscribe`** (HuggingFace, privado): ONNX oficial,
  vocabulário, model card, alternativos e os artefatos de finetune (~3,0 GB). Excluídos os
  dados de avaliação (`testdata/`, 1,2 GB) e o `.pt` truncado — que permanece em disco.
- **`jvscribe/tools/finetune_smoke.py` — prova que o checkpoint publicado TREINA.**
  Três asserções sobre dados reais: `load_state_dict(faltando=0)`; CTC loss do checkpoint
  **25× menor** que a de um modelo aleatório de mesma arquitetura no mesmo lote (0,86 vs
  21,96 — um `.pt` corrompido produziria loss de aleatório); e loss caindo 85,4% em 10 passos
  com a norma do gradiente indo de 16,4 a 0,59.
  Fecha a lacuna deixada pela reconstrução do `avg-124k-112k.pt`, antes verificado só por
  "abre e tem o tamanho certo".
- `wiki/medicoes/reprodutibilidade.md` — hipóteses, evidência e limitações da
  verificação, incluindo o que ela **não** prova (não é treino; `k2` é stub; 8 kHz segue
  `[DESCONHECIDO]`).
- **Reprodutibilidade validada a partir do HuggingFace, não dos arquivos locais.** Download
  limpo de `paulohenriquevn/jvscribe`: `model_sha256` e `vocab_fingerprint` conferem com o
  card, inferência entrega **WER 15,99% / CER 7,30%** (idêntico ao declarado) a RTFx 43,4×, e
  o finetune sobre o `.pt` baixado desce a loss 80,9% em 8 passos.
  Achado no caminho: `hf download --include` com seis padrões buscou cinco arquivos e **omitiu
  o `model.int8.onnx` sem erro nem aviso** — registrado no documento como armadilha para quem
  reproduzir.


### Added
- **`jvscribe/common/artifact.py` — um resolvedor de artefato para todos os entrypoints.**
  `batch_transcribe`, `mic_transcribe` e os testes resolviam o modelo cada um por conta
  própria; defaults duplicados divergem. Agora todos leem `model_file` do `model_card.json`,
  com degradação para nomes conhecidos quando o card falta.
- Model card no padrão HuggingFace em `models/current/README.md` — YAML frontmatter com
  `model-index`, resultados medidos, arquitetura completa, limitações explícitas (8 kHz e
  call center **não medidos**) e licença `other` com a herança dos corpora declarada.

### Changed
- **Nomenclatura SOTA em `models/`.** `m5-final-medium-phoneme` →
  `jvscribe-ptbr-zipformer-ctc-64m` (produto-idioma-arquitetura-tamanho). O peso oficial passa
  a se chamar `model.int8.onnx`; os alternativos vão para `alternates/` com nomes que declaram
  a procedência (`ckpt124k.int8.onnx`, `ckpt124k.fp32.onnx`) em vez de escondê-la num sufixo.
  Em `finetune/`: `avg-124k-112k.pt`, `phoneme_targets.json`, `training.log`. A convenção
  `checkpoint-N.pt` do icefall foi mantida — é o padrão do framework.
  Verificado funcionalmente após a renomeação: WER 15,99% / CER 7,30% / RTFx 40,0×, idêntico.

### Fixed
- **A renomeação transformou um smoke de ponta a ponta em `skip` silencioso.**
  `test_batch_transcribe.py` tinha o caminho do modelo absoluto e literal; ao renomear o
  artefato o teste passou a pular com "modelo ausente" e a suíte seguiu verde — cobertura
  perdida sem nenhum sinal. Agora resolve pelo kernel compartilhado. 204 testes, zero skips.
- **`mic_transcribe.py` carregava `m5_avg.int8.onnx` fixo no código** e quebrou na renomeação
  enquanto o lote continuou funcionando. Coberto por teste novo que exige que todos os
  entrypoints resolvam o MESMO artefato canônico.


### Added
- **`models/current/finetune/` — tudo para retomar o treino dos dois modelos M5, em um lugar só.**
  Renomeado de `backup/` (nome que não dizia para que servia) e completado com `tokens.txt` +
  dois READMEs: `models/README.md` (qual é o oficial e por quê) e
  `models/current/finetune/README.md` (comandos de retomada, as quatro flags
  de arquitetura obrigatórias, e as armadilhas já pagas — LR de cabeça fresca, fp16 colapsando,
  full-FT com codec-aug colapsando o greedy).

### Fixed
- **O `.pt` do modelo oficial estava corrompido — recuperado.** `avg_124_112.pt`, o checkpoint
  que gerou o `m5_avg.int8.onnx` (WER 15,99%), não abria: `PytorchStreamReader failed reading
  zip archive`. Tinha 80 MB onde 64M parâmetros em fp32 ocupam ~257 MB — truncado a ~31%,
  provavelmente por disco cheio na vast.ai durante o salvamento. Regenerado como a média dos
  `model` state dicts de `checkpoint-124000.pt` e `checkpoint-112000.pt`, ambos íntegros (735
  tensores cada, com `optimizer`/`scheduler`). O arquivo truncado foi **mantido** como
  `avg_124_112.CORROMPIDO.pt` — peso não se apaga.
  Limite honesto: a equivalência bit a bit com o original **não** foi verificada (o script de
  export ONNX rodava na instância remota). Rotulado `[ESTIMATIVA]` no README.


### Changed
- **O modelo oficial passou a ser `m5_avg.int8.onnx` — decidido por medição, não por nome.**
  Os dois pesos M5 que coabitam o artefato canônico foram medidos no mesmo conjunto
  (FLEURS pt_br test[0:100], 2.552 palavras, greedy CTC, máquina com load < 2):
  `model.int8.onnx` WER 17,32% / CER 7,39% contra `m5_avg.int8.onnx` WER **15,99%** / CER 7,30%.
  Bootstrap pareado de 5.000 reamostragens dá IC95% do delta em **[−2,25, −0,43] pp** — não
  cruza zero. O `model_card.json` foi regenerado apontando para o vencedor, com o WER medido e
  a condição da medição no campo `wer_source`.
  Confirma por medição o que o `CLAUDE.md` registrava como `[ESTIMATIVA]`: checkpoint averaging
  bate abaixo do melhor checkpoint individual.

### Fixed
- **`batch_transcribe.py` escolhia o peso pelo nome do arquivo e entregava o pior em silêncio.**
  Com `model.int8.onnx` e `m5_avg.int8.onnx` no mesmo diretório, a ordem literal de nomes
  selecionava o de WER 17,32% em vez do de 15,99% — sem erro, sem aviso, só transcrição
  mensuravelmente pior. O resolvedor agora lê `model_file` do `model_card.json` como autoridade
  e só cai para os nomes conhecidos quando o card está ausente ou ilegível. Mesma classe de
  falha que o M9 endereça: artefatos indistinguíveis por metadado superficial.
  Coberto por dois testes novos em `jvscribe/tests/test_model_dir_contract.py` (o caso feliz e
  o card apontando para peso inexistente).
- Cabeçalho `## [Unreleased]` duplicado neste arquivo.

### Removed
- **`models/` limpo: 8,1 GB → 4,0 GB.** Mantido apenas `m5-final-medium-phoneme`, o
  deliverable final de M5. Removidos `m0-borrowed` + `m0-borrowed-hf` (2,4 GB — o modelo
  emprestado que só o runtime Rust removido usava), `m4-final-medium-phoneme` (1,3 GB) e
  `m4-final-phoneme-small` (453 MB). Cada remoção foi precedida de verificação por hash: os
  pesos de `m4-*` têm duplicata em `models/m4-legacy-onnx/`.
  **Perda real registrada:** `m4-final-phoneme-small/model.fp32.onnx` (88 MB) era o único peso
  sem duplicata em outro lugar. `models/` é gitignored — não volta.
- Cópias byte-idênticas de `decode_onnx_local.py` e `mic_transcribe.py` que viviam dentro do
  diretório de modelo (achado da auditoria de system design).

### Fixed
- **O artefato canônico apontava para o modelo errado.** `models/current` resolvia para
  o diretório da geração M4 (hoje `models/m4-legacy-onnx/`), cujo `model.int8.onnx` NÃO é
  o M5. É exatamente o defeito que M9 foi construído para impedir, e estava ativo. Agora
  aponta para `m5-final-medium-phoneme`, com `model_card.json` gerado (fingerprint
  `9fcb45e4…`, 500 tokens emitíveis).

### Added
- `jvscribe/tools/compare_models.py` — compara dois modelos no mesmo conjunto com a mesma
  régua, reportando WER, CER e **intervalo de confiança por bootstrap**. Existe porque "qual
  modelo é melhor" foi decidido por nome mais de uma vez neste projeto ("final", "leve",
  "SOTA"), e nome não é evidência. Declara explicitamente quando os intervalos se sobrepõem —
  escolher pelo WER nesse caso seria escolher por ruído. 6 testes.

### Changed
- **`training/` renomeado para `jvscribe/`** — o topo do repositório passa a declarar o
  produto, e um nível abaixo declara as capacidades (`common`, `corpus`, `finetune`, `batch`,
  `realtime`, `eval`, `tools`, `tests`). O nome anterior **mentia**: `training/` continha
  transcrição em lote, tempo real e avaliação — treino era uma parte, não o todo.

  `src/` foi avaliado e **rejeitado**: o benefício real do src-layout é impedir import
  acidental antes de instalar, e isso exige `pyproject.toml`, que o projeto não tem. Adotá-lo
  agora custaria um nível a mais sem entregar o benefício, e trocaria um nome que mente por
  um que não diz nada.

  Custo real da mudança: **zero imports alterados** — eles são por nome, resolvidos pelo
  `conftest.py`. Só caminhos textuais mudaram.

- **Reorganização estrutural: uma árvore só, `scripts/` eliminado.** Conviviam duas pastas
  chamadas "scripts" — `scripts/` (raiz) e `jvscribe/scripts/` — o anti-pattern de
  pasta-lixeira: nome genérico não exige decisão de onde algo pertence, então acumula código
  sem relação. `scripts/` misturava setup de ambiente, ferramentas de avaliação, biblioteca de
  corpus e utilitário de texto.

  | De | Para | Por quê |
  |---|---|---|
  | `scripts/corpus/` | `jvscribe/corpus/` | biblioteca de preparação de dados |
  | `scripts/text_normalize_ptbr.py` | `jvscribe/common/` | é shared kernel |
  | `scripts/make_model_card.py` | `jvscribe/common/` | governança de artefato |
  | `scripts/{eval_wer,baseline_*,run_baseline}.py` | `jvscribe/eval/` | ferramentas de medição |
  | `jvscribe/scripts/` | `jvscribe/tools/` | one-offs de análise — o nome agora diz isso |
  | `scripts/tests/` | `jvscribe/tests/` | uma árvore de testes |
  | `scripts/requirements-*.txt` | raiz | são do repositório, não de um subdiretório |

  Dois testes travam a estrutura: `test_nao_existe_pasta_lixeira_chamada_scripts` (proíbe
  `scripts`/`utils`/`helpers`/`misc`/`lib`) e `test_cada_pipeline_declarada_existe` (impede
  o `conftest.py` divergir da realidade).

### Fixed
- `jvscribe/tests/test_codec_pool.py` importava `codec_pool` **sem configurar path** e passava
  só porque outro módulo poluía o `sys.path` antes dele — dependência de ordem de execução
  (`testing.md` § 6). A reorganização resolveu na raiz: `corpus/` agora é declarado no
  `conftest.py`.

### Removed
- **Runtime de inferência em Rust removido** (decisão do dono, 2026-07-30): 3 crates,
  4.042 LoC, 79 testes. `jvscribe` passa a ser **Python-only**. Arquivado e recuperável em
  `git switch -c rust-restore rust-runtime-archive-v0.8.0`. Racional completo em
  `knowledge-base/adrs/0004-remocao-do-runtime-rust.md`.
  **A decisão não foi por performance:** `[MEDIDO]` na mesma clip e pipeline, Python mediana
  6,7× e Rust mediana 6,9× — indistinguíveis. Foi por foco de time e colaboração de cientistas
  de dados.
- `scripts/{app,bench,test_report}.sh` — dependiam do binário Rust.

### Added
- `jvscribe/realtime/dual_capture.py` — captura dual mic + loopback com **seleção de source por
  stream**, a capacidade de produto que só existia no Rust (separa atendente de cliente numa
  ligação). Usa um `parec --device=<source>` por stream porque `sounddevice` **não expõe monitor
  sources** (verificado: 8 entradas, 0 monitores nesta máquina). 6 testes provam em execução
  real, incluindo captura simultânea dos dois streams e ausência de processo órfão.
- CI reescrito para Python-only, com `pulseaudio-utils` e relatório de skips.

### Fixed
- **Correção de método na própria reetiquetagem** (2026-07-30): eu afirmei que "o número real desta máquina é ~6–7×" e que RNF-01/07 não podia ser dado como verde. As medições foram tomadas com **load average 69,4 sobre 12 cores** — ~6× sobrecarregada, em parte pela própria sessão de agente. Isso caracteriza a carga, não a máquina. O estado correto de RNF-01/07 é **`a re-medir`**. Continua válida a comparação **relativa** Rust × Python, medida alternadamente sob a mesma carga.
- `wiki/medicoes/m6-tempo-real-primeira-medicao.md` **reetiquetado**: os RTFx de 41–90× ali
  registrados são medição de **componente** (só inferência) em máquina ociosa, e estavam sendo
  lidos como se descrevessem o pipeline. `[MEDIDO]` no pipeline completo, mesma máquina, o
  número é **~6–7×** contra o piso de 6× do RNF-07 — folga de ~10%, não de 7–15×, com execuções
  individuais **abaixo do piso** sob carga. O placar de RNF-01/07 do documento não pode ser
  lido como ✅ com folga até ser re-medido de ponta a ponta.
- `batch_transcribe.py` resolvia modelo e vocabulário por **nome fixo relativo ao cwd**, então
  quebrava assim que `models/current` apontava para um artefato com outro nome de arquivo —
  o operador canonizava e nada canonizava. Agora resolve pelo artefato canônico
  (`JVSCRIBE_MODEL_DIR` > `models/current` > cwd) e busca o `tokens.txt` **no mesmo diretório do
  modelo**, que é o que impede o par incoerente que M9 fechou.

### Changed
- Produto renomeado de "jvscribe" para **jvscribe** nos documentos vivos. Registros
  históricos (ADRs anteriores, `wiki/medicoes/*.md`, medições) **não** foram reescritos —
  documentam o que era verdade quando foram escritos.

### Added
- Teto de threads no runtime Rust (M6/R1): `AsrEngine::load` passa a chamar
  `with_intra_threads`, default 2, override por `MACAW_THREADS`. Antes o ONNX Runtime
  reivindicava todos os 12 cores lógicos desta máquina, contra um orçamento declarado de
  ≤ 2 P-cores (o produto divide a CPU com um softphone).

### Fixed
- **Medição de RTFx corrigida por método** (M6): a comparação que sugeria o runtime Rust
  lento era inválida — confrontava o RTFx do Rust (pipeline completo: fbank + inferência +
  decode) com o do `bench_rtfx.py` (só inferência). É a falácia § 3 #11 da
  `asr-evidence-discipline.md`. `[MEDIDO]` 2026-07-30, mesma clip de 17,76 s, mesmo pipeline,
  2 threads: **Python 5,7–8,0× (mediana 6,7)** vs **Rust 3,0–14,7× (mediana 6,9)** — os dois
  runtimes são indistinguíveis, e ambos ficam colados no piso de 6× do RNF-07 nesta máquina
  sob carga.

### Known issues
- Os RTFx de 41–90× registrados em `wiki/medicoes/m6-tempo-real-primeira-medicao.md` vêm de
  medição **de componente** em máquina ociosa. Sob pipeline completo e carga real, o número
  desta máquina é ~6–7×. O `m6-realtime-current-model.md` precisa ser reetiquetado.
- `models/current` (symlink de M9/T1.3) aponta para um diretório cujo modelo se chama
  `model.int8.onnx`, enquanto `batch_transcribe.py` tem default `m5_avg.int8.onnx`. Os dois
  artefatos usam nomes diferentes e a unificação não foi feita.

## [0.8.0] - 2026-07-30

### Known issues
- `test_slow_endpoint_does_not_block_metrics` é **flaky em ~10%** nesta máquina. `[MEDIDO]`:
  2 falhas em 8 execuções com o load do encoder de 2,3 GB, 0 em 8 sem ele, com ~1 GB de RAM
  livre. Mecanismo: sob pressão de memória o ONNX Runtime aborta em C++ e mata o processo de
  teste, o que aparece como `ConnectionReset` em `/metrics`. Duas correções reais no caminho
  (dois `.expect` que envenenavam o mutex do cache de engine) reduziram de ~33% para ~10%; o
  resíduo é ambiental. **Não foi mascarado** apontando o teste para um diretório sem modelo —
  isso removeria a lentidão que ele existe para medir. Fix apropriado (endpoint lento
  sintético) fica fora do escopo de M9.

> **Nota de versionamento.** A regra de derivação do `cycle-release.md` dispara MAJOR quando
> `§ Removed` não está vazio, o que daria v1.0.0. Desvio deliberado para MINOR: nenhuma API
> pública foi removida (verificado no diff — zero `-pub fn|struct|enum`); o `§ Removed` lista
> dumps de experimento, examples sem caller e uma dependência duplicada. Além disso, v1.0
> neste projeto tem gate próprio (`dogfood-golden-rule.md`: evidência de uso sustentado, que é
> o M8 ainda não feito). Cortar v1.0.0 aqui seria alegação falsa de maturidade.


### Added
- `scripts/make_model_card.py` e artefato canônico `models/current` (M9/T1.3): gera `model_card.json` com sha256 do modelo, fingerprint e contagem de tokens emitíveis. O fingerprint Python reproduz bit a bit o do Rust (teste de conformidade cross-language). `models/current` é **symlink** — nenhum peso é movido ou copiado. `eval_public_hf.py` deixa de usar caminho absoluto e honra `JVSCRIBE_MODEL_DIR`.
- `JVSCRIBE_MODEL_DIR` também no runtime Rust (M9): `app.rs::model_dir()` passa a honrar a variável, fechando o item do DoD "nos dois lados" — antes só o lado Python o cumpria.
- Validação de **identidade** de vocabulário contra o `model_card.json` (M9/T1.2b): `validate_against_model_card`, ligada no caller de produção. Complementa a checagem de cardinalidade, que pega o erro fácil — este pega o difícil: `[MEDIDO]`, os dois artefatos do repositório têm 500 tokens emitíveis **cada** e 492 dos 500 ids mapeiam tokens diferentes, então trocá-los produz transcrição integralmente errada sem nenhum erro de dimensão. Degrada para no-op quando não há card.
- Fail-fast de par (modelo, vocabulário) incoerente (M9/T1.2): `AsrEngine` lê a dimensão de saída do grafo na carga (sem inferência) e `transcribe` recusa vocabulário incompatível com `AsrError::VocabModelMismatch`, citando os dois números. Antes, apontar para o `tokens.txt` errado produzia transcrição silenciosamente errada.
- `Vocab::real_len()` e `Vocab::fingerprint()` (M9/T1.1): contagem de tokens emitíveis (excluindo símbolos de desambiguação `#N` do lexicon FST) e fingerprint SHA-256 de identidade do vocabulário. Medido nos dois artefatos reais: ambos com 500 tokens emitíveis (502 e 503 linhas) e fingerprints distintos — cardinalidade não os distingue, identidade sim.
- Restaurado `knowledge-base/references/_catalog.md` (fonte: `c7c67b9~1`, onde foi removido junto com o resto do knowledge-base) — catálogo dos 8 peers SOTA clonados em 2026-07-24, necessário como contrato de fonte para o ciclo DISCOVER de M9. Bootstrap autorizado via marcador `.references-bootstrap` conforme `hooks/boundary-check.sh`.
- Plano de M9 (SHIPPABLE 99,2/100, 32/32 critérios executáveis, zero hard caps) em `knowledge-base/plans/`. Medição durante o planejamento **corrigiu** o achado da auditoria: os dois artefatos têm 500 classes cada (a diferença 502/503 no tokens.txt são símbolos de desambiguação do FST), mas **492 dos 500 ids mapeiam tokens diferentes** — logo validar cardinalidade seria insuficiente e M9 valida identidade (fingerprint SHA-256). `/deps-audit`: zero CVEs em Rust e Python.
- Ciclo DISCOVER de M9 concluído: plano de pesquisa (SHIPPABLE 100/100) e blueprint (SHIPPABLE 99,4/100) em `knowledge-base/discoveries/`, com 8 questões respondidas por evidência `[FONTE-REPO]` do peer sherpa-onnx no SHA 116a44e7. Achado central: o padrão de validação vocabulário×modelo que M9 precisa já existe e é copiável (`offline-recognizer-canary-impl.h:246`).
- Roadmap amendado: adicionado M9 Governança de artefato e reprodutibilidade (`/roadmap-feature governanca-artefato-reprodutibilidade`) — fecha as lacunas de integridade encontradas na auditoria de system design de 2026-07-30 (artefato de modelo canônico, fail-fast de vocabulário, shared kernel do decode CTC, CI, licença). Depende de M5.
- Auditoria de system design (`/loop-system-design`, modo full): 51 achados em 14 módulos, 4 quality gates aprovados, relatório e plano de reorganização em `system-design-output/`.
- `CLAUDE.md` na raiz: guia de onboarding para o Claude Code — comandos de build/teste das duas metades (Rust e Python), camadas do workspace, as duas armadilhas que custaram tempo (as duas convenções de fbank que coexistem; o ONNX Runtime carregado por `dlopen`) e o aviso de que `PRD.md`/`ROADMAP.md`/`knowledge-base/` citados no código foram removidos em `c7c67b9`.
- Reorganização FAANG (fase 3): `jvscribe/README.md` mapeia as 3 pipelines (problema→entrada); refs de path atualizadas no paper (EN+PT-BR §10) e no `PRD.md`.
- Edição PT-BR do paper (`docs/paper/jvscribe-voice-cpu-asr.pt-br.md`): cada componente do modelo, do sistema e das decisões de método explicado no formato "Problema que resolve → Como resolve".
- Paper técnico/experience (`docs/paper/jvscribe-voice-cpu-asr.md`) — relato rigoroso e honesto de todo o percurso de pesquisa (seleção de arquitetura por medição, treino, e o case study do bug de config que simulou um limite fundamental). Guia "construa o seu" + checklist para praticantes. Cada número com rótulo de proveniência. Inclui 7 figuras Mermaid (arquitetura, system design, árvore de decisão do debug, gráficos de WER/RTFx) + versão HTML autocontida das figuras (`docs/paper/figuras.html`, `arquitetura.html`) que renderiza em qualquer navegador.
- Benchmark público reprodutível (`jvscribe/eval_public_hf.py`, `wiki/medicoes/benchmarks-publicos.md`): **16,14% WER** no FLEURS pt_br (fala lida banda-larga), RTFx 24,6x em batch (CPU). Confirma o modelo forte em áudio de boa qualidade; o gargalo telefônico é canal/dado. [MEDIDO]
- Transcrição em LOTE de pasta de áudios (`jvscribe/batch_transcribe.py`) — lê qualquer formato
  via ffmpeg → 16 kHz → VAD por silêncio → inferência ONNX **em batch** com decode paralelo.
  Saída: um .txt por áudio + transcripts.json com RTFx agregado. Medido: 9,2 min de áudio em
  11,5s = **47,8× RTFx** em CPU. 7 testes (incl. smoke ponta-a-ponta).

### Added
- `jvscribe/common/text.py` (M9/T3.2): as duas semânticas de normalização PT-BR com nomes que
  revelam o contrato — `normalize_for_wer_compare` (remove acento) e `normalize_train_target`
  (preserva). Medido: das 5 funções chamadas `normalize_ptbr`, há **2 semânticas** e 3 cópias
  byte-idênticas de uma delas. O defeito não era a duplicação, era o **nome compartilhado por
  comportamentos opostos** — enquanto durasse, comparar dois WERs do projeto pressupunha uma
  igualdade de régua que ninguém tinha verificado.
- `jvscribe/common/` — shared kernel das pipelines (M9/T3.1). `ctc.py` consolida o colapso CTC
  greedy que estava replicado em 5 arquivos. A consolidação só foi feita **depois de medir** a
  equivalência (`jvscribe/tests/test_ctc_equivalence.py`): o laço de colapso é idêntico entre
  as cópias; o que divergia era a detokenização — 4 usam `join + replace("▁"," ")` e
  `measure_realcodec` usa `sp.decode()`. As duas convenções ficaram como funções distintas e
  nomeadas, em vez de uma unificação cega que mudaria um número publicado.
- Guarda de layout mais forte (M9/T3.3): import cross-pipeline agora é permitido **apenas** a
  partir de `common/`, e a varredura passou a cobrir todo arquivo versionado — antes ela via
  só `jvscribe/`, e por isso não enxergava as cópias que escaparam para fora da árvore.
- CI com dois jobs (M9/T2.3): `test-model-free` (obrigatório, runner limpo, sem nenhum
  artefato de modelo) e `test-with-artifact` (condicional, roda os testes `#[ignore]`).
  Separar as camadas elimina o falso verde por **design** em vez de detectá-lo por relatório —
  padrão observado em sherpa-onnx, onde nenhum dos 22 `*-test.cc` toca modelo.
- `rust-toolchain.toml` fixando a toolchain (M9/T2.4).

### Fixed
- **`rust-version` do workspace estava errado** (M9/T2.4): declarava `1.75`, mas o projeto
  nunca buildou nessa versão — buildava com o rustc da máquina. Fixar a toolchain em 1.75
  quebrou o build na hora (`ort 2.0.0-rc.12` exige `edition2024`). O MSRV real, lido da
  própria dependência, é **1.88**; corrigido e verificado com a suíte completa.
- **Teste flaky em `capture_test`** (M9/T2.3): `[MEDIDO]` 2 falhas em 5 execuções (40%) em
  `test_capture_thread_terminates_cleanly_on_drop`. Causa: o teste de captura dupla soltava o
  lock de serialização **antes** de suas threads morrerem (elas só encerram na próxima leitura
  após o canal fechar, ~32 ms), deixando o contador global sujo para o teste seguinte.
  Corrigido com limpeza determinística; `[MEDIDO]` 0 falhas em 8 execuções.
- **`test_report.sh` reportava sucesso com o build quebrado** (M9/T2.3): imprimia
  "testes 'ok': 0 / SKIPs: 0" e saía 0 quando `cargo test` falhava — a ferramenta feita para
  impedir falso verde produzindo o falso verde mais puro. Agora propaga o código de saída e
  trata zero-testes-executados como erro.

### Security
- Verificação de integridade no download do ONNX Runtime (M9/T2.2): `scripts/setup_onnxruntime.sh` agora confere SHA-256 **antes** de extrair e aborta sem criar `vendor/` se o tarball não conferir. `[MEDIDO]` em M6 uma lib errada deixou a inferência até 40× mais lenta; sem checksum, um artefato corrompido ou substituído passaria em silêncio. Hash de referência medido e validado por equivalência com a lib já em uso.

### Fixed
- Suíte validada em **ambiente limpo** (M9): instalando só o `requirements-test.txt` num venv virgem, a suíte roda com **91 passed / 14 skipped / 0 failed**; na máquina completa, 192 passed. Os 14 SKIPs declaram honestamente quais testes exigem a stack de treino (`lhotse`/`torch`) — antes eles derrubavam a coleta inteira e ninguém via nada.
- **A suíte Python nunca foi reprodutível fora da máquina do dono** (M9, achado do CI): dez
  dependências eram usadas sem estar declaradas (`scipy`, `sounddevice`, `onnxruntime`,
  `lhotse`, `sentencepiece`, `torch`, `datasets`, `phonemizer`, `pytest`, `yaml`), e quatro
  módulos quebravam na **coleta** — o que derruba a suíte inteira, não só o teste afetado.
  Novo `scripts/requirements-test.txt` declara o que os **testes** precisam (distinto do
  `requirements-eval.txt`, que declara o que a **avaliação** precisa — a diferença nunca tinha
  sido explicitada). A stack pesada de treino usa `pytest.importorskip`, virando SKIP visível
  em vez de erro de coleta.
- CI passou a usar `venv`: distribuições recentes marcam o Python do sistema como
  externally-managed (PEP 668) e recusam `pip install` global.
- **Um handler do dashboard derrubava o servidor** (M9, achado do CI): `run_fixture_test`
  fazia `.expect("engine acabou de ser carregado")`. Num ambiente sem o modelo, o `expect`
  entrava em panic **segurando o mutex do cache de engine**, envenenando-o — e endpoints não
  relacionados (`/metrics`) passavam a falhar com `ConnectionReset`. Agora devolve resposta
  tipada indicando o que falta. Só apareceu porque o CI roda num container sem os artefatos.
- **CI não rodava — três defeitos que só a execução expôs** (M9/H-5 do `/review`). O critério
  original ("o YAML parseia") era um proxy que não distinguia workflow válido de workflow
  funcional. Rodando com `act`:
  1. `rustup: command not found` — o step assumia uma ferramenta que o runner do GitHub traz
     mas o container não, tornando o workflow não-verificável localmente;
  2. `cannot find -l:libpulse.so.0` — **a dependência de sistema nunca era instalada**. Não é
     limitação do `act`: o runner do GitHub também não traz `libpulse-dev`, então o job
     falharia igual em produção;
  3. `test_capture_fails_with_typed_error_when_source_does_not_exist` exigia servidor de áudio
     inexistente no container. A asserção **não foi enfraquecida** — onde há servidor ela
     continua exigindo `SourceNotFound`; onde não há, degrada com `SKIP` visível no
     `test_report.sh`.
- **Regressão de M9/T3.1 corrigida (BLOCKER do `/review`)**: a migração para o shared kernel
  quebrou a execução standalone dos scripts de pipeline — `python3 jvscribe/batch/batch_transcribe.py`
  falhava com `ModuleNotFoundError: No module named 'ctc'`, porque `import ctc` só resolvia sob
  pytest (é o `conftest.py` que injeta `common/` no path). Toda a suíte passava. Corrigido com
  insert explícito de path, e coberto por
  `test_entrypoints_de_pipeline_rodam_standalone`, que executa cada entrypoint de verdade.
- Ambiguidade de `normalize_ptbr` eliminada de fato (M9/T3.2): a versão que **remove** acento
  foi renomeada para `normalize_for_wer_compare` e seus 5 callers atualizados. As definições
  remanescentes têm todas a mesma semântica — redundância é tolerável, duas semânticas opostas
  sob o mesmo nome não eram.
- `LICENSE` passou de stub de 17 linhas para o texto completo (202 linhas, com o apêndice que a
  Apache-2.0 § 4(a) exige distribuir).
- README: estado de M9 alinhado ao `ROADMAP.md` e referências a "M0–M8" atualizadas para M0–M9.
- README corrigido (M9/T4.3): os 5 links internos voltaram a resolver (4 pelas restaurações de
  `c7c67b9~1`, 1 pela recuperação de `m2-rtfx-candidates.md`), a tabela de milestones foi
  sincronizada com o `ROADMAP.md`, e a seção de arquitetura deixou de afirmar que **"o vencedor
  não está travado"** — M4 travou o finalista (Zipformer-CTC medium 64M + fonema, ADR 0003).
  Um teste (`test_readme_links.py`) impede a reincidência.
- Rota `/m1` do dashboard devolvia `200 OK` vazio para sempre (M9/T4.1): `m1_measurements_json`
  lia `knowledge-base/measurements` — removido em `c7c67b9` — e engolia o ENOENT com
  `unwrap_or_default()`, o que o dashboard exibia como "relatório ainda não gerado",
  indistinguível de "medição zero". Único caso em que a deriva documental virou defeito de
  runtime. Agora a ausência é reportada no payload e exibida como causa. Os dois relatórios de
  medição de M1 foram restaurados de `c7c67b9~1`.
- `.gitignore` deixava as fixtures determinísticas fora do versionamento (M9/T2.1): as linhas 57-58 repetiam `*.wav`/`*.f32` **depois** da exceção `!tests/fixtures/*.wav`, e em `.gitignore` o último padrão que casa vence. As fixtures sobreviviam só por já estarem no index; qualquer fixture nova sumiria em silêncio, e o CI perderia o golden do `kaldi_fbank`. A regra geral agora precede a exceção, e 4 testes cobrem os dois sentidos — inclusive que o dump de eval `fleurs_one.f32` (214 K) **continua** ignorado.

- Correção de rigor no paper: número de experimentos de fine-tune colapsados alinhado à fonte medida (quatro configs codec-aug, não cinco) e remoção de precisão não-medida ("61% correct tokens").

### Removed
- Grupo A da lista de remoção da auditoria (M9/T4.2): 6 dumps `errs-*.txt` (73.368 linhas)
  cujo `recogs-*.txt` par sobrevive, 6 `wer-summary-*.txt`, 2 `examples` Rust sem caller, a
  declaração duplicada de `macaw-audio` no `Cargo.toml` do CLI, e o `train.log` de 16.034
  linhas que o próprio `.gitignore` já mandava ignorar. **Derivabilidade provada antes de
  remover**: `cer_from_recogs.py` regenera do `recogs-*` o WER = 36,36% declarado no `errs-*`
  descartado. `m4-pilot-fleurs` foi **arquivado, não apagado** (193 KB) — é o único decode sem
  `recogs` par, logo seus `errs-*` não são recomputáveis. **Nenhum modelo, peso ou vocabulário
  removido**: 27 arquivos antes, 27 depois, listagem idêntica.
- Reorganização FAANG (fase 1): removidos 5 scripts/runbook M4-superseded e one-offs de `jvscribe/` (prep_mls, prep_nemo, prep_conformer_ctc_decode, resume_tagarela_feats, run_pilot_icefall) + 3 testes órfãos + 2 arquivos `results/` marcados STALE-DO-NOT-USE.

### Changed
- Roadmap "out of scope" amendado: removido "versionamento de modelo" do item **Plataforma de frota** (agora em escopo como parte de M9). Distribuição BYOD, telemetria e monitoramento de WER em produção permanecem fora de escopo.
- Restaurados de `c7c67b9~1`: `PRD.md`, `ROADMAP.md`, `CLAUDE.md` e os 3 ADRs de `knowledge-base/adrs/`, removidos por engano em `c7c67b9` contra a regra `audit-trail-rotation.md § What NEVER rotates`.
- Reorganização FAANG (fase 2): reestruturado `jvscribe/` por pipeline — `finetune/` (prep+treino), `batch/` (transcrição+benchmark), `realtime/` (demo mic), `eval/` (medição telefônica). Um `jvscribe/conftest.py` preserva os imports por nome; a suíte agora roda de qualquer diretório (antes exigia `PYTHONPATH=training`).

## [0.7.0] - 2026-07-30

### Changed
- `codec_pool` on-the-fly agora usa torchaudio `AudioEffector` (in-process, ~21ms/cut) para
  opus baixo-bitrate, em vez de ffmpeg-subprocess (que starvava a GPU a 0% util, ~0,45 batch/s).
  Pool de treino = {G.711 μ/a (audioop), opus_low (torchaudio)}; GSM fica no builder offline.
- FT gentil (`jvscribe/run_ft_codec.sh`): `--num-workers` 2→10 para paralelizar o codec-pool
  (ffmpeg per-cut estava starvando a GPU a 0% util). Lançamento via `nohup setsid` (o `pkill -f`
  com padrão que casava o próprio shell SSH matava o launch — corrigido).
- App do microfone (`jvscribe/mic_transcribe.py`) reescrito de segmentação-por-pausa (VAD)
  para **pseudo-streaming**: janela deslizante com sobreposição + LocalAgreement-2
  (Macháček et al., ACL 2023) — não corta mais palavras na fronteira, exibe texto tentativo
  (cinza) com latência ~hop e trava a palavra (branco) quando 2 decodificações concordam.
  Trim por timestamp do CTC mantém a janela pequena. Testes do núcleo em
  `jvscribe/tests/test_mic_transcribe.py` (LocalAgreement + colapso CTC).

### Added
- Veredito final DoD#3 [MEDIDO]: com o bug encoder_embed corrigido, o FT NAO colapsa mas platoa em ~39% (acima do baseline 35,53%) — data-limited. DoD#3 <=25% nao atingivel com o modelo 64M + dados atuais; melhor telefonico = modelo entregue ~36%. <=25% depende de dado real (follow-up).
- Veredito conclusivo DoD#3 telefônico [MEDIDO]: 4 configs de codec-aug fine-tuning colapsam o
  CTC para blank (~98-100%), enquanto o modelo entregue faz 35,53% no mesmo teste — a augmentação
  dispara o atrator de blank. DoD#3 (≤25%) NÃO atingido; melhor honesto ~36% real-codec. Caminho
  a ≤25% documentado como follow-up (curriculum/label-prior research + dado telefônico real).
- Pivô do FT telefônico: full-FT + codec-aug colapsa o greedy p/ ~98% (2× medido, D2 + run
  gentil). Novo runbook `jvscribe/run_ft_freeze.sh` — encoder congelado (63M), treina só
  frontend+cabeças (~0,9M, collapse-proof). Patch de freeze via env var no train.py da instância.
- Baseline D1 real-codec + runbook do FT gentil corrigido: `jvscribe/measure_realcodec.py`
  (WER em CORAA mono-falante degradado pelo codec-pool = **36,88% [MEDIDO]**) e
  `jvscribe/run_ft_codec.sh` (FT single-ckpt + LR 0,002 + codec-pool p=0,5 + fp32 — corrige o
  colapso do D2). Phase 2/4 do plano m5-8khz.
- Cadeia telefônica de treino agora sorteia o codec do pool por-cut
  (`scripts/corpus/telephone_channel_transform.py` + `apply_band` em `telephone_channel.py`),
  substituindo o G.711-fixo. Default do pool = codecs realistas (GSM/Opus/G.711); `{"g711a":1.0}`
  recupera o comportamento legado. Retrocompatível (152 testes verdes). (ADR D3/D4 do plano m5-8khz)
- Pool de codecs telefônicos realistas (`scripts/corpus/codec_pool.py`) — G.711 μ/a (audioop),
  GSM-FR e Opus baixo-bitrate (ffmpeg em pipes, sem WAV em disco), amostrável por pesos. Substitui
  o G.711-fixo que causava o platô de 8 kHz (ADR D3/D4 do plano m5-8khz). 7 testes.
- Plano da fatia que fecha o DoD#3 telefônico
  (`knowledge-base/plans/m5-8khz-telephone-wer-plan.md`) — FT gentil corrigido + codec-pool
  realista + n-gram LM + métrica CORAA mono-falante real-codec. plan-confidence
  SHIPPABLE_WITH_CAVEATS (weighted_avg 99,2).
- Harness de medição de WER em call center real 8 kHz (`jvscribe/measure_callcenter.py`) —
  segmenta pela transcrição humana timestampada, normaliza, WER via jiwer; dado fica local
  (LGPD). Baseline REAL do modelo entregue = 40,13% [MEDIDO] (pior que o proxy 31,97%).
- Blueprint de deep research para WER 8 kHz telefônico
  (`knowledge-base/discoveries/blueprints/m5-8khz-telephone-wer-blueprint.md`) — ranking de
  alavancas (n-gram LM, pool de codecs realistas, adaptação gentil, dev/test real), com
  divergência entre cientistas registrada (8kHz-nativo vs upsample).
- App de transcrição em tempo real do microfone (`jvscribe/mic_transcribe.py`) — captura mic
  16 kHz → VAD de energia (RMS+histerese, calibra ruído de fundo, zero deps de ML) → fbank →
  ONNX int8 M5 → transcrição ao vivo no terminal, por frase (M5 é não-streaming). Mostra
  latência + RTFx por frase. Roda no notebook em CPU.
- Deliverable medido de M5 `[MEDIDO]` — Zipformer-CTC medium+fonema fine-tunado (CORAA+TAGARELA),
  int8 ONNX, avaliado **no hardware-alvo (notebook CPU, ONNX Runtime)**, full-test CORAA humano
  12.676 utts: **WER wideband espontâneo 23,31%** (CER 11,28%; abaixo do M4 27,46% que era fala
  lida) e **RTFx 34,69×** (RNF-07 ≥6× ✅). Modelo médio (averaging de checkpoint-124000+112000).
  Telefônico-proxy 8 kHz 31,97% (continuação com augmentação D2 em curso para o DoD#3 ≤25%).
  Resultados + metodologia em `wiki/medicoes/m5-modelo-final.md`; harness de medição em
  `jvscribe/decode_onnx_local.py`; prep da clip real em `jvscribe/make_callcenter_cuts.py`;
  auditoria de ruído de pseudo-rótulo em `jvscribe/scripts/tagarela_noise_audit.py`.
- Diagnóstico de M5 documentado no `CLAUDE.md` § "Contexto que evita erros repetidos" —
  a arquitetura está correta `[MEDIDO]`: o finetune faz *overfitting* (train ctc ≈ val ctc
  no melhor ponto de cada época, val sobe acima da train dentro da época), o que **prova
  capacidade de encoder suficiente**; o gargalo é dado/generalização (ruído dos pseudo-rótulos
  Whisper do TAGARELA). Registra 3 alavancas grátis contra o mesmo overfitting antes de
  colher dado novo: augmentação ligada (Reverb→Noise→Telephone + SpecAugment/weight decay,
  ADR D2, também ataca DoD#3), checkpoint averaging (`--avg`), e beam+LM no decode (hoje greedy).
- Ciclo de M5 (discover→plan) — blueprint `m5-scale-model-wer-blueprint.md`
  (`/discover-confidence` SHIPPABLE) trava o recipe de fine-tune (`do_finetune` do icefall,
  não resume) + augmentação `cut_transforms`; plano `m5-scale-model-wer-plan.md`
  (`/plan-confidence` SHIPPABLE 97,6). Corpus (ADR D4): mux CORAA humano + TAGARELA pseudo
  pesado 1:1 (`--use-mux`), test sempre no CORAA humano (pseudo nunca no test).
- Patch de fine-tune de M5 — `jvscribe/prep_finetune.py` porta o mecanismo `do_finetune`
  (flags `--do-finetune/--init-modules/--finetune-ckpt` + `load_model_params`) para o
  `zipformer/train.py` do icefall, reusando `apply_patch` (Regra 9/DRY); 5 testes de
  contrato verdes (`jvscribe/tests/test_prep_finetune.py` — injeção, compilação,
  idempotência, fail-fast).
- Prep do TAGARELA para o mux de M5 — `jvscribe/prep_tagarela.py` (molde `prep_coraa.py`,
  reusa `normalize_ptbr`+Fbank, Regra 9) adaptado ao schema parquet real (FLAC embutido em
  `audio.bytes`, filtra `accent=="pt-br"`); sem flag de split dev/test por construção
  (garantia estrutural de não-vazamento). Revisão de corpus (speech-data-scientist) →
  correções: downmix mono + decode via `Recording.from_file` (bounda RAM, garante mono, F4/F5);
  filtro determinístico de alucinação de pseudo-label (repetição n-grama + bound char/segundo,
  F3); relatório de cobertura por show (F7); 18 testes comportamentais verdes.
  `jvscribe/scripts/tagarela_coraa_leak_check.py` cruza paths do TAGARELA × videoIDs do TEDx no
  test CORAA (vazamento cross-corpus = BLOCKER; F2). Subset ~600h baixado na instância. Infra:
  consolidada em 1 instância vast.ai (RTX 3090, 600GB, $0,313/h); modelo M4 preservado local (SHA).
- Augmentação on-the-fly de M5 — adapter `scripts/corpus/telephone_channel_transform.py`
  (`TelephoneChannel(AudioTransform)`) torna o canal telefônico de M3 aplicável como
  transform lhotse lazy (precedente `Recording.narrowband()`, trata `MonoCut`/`MixedCut`),
  reusando `apply_telephone_channel` sem duplicar DSP (Regra 9); patch
  `jvscribe/prep_augment_datamodule.py` injeta Reverb + flags `--enable-telephone-aug`/
  `--rir-manifest` + telephone no `asr_datamodule.py` na ordem física Reverb→ruído→telefone
  (ADR D2); 15 testes de contrato verdes; canal telefônico é on-the-fly no treino (não
  materializado em disco), offline só nos test sets.
- Fase de dados de M5 — CORAA-v1.1 (fala espontânea PT-BR) preparado no formato do
  datamodule icefall: `jvscribe/prep_coraa.py` reusa `normalize_ptbr` + Fbank 80-bin do
  treino (Regra 9), emite `cv-pt_cuts_{dev,test}` com dev=5,91h/7522 cuts e
  test=11,24h/12676 cuts [MEDIDO] na instância vast.ai (`jvscribe/tests/test_prep_coraa.py`).
- Prova de ausência de vazamento de locutor no CORAA (PRD §7.3):
  `jvscribe/scripts/coraa_speaker_overlap.py` — disjunção train↔dev↔test provada por
  script nas 3 fontes com chave de locutor no path (CORAL/NURC/TEDx ≈78% das horas de
  train, 0 chaves em comum); ALIP+SP2010 (≈22%) reportados como não-verificáveis.

### Changed

### Deprecated

### Removed

### Fixed
- Corrige dois artefatos do app de streaming (`jvscribe/mic_transcribe.py`): duplicação de
  palavra na costura da janela pós-trim (dedup no `commit_localagreement`) e a linha que não
  quebrava em fala contínua (quebra por tamanho independe de texto tentativo). Núcleo do
  LocalAgreement extraído para função pura testável (+4 testes).

### Security

## [0.6.0] - 2026-07-28

### Added

- **M4 DELIVERABLE FINAL — Zipformer-CTC medium (64M) + cabeça de fonema: WER 27,49% `[MEDIDO]`** (`wiki/medicoes/m4-cabeca-de-fonema-no-medium.md` + `models/m4-final-medium-phoneme/`): fecha a pendência que o ADR 0003 criou (a ablação de fonema fora medida no small; a transferência ao medium era `[ESTIMATIVA]`). O medium+fonema treinou 30 épocas no MESMO corpus 161h e decodou avg=10 no FLEURS test → **WER 28,86% → 27,49%** (CER 10,94% → **10,53%**), **melhora relativa 4,74%** (IC95% bootstrap pareado [2,79%, 6,72%], n=919, B=10.000). **P(>0)=100%**, **P(≥3%)=95,7%** — DoD ≥3% atingida no ponto, e desta vez acima de 95% de confiança (o small ficara em 94,1%, fronteiriço). **A cabeça de fonema transfere ao medium** com a mesma ordem de grandeza do small (−4,74% vs −4,64% rel). Params 64,28M (cabeça +0,07%, removida do grafo ONNX de decode). Modelo exportado+verificado local (`models/m4-final-medium-phoneme/`). **Validação em CPU (o produto roda int8 em CPU, não GPU):** runtime Rust `macaw-cli transcribe` na i7-1355U, full FLEURS 919 → **WER 27,46% / CER 10,54%** — Δ 0,03pp vs o decode Python (27,49%), o runtime NÃO degrada; **int8 lossless no medium** confirmado (desconfundido: int8 28,56% ≈ fp32 28,66% no mesmo n=300, o +1pp era subconjunto). RTFx ~35-64× (real-time com folga). Limites: WER wideband (não 8 kHz — M5); peso 0,3 não variado. **M4 completo e medido em CPU de ponta a ponta (WER/CER/RTFx).**

- **DISC-05 — probe de TTA forward-only (alinhamento de features) REFUTOU a versão ingênua `[MEDIDO]`** (`jvscribe/scripts/tta_feature_align_probe.py` + `knowledge-base/backlog.md`): motivado pelo paper Dynamic-SUTA (TTA contínua). Análise: TTA com backprop está descartada para CPU real-time (N=10 forward+backward/utterance mata o RTFx); mas dá para tentar TTA forward-only adaptando normalização/prior (não pesos). **Probe barato (CPU-only, sem GPU)** mediu um alinhamento afim global telefone→wideband no test FLEURS degradado (8 kHz A-law): wideband 28,6% → telefone **cru** 37,4% → telefone **alinhado** 62,0% (n=150) — o alinhamento **PIORA** (−24,6pp, IC95% [−27,2, −22,0], P(ajuda)=0%). Diagnóstico de raiz: tentar inverter um canal **irreversível** (bandlimit destrói informação) e **não-afim** (G.711 é companding) com uma operação **afim reversível** (CMVN), no espaço errado (log-mel, onde stopband→floor); dividir por σ≈0 das bandas mortas **amplifica ruído** e converte uma degradação **benigna** (bandlimit coerente, que o modelo tolera) em **maligna** (ruído injetado). Achados: (1) CMVN global refutado para pesos congelados — **não se toca nas features** (o modelo está calibrado a elas); (2) o **gap telefônico é REAL** (+8,84pp / ~31% rel, 28,6%→37,4%, simulado bandpass+A-law, o piso da penalidade) → há headroom, e o espaço certo é o **DECODER** (blank penalty/LM fusion/léxico), não a feature; **M5 (augmentação offline) é o lever primário**. Meta-lição: o probe de minutos falsificou uma teoria plausível antes de qualquer build (YAGNI/parsimony na prática). Variantes refinadas (CMN só-média; alinhamento mascarado por banda) ficam no backlog `[ESTIMATIVA]`. Números n=150: `wiki/medicoes/probe-tta-align.txt`. Teste: `jvscribe/tests/test_tta_feature_align_probe.py` (greedy CTC).
- **DISC-06 — "TTA do decoder" (a inovação/IP) + probe do blank penalty `[MEDIDO]`** (`jvscribe/scripts/blank_penalty_probe.py` + `knowledge-base/backlog.md`): reframe nascido do DISC-05 — para um CTC int8 de pesos congelados em CPU, a superfície adaptável é o **DECODER** (blank penalty / peso do LM / beam / léxico), não os pesos (backprop) nem as features (irreversível). Um controlador online fast-slow (estrutura do DSUTA) que acopla **dificuldade→esforço de compute** (greedy barato no fácil; sobe LM/beam no difícil detectado por blank-ratio/peak-posterior forward-only) — unifica DISC-03/04 + EXP-02 + o dynamic-reset do DSUTA. **Probe da alavanca blank penalty (decoder-space): também não ajuda** — best β=0, qualquer β>0 piora monotonicamente (wideband e telefone). Insight: sob telefonia os erros são **substituições** (detalhe espectral perdido confunde fonemas), não **deleções** — blank penalty conserta deleção → **alavanca errada** para este modo de erro (consistente com `analyze_error_composition`, substituição dominante). **Os dois probes juntos (DISC-05 feature, DISC-06 blank) eliminam por medição os caminhos errados e convergem para o que a evidência já apontava: LM fusion (EXP-02) + léxico (DISC-04) + augmentação (M5)** — as alavancas de decoder/treino que atacam substituição. O reframe DISC-06 sobrevive (o controlador aprenderia a subir LM/léxico, não blank); o probe informa quais knobs valem. Números n=150: `wiki/medicoes/probe-blank-penalty.txt`. Teste: `jvscribe/tests/test_blank_penalty_probe.py`.


### Changed

- **ADR 0003 — reversão do finalista de M4: tamanho small (22M) → medium (64M) por medição de soak/carga `[MEDIDO]`** (`knowledge-base/adrs/0003-m4-finalist-medium.md`): supersede **parcialmente** o ADR 0002 — muda **só o eixo tamanho**; encoder (Zipformer), decoder (CTC greedy) e cabeça de fonema auxiliar permanecem (`asr-chief-scientist`). Fecha a pendência que o ADR 0002 deixou explícita (soak RNF-04 + carga RNF-05 nunca medidos; o RTFx do ADR era clip único offline). **Sob a condição-alvo de produção (softphone concorrente = carga, RNF-05): small e medium EMPATAM em RTFx** (min 7,1× vs 7,6×, ambos ≥ 6× RNF-07) — a vantagem do small evapora quando a CPU satura. Isolado, o small é só **1,15× mais rápido** (74,1× vs 64,3× median), não 2×. **Correção de análise:** o RTFx do medium no ADR 0002 ("17-38×") estava **subestimado ~2×** — bench independente @ 2 threads dá 35-60×, consistente com os 64× da soak; só o small tivera tabela detalhada na fase-5, o que enviesou a decisão para o small. Removidos os dois artefatos (RTFx do medium subestimado + RTFx do small fora da condição-alvo), o critério bloqueante 1 (RTFx) empata e o desempate migra para o eixo primário do projeto — acurácia — onde o **medium ganha −1,11pp WER (~3,7% rel: 28,86% vs 29,97%)**. Térmico estável 87-94°C (a queda de RTFx nas idle era **contenção, não throttle** — provado por covariável load1/temp). Rejeita: small como default (vantagem só em máquina ociosa, some sob carga → rebaixado a fallback de tiering), large (retornos decrescentes já medidos no ADR 0002, regime data-bound R9). Limites honestos: frota Q-01 não medida (esta é a máquina BOA; medium 30s ~35× cairia a ~12-17× em CPU 2-3× mais fraca → tiering como trabalho futuro do `hardware-validation-engineer`); **cabeça de fonema não re-medida no medium** (ablação foi no small, transferência esperada mas `[ESTIMATIVA]`); estressor ≠ Zoom real; medium teve só 7/19 janelas limpas; acurácia é wideband (gap 8 kHz de M5 pode não escalar o 1,11pp). **Pendência criada:** treinar/exportar o **medium + cabeça de fonema** e re-medir WER. `models/m4-final-phoneme-small/` fica retido como fallback. Evidência: `wiki/medicoes/m4-soak-small-vs-medium.md`.

## [0.5.0] - 2026-07-27

### Added

- **M4 fase 3 — cabeça de fonema: DoD ≥3% atingida no ponto (WER −4,63% rel, IC fronteiriço) `[MEDIDO]`** (`jvscribe/prep_phoneme_head.py` + `jvscribe/gen_phonemes.py` + `jvscribe/scripts/bootstrap_wer_ci.py` + `jvscribe/scripts/wer_core.py`, NOVOS): estende a recipe REAL do icefall (`zipformer/{zipformer.py,model.py,train.py}`) com uma 2ª cabeça CTC de fonema em camada intermediária (§ 8.1 do PRD), via patch determinístico idempotente (substrings exatas + `assert count==1` — Regra 9). Colocação em ~50% da profundidade (stack 2, dim 256), fundamentada em Lee & Watanabe 2021 (intermediate-CTC). Custo em produção `[ESTIMATIVA/FONTE-REPO]` zero (cabeça só instancia quando `phoneme_vocab_size>0` e não entra no grafo ONNX de decode — verificado; +16.034 params = +0,07% no treino). Alvos G2P `phonemizer`+`espeak-ng` (GPLv3, **só treino offline**): 37.668 textos, 62 fonemas, 0 falhas. **Resultado da ablação** (30 épocas, `phoneme_loss_scale=0.3`, decode `ctc-greedy-search` avg=10, FLEURS held-out, load estrito 559/559 chaves): **WER 29,97% → 28,58%** (CER **11,42% → 10,85%**), **melhora relativa 4,63%** (IC95% bootstrap pareado [2,63%, 6,63%], n=919, B=10.000). **P(melhora>0)=100%** (inequivocamente significativa), **P(melhora≥3%)=94,1%**. **Critério de DoD = estimativa pontual** (4,63% ≥ 3% → atingida); o IC é qualificação obrigatória e é honesto: limite inferior 2,63% < 3% → **PASS com nota, fronteiriço, não folgado** (o critério IC-inferior≥3% exigiria varredura de peso — follow-up). Supervisão fonética do § 8.1 empiricamente validada para o Zipformer-CTC small. Evidência: `wiki/medicoes/m4-cabeca-de-fonema-no-medium.md`. Testes puros (15 casos): `test_gen_phonemes.py`, `test_prep_phoneme_head.py`, `test_bootstrap_wer_ci.py`, `test_cer_from_recogs.py`.
- **ADR 0002 — finalista de arquitetura de M4: Zipformer-CTC small (22M), int8 `[MEDIDO]`** (`knowledge-base/adrs/0002-m4-architecture-finalist.md`): fecha a pendência do ADR 0001 (`asr-chief-scientist`). Decide encoder/decoder/tamanho para o alvo CPU real-time **por medição** (mesmo corpus/test/decode/máquina para todos os braços). Head-to-head arquitetural: **Zipformer-CTC medium domina os dois eixos de acurácia sobre Conformer-CTC medium** (WER 28,86% vs 31,57%, CER 10,94% vs 11,90%, params equivalentes +0,7%) — diferença atribuível à arquitetura, não a confound de framework. Curva WER×RTFx decide o tamanho: **small (22M) domina** — mesmo CER (~11%) do large 7× maior, ~1pp de WER a mais, RTFx 49-90× vs 17-38× do medium (retornos decrescentes: large empata com medium, ganho zero por 2,3× params — regime data-bound, R9). int8 lossless (Δ 0,24pp WER vs fp32). Rejeita Conformer-CTC (perde acurácia; RTFx CPU `[DESCONHECIDO]` mas não-decisivo) e medium/large Zipformer (retornos decrescentes). Limites honestos: WER é wideband FLEURS (não 8 kHz call center — M5); é Conformer-icefall, não FastConformer-NeMo (un-provisionable, 4+ falhas); treino causal/equivalência streaming são M4-fase-3/M6. Evidência: `wiki/medicoes/index.md`, `wiki/medicoes/runtime-rust-int8-vs-fp32.md`.
- **M4 fase 4 — Conformer-CTC (2º finalista) treinado e decodado `[MEDIDO]`** (`jvscribe/scripts/cer_from_recogs.py`, NOVO): Conformer-CTC medium (64,72M, recipe `conformer_ctc3` do icefall) treinou 30 épocas no MESMO corpus `data/pt` (161h) e decodou `ctc-greedy-search` avg=10 no FLEURS test full (919 cuts, 21.471 palavras) → **WER 31,57% / CER 11,90%**. Fecha o head-to-head do ADR 0002. O scorer novo computa WER+CER de um `recogs-*.txt` do icefall reutilizando o Levenshtein do `eval_runtime_wer.py` (Regra 9) — **validado** por reproduzir o WER oficial do icefall exatamente (31,57%), o que torna o CER confiável; método idêntico ao que produziu o CER do Zipformer (comparação apples-to-apples). Testes: `jvscribe/tests/test_cer_from_recogs.py` (caso conhecido + transcrição perfeita + caso negativo ref/hyp desemparelhado falha alto). Artefatos (recogs/errs/logs de avg=10 e avg=1): `wiki/medicoes/m4-conformer-ctc-medium/`.
- **M6 DISCOVER — blueprint de streaming causal Zipformer-CTC (RNF-02) `[FONTE-REPO]`** (`knowledge-base/discoveries/blueprints/m6-streaming-causal-blueprint.md`): fase discover do CYCLE de M6 (`streaming-asr-scientist`), ancorada no código dos peers (icefall causal + sherpa-onnx online), 42 rótulos de proveniência, citações verificadas linha-a-linha. Achados: (1) **equivalência batch≡streaming é por construção** — treino `--causal 1` já aplica máscara de atenção chunk-limitada; o repo mede Δ<0,1pp WER simulated vs chunk-wise (`RESULTS.md:823`, verificado: 7,81 vs 7,79); (2) **chunk-16/left-128 → 320ms** fecha RNF-02 p99≤500ms (~180ms de folga); **chunk-32→640ms VIOLA**; (3) cache = 6 tensores/camada bounded por left-context (base RNF-03), I/O ONNX de forma fixa; (4) caveat: equivalência fp32 NÃO transfere ao int8 — verificar nos dois; (5) warm-start offline→causal é parcial (conv causal difere) → treino causal do zero (~6h). De-risca o *como* do streaming sem travar o finalista (output de M4). Unknowns (WER por chunk, p99 sob carga) marcados p/ M4/M5/M6.
- **M4 — curva Zipformer COMPLETA (WER+CER), retornos decrescentes confirmados `[MEDIDO]`:** small 22M = **29,97% WER / ~11,0% CER**, medium 64M = **28,86% / 10,94%**, large 147M = **28,87% / 11,14%** (FLEURS test, 21.471 palavras). O **large empata com o medium em WER E CER** (2,3× params, ganho zero) e o **small tem o mesmo CER (~11%) que o large** — regime data-bound (corpus é o gargalo, não capacidade). **`small` é o finalista claro** (mesmo CER, +1pp WER, 3-7× mais barato, RTFx 49-90×). Caveat honesto: large decodado avg=9 (epoch-20 apagado no conserto do crash de disco cheio — o treino morreu no epoch-28 corrompido, retomado do 27). CER do small via runtime (recogs icefall sobrescritos pelo exp. telefônico). Evidência: `wiki/medicoes/index.md`.

- **Análise da composição do erro do ASR — 47,8% atacável por léxico `[MEDIDO]`** (`jvscribe/scripts/analyze_error_composition.py`, NOVO): testa empiricamente a ideia de "corrigir palavra fora do léxico PT-BR". Classifica cada substituição do runtime contra um dicionário de 471k palavras (`/usr/share/dict/brazilian`): **non-word atacável por léxico = 47,8%**, real-word inatacável (só LM) = 36,3%, rare-ref (biasing) = 15,9%, false-flag (risco de corromper palavra correta) = **0,35%** (n=120, 611 substituições). Valida a técnica com teto alto + risco baixo; alimenta o discover `DISC-04` (léxico + biasing sobre CTC via beam+FST `L∘G∘B`, reusa sherpa — não hashmap pós-hoc). Caveat honesto: FLEURS limpo ≠ call center (rare-ref e false-flag sobem lá); parte dos non-word é char-doubling do modelo ("elle"/"annos") que M5 conserta na fonte. Backlog: `knowledge-base/backlog.md`.
- **M6 — eval de ACURÁCIA do runtime Rust: WER 25,75% ≈ decode Python 29,97% `[MEDIDO]`** (`jvscribe/scripts/eval_runtime_wer.py`, NOVO): harness que faltava — roda N utterances do FLEURS test pelo runtime de produção (`macaw-cli transcribe` = wav → kaldi_fbank → transcribe → ctc_greedy) e computa WER real (Levenshtein de palavras, normalização de treino). **Runtime Rust WER = 29,92%** (n=470) vs **29,97%** do decode Python (set completo) → o runtime **não degrada** a acurácia; a cadeia Rust é funcionalmente equivalente ao decode do icefall (o n=40 = 25,75% era ruído de subconjunto; com n grande o número casa). Eval agora reporta **WER e CER** (`[MEDIDO]` small: WER 28,21% / **CER 10,99%**, n=100 — o CER≪WER mostra erros de 1-2 chars foneticamente próximos, não grosseiros). Robusto a timeout por-utterance. Velocidade: **RTFx 48-55×**. **Dois achados de deployment `[MEDIDO]`** (`wiki/medicoes/runtime-rust-int8-vs-fp32.md`): (1) o binário **standalone** precisa de `ORT_DYLIB_PATH` apontando p/ a ONNX Runtime vendorizada (`vendor/onnxruntime-linux-x64-1.23.0/`) — sem ele o `ort` load-dynamic cai numa lib lenta do sistema (clip de 6,84 s: 0,12 s com a lib certa → >30 s com a errada, 40×+); era esse o gargalo, não o modelo/O(T²)/utterance-longa. **Follow-up:** o binário de produção deve garantir a lib certa (rpath/bundle/check no startup). (2) `GraphOptimizationLevel::Level3` DEGRADA o int8 com esta lib (comentário `[MEDIDO]` em `crates/macaw-asr/src/lib.rs` — `load` fica com `Disable`).
- **M6 runtime v0 — wiring triad COMPLETO: subcomando `macaw-cli transcribe <wav>` `[MEDIDO]`** (`crates/macaw-cli/src/transcribe.rs`, NOVO): o caller de produção que faltava (pilar a do wiring, apontado pelo `/review`). Roda a cadeia completa `wav → jvscribe_audio::kaldi_fbank → AsrEngine::transcribe → texto` e emite a métrica de runtime (pilar c). Prova e2e no wav real: `após o ocidente guibs foi movido para um hospital mas morreu pouco tempo depois` — **RTFx=12,3× por-utterance** (só fbank+inferência, load do modelo fora da janela — honesto vs RNF-07), T=684, 6,84s de áudio, 14 tokens. Erros tipados (`TranscribeError`: WAV inválido/ausente, features, ASR), validação de formato (16 kHz mono → caso negativo testado). Testes: `crates/macaw-cli/tests/transcribe_wav_test.rs` (leitura de WAV + caso negativo sempre; e2e `#[ignore]` com modelo). **Fecha o finding F3 do `/review`** — o runtime v0 agora transcreve um WAV de ponta a ponta como caminho de produção observável, não só como teste. clippy `-D warnings` limpo. (Streaming/causal e hotwords seguem fora do v0.)
- **M6 runtime v0 — task #25 fechada: fbank 80-bin kaldi no macaw-audio, casado com o lhotse `[MEDIDO]`** (`crates/macaw-audio/src/kaldi_fbank.rs`): novo extrator de log-mel 80 bins na convenção kaldi/HTK (janela povey, mel HTK, pré-ênfase + remoção de DC no domínio do tempo, `snip_edges=False` com reflexão de borda) que casa bit-a-bit com `Fbank(FbankConfig(num_mel_bins=80))` do lhotse — a MESMA chamada usada no treino (`jvscribe/prep_mls.py:99`, `jvscribe/prep_icefall.py:112`). Casamento numérico contra golden gerado pelo lhotse (`jvscribe/scripts/make_kaldi_fbank_golden.py`): **MAE=0,000088, correlação de Pearson=1,000000** (300 frames × 80 bins, tom 440 Hz determinístico). **Prova end-to-end com fala real e o modelo de produção** (`crates/macaw-asr/tests/real_speech_from_wav_test.rs`, `#[ignore]` — fixtures não versionadas): wav → `jvscribe_audio::kaldi_fbank` → `AsrEngine::transcribe` produz **86% word-overlap**, idêntico ao obtido alimentando features pré-computadas do lhotse (`real_speech_test.rs`) — o extrator novo é funcionalmente equivalente ao de treino. **Remove o bloqueio** dos pilares (a)+(c) do wiring apontado pelo `/review` do runtime v0 (o gap era o macaw-audio produzir 128-bin NeMo/Slaney quando o modelo espera 80-bin kaldi/HTK). Resta expor a cadeia num caller de produção — o subcomando `transcribe <wav>` no macaw-cli (pilar a) + métrica (pilar c); a cadeia em si está provada e2e. Adiciona sem quebrar: o extrator de 128 bins (`crate::features`, usado pelo M0-proof) permanece intacto. Fixture real de fala extraída via `jvscribe/scripts/extract_fleurs_one_wav.py` (mesma utterance de `fleurs_one.f32`/`fleurs_one.txt`, não versionada — mesma decisão já registrada para os demais fixtures de fala real).
- **M6 runtime v0 — TRANSCRIÇÃO DE FALA REAL validada `[MEDIDO]`** (`crates/macaw-asr/tests/real_speech_test.rs`): o runtime Rust (ctc_logits→ctc_greedy→detok) decodifica um utterance real do FLEURS test (features corretas do lhotse) → **86% word-overlap** com a referência ("após o acidente gibson foi movido para um hospital mas morreu pouco tempo depois" → só 2 palavras foneticamente próximas erradas). **Prova end-to-end que o decode está 100% funcional em fala real.** O único gap para o demo wav→texto é o fbank do macaw-audio (128-bin NeMo vs 80-bin icefall, task #25), NÃO o decode
- **M6 runtime v0 Fase 2 — inferência do modelo real em Rust `[MEDIDO]`** (`crates/macaw-asr/src/lib.rs`): `AsrEngine::ctc_logits()` + `transcribe()` rodam o contrato REAL do nosso ONNX icefall (`x`(1,T,80)/`x_lens`→`log_probs`), corrigindo o achado do deep-review (o `encode()` de M0 era placeholder NeMo com nomes errados que só devolvia o shape). Teste de integração no `model.int8.onnx` real: 60 frames → T=13 (subsampling 4× do Zipformer), vocab=500, pipeline logits→greedy→detok roda sem erro (`tests/transcribe_smoke_test.rs`). ADR-1: adicionar, não mudar `encode()` (11/11 testes do crate verdes). Falta a Fase 3 (wav→texto com features casadas) para provar transcrição de fala real
- **M6 runtime v0 — decoder CTC greedy em Rust `[MEDIDO]`** (`crates/macaw-asr/src/decode.rs`): implementado o `ctc_greedy` (argmax por frame + colapso blank/repetição, portado de sherpa-onnx `offline-ctc-greedy-search-decoder.cc:42`, Regra 9) + `detok` BPE (▁→espaço) + `argmax`. Domínio puro (sem ONNX), fail-safe a entrada curta. **5/5 testes fixture verdes** (`tests/ctc_decode_test.rs`), clippy limpo, 57 LoC. Fase 1 do plano `m6-runtime-v0` (CYCLE de M6: discover SHIPPABLE → plan SHIPPABLE 100 → implement). Zero dep nova

- **M6 early (real-time de-risk com o modelo atual)** — `jvscribe/bench_rtfx.py --soak-min N`: modo soak que roda o int8 continuamente por N min na i7-1355U, logando RTFx por janela de 30s para revelar throttle térmico (RNF-04 exige RTFx sustentado ≥ 80% do pico ≥ 10 min). Iniciado M6 com o Zipformer-CTC small que já temos, conforme decisão do dono (2026-07-26): valida os critérios de real-time que NÃO dependem de M5. Nota honesta: soak/carga/int8 são validáveis já; a latência p99 streaming (RNF-02) + equivalência batch≡streaming exigem um modelo causal (`train --causal 1`), que fica para quando um GPU liberar

- **M4 fase 4 — corpus NeMo p/ o 2º finalista** (`jvscribe/prep_nemo.py`): converte o MESMO corpus (MLS-PT 161h train + FLEURS dev/test) para o formato de manifest do NeMo (`{audio_filepath, duration, text}`), reusando `prepare_mls` + o build do FLEURS (Regra 9) — comparação justa FastConformer-CTC vs Zipformer-CTC no mesmo test. Testes: `jvscribe/tests/test_prep_nemo.py`. Instância NeMo (imagem `nvcr.io/nvidia/nemo:24.12`) provisionada
- **M4 fase 5 — RTFx na CPU-alvo `[MEDIDO]`** (`jvscribe/bench_rtfx.py`): export do small para ONNX int8 (27MB) + benchmark na **i7-1355U de referência** → **RTFx 41-68× a 1 thread / 49-90× a 2 threads**, contra o piso de **≥6× (RNF-07)** = **7-15× de folga**. Fecha o eixo decisivo do objetivo CPU: o small tem margem enorme para tempo real. Régua reutilizável testada. Caveats: offline (não streaming), clip único (não soak RNF-04). Testes: `jvscribe/tests/test_bench_rtfx.py`
- **M4 — experimento de penalidade telefônica** (`jvscribe/make_telephone_test.py`, recomendado pelo `asr-chief-scientist`): degrada o held-out FLEURS pela cadeia telefônica do M3 (banda 300-3400 Hz + G.711 A-law, reusa `scripts/corpus/telephone_channel.py` — Regra 9) e re-decodifica o checkpoint de 161h JÁ treinado — mede o multiplicador do domínio 8 kHz **sem treinar nada**, atacando o maior risco identificado (o alvo é 8 kHz telefônico, o WER medido era wideband limpo). Testes: `jvscribe/tests/test_make_telephone_test.py`
- **M4 fase 2 — curva WER×tamanho em 161h `[MEDIDO]`:** small (22M) = **29,97%** vs medium (64M) = **28,86%** (avg=10, held-out FLEURS). **Retornos decrescentes fortes: 3× os params compram só −1,1 p.p.** — regime data-bound, favorece o `small` para o objetivo CPU real-time (quase o mesmo WER a fração do compute). large (147M) treinando p/ completar a curva do DoD
- **M4 fase 2 — PRIMEIRO WER real em 161h `[MEDIDO]`:** Zipformer-CTC **small (22,1M)** treinado 30 épocas em MLS-PT 161h → **WER held-out (FLEURS) = 29,97%** (avg=10) / 33,99% (avg=1). **Salto de 96% (piloto 10h) → 30% (161h)** confirma plenamente a tese data-bound (o gargalo é corpus, não arquitetura — PRD R9). Modelo saudável (74% das palavras corretas, erros balanceados, não o colapso-para-blank do piloto). Model-averaging **inverteu como a teoria prevê**: no run convergido (val loss 0,23) o avg **ajuda** (ao contrário do piloto não-convergido onde degenerava). Evidência: `wiki/medicoes/index.md`. Medium/large treinando na sequência
- **M4 fase 2 — orquestração de treino** (`jvscribe/run_zipformer_ctc.sh`): train+decode de UM tamanho Zipformer-CTC no corpus `data/pt`, encapsulando o conhecimento do piloto (lang-dir completo com `tokens.txt`, `--enable-musan 0`, decode sem averaging cego — testa avg=1 e avg=10, o melhor vence). Flags dos 3 tamanhos (small 22M / medium 64M / large 147M) copiados do `RESULTS.md` do icefall (Regra 9). Uso: `bash run_zipformer_ctc.sh <small|medium|large>`
- **M4 fase 1 — corpus de decisão** (`jvscribe/prep_mls.py`): monta o corpus para comparar as arquiteturas com dado adequado — **train = MLS-PT ~161h** (CC-BY, humano) via `lhotse.recipes.prepare_mls` (Regra 9 — a recipe do lhotse lê o layout OpenSLR tar/opus, não reimplementamos), **dev/test = FLEURS held-out humano** (mesmo test set do piloto, para comparação justa). Emite `cv-pt_cuts_{train,dev,test}` no formato do datamodule real do icefall; reusa `normalize_ptbr`/`build` do `prep_icefall` sem duplicar (audit D2). Testes de contrato: `jvscribe/tests/test_prep_mls.py`. Decisão do dono (2026-07-25): corpus CC-BY limpo ~161h (não ~500h pseudo-labelado) — suficiente para ranquear as 2 arquiteturas
- **Piloto FLEURS-only de M4 executado na recipe REAL do icefall (vast.ai RTX 3090, ~$0,22 `[MEDIDO]`):** Zipformer-CTC small (22,1M params, CTC puro) treinado 30 épocas do zero em FLEURS pt_br (~10h) → decode `ctc-greedy-search` no held-out. **WER test = 96,52% `[MEDIDO]`** (train 95,19% — train≈test ⇒ **underfit/colapso-para-blank**, não overfit; contraste com o smoke de 1h que overfitou). Throughput **41,9s/época `[MEDIDO]`**. Achado metodológico: model-averaging (avg-15) sobre trajetória não-convergida **degenera** o modelo (100% vazio) — sem averaging = 96,52%. Prova o pipeline ponta-a-ponta na recipe real (os 757 corretos provam que o decode não tem bug); confirma a tese data-bound (10h é insuficiente; TAGARELA/M5 é a resposta). **NÃO decide o finalista de M4** (1 finalista, dados mínimos, sem RTFx). Evidência: `wiki/medicoes/m4-pilot-fleurs-results.md` + logs. Decoder adaptado (librispeech→commonvoice, Regra 9): `jvscribe/patch_ctc_decode.py`
- Adaptador de dados `jvscribe/prep_icefall.py` — emite o corpus multi-fonte (FLEURS + MLS-PT, ~161h+) no formato EXATO que o datamodule real do icefall carrega (`cv-{lang}_cuts_{train,dev,test}.jsonl.gz` + fbank). É o único código nosso para o piloto; o treino/loss/model vêm da recipe real do icefall (Regra 9). Runbook: `jvscribe/run_pilot_icefall.md`. Aguarda crédito GPU (~$50) para o piloto real. Testes determinísticos da parte pura (normalização PT-BR preserva diacríticos + estrutura das fontes): `jvscribe/tests/test_prep_icefall.py` (7 casos); flag `--limit` para smoke local do gerador de cuts

- Pipeline de treino de M4 (`jvscribe/`): `prep_fleurs` (FLEURS pt_br → manifests Lhotse + fbank), `gen_phonemes` (alvos fonéticos G2P), `train_ctc` (Zipformer-CTC do zero + cabeça de fonema auxiliar — reusa os módulos do icefall, CTC via torch), `decode_ctc` (WER greedy). **Provado end-to-end numa GPU real** (vast.ai RTX 3090, imagem oficial `k2fsa/icefall`, ~$0,35): treina, converge, decoda, produz WER `[MEDIDO]`. Achado honesto: o smoke (1 h de corpus) overfita — WER held-out ~95%+; a ablação da supervisão fonética é inconclusiva nesse volume, só testável no piloto de ~500 h (`wiki/medicoes/m4-smoke-results.md`, `knowledge-base/implementations/m4-pilot-implementation.md`)

- Blueprint de discovery de M4 (piloto comparativo) — `knowledge-base/discoveries/blueprints/m4-pilot-blueprint.md` (SHIPPABLE 100). Deep research de 3 agentes (asr-chief-scientist, ptbr-phonetics-scientist, ml-infra-engineer) respondeu 8 questões: recipe icefall Zipformer-CTC (train.py paramétrico, 3 tamanhos por escala), **G2P PT-BR medido** (cobertura/determinismo 100% sobre FLEURS pt_br, mas GPLv3 — só treino offline; PER absoluto `[DESCONHECIDO]`), e a **estimativa de custo com fórmula**: piloto ~$98-200, M5 completo ~$1.350-2.000/run. Achados que reenquadram M4: a supervisão fonética NÃO existe pronta na recipe (só CTC de subword — exige construir a cabeça de fonema); k2 é incompatível com o torch instalado (treino exige imagem GPU separada)


### Changed

- **Limpeza de `jvscribe/` pós-audit `/loop-system-design`** (relatório: `knowledge-base/audits/2026-07-25-training-system-design.md`, score 3,5/5, 0 críticos/altos): o **cluster smoke** (`train_ctc.py`, `decode_ctc.py`, `prep_fleurs.py`, `gen_phonemes.py`) foi movido para `jvscribe/smoke/` (quarentena) — remove o risco de copy-paste ao lado do único código de produção `prep_icefall.py` (findings B1/D3) e resolve a duplicação/drift do `normalize_ptbr` (D2) deixando a produção com uma cópia só. `prep_icefall.py`: removidos imports mortos `numpy`/`glob` (D4) e parametrizado `--num-jobs` para o prep de ~500h de M5 (SC1). ADR sugerido (formaliza a decisão Regra-9 de reusar a recipe): `knowledge-base/audits/000X-m4-reuse-icefall-recipe.md`
- **Correção de rumo em M4 (honestidade):** o `train_ctc.py` (wrapper self-contained) foi rebaixado a SMOKE ONLY — tem bug confirmado contra a recipe real do icefall (não passa `src_key_padding_mask` ao encoder → atende frames de padding) + cabeça de fonema ad-hoc + configs por escala. O smoke overfitou (WER treino 18% vs held-out 99%), o que mascarou os defeitos. O **piloto de 500 h passa a usar a recipe REAL do icefall** (`train.py`/`model.py`/`asr_datamodule.py`, `--use-ctc 1 --use-transducer 0`) sem reescrever loop/loss/model (Regra 9) — runbook em `jvscribe/run_pilot_icefall.md`


### Fixed

- **M6 EXP-01 — int8 é lossless vs fp32 (custo zero de acurácia) `[MEDIDO]`** (lição T-Mimi testada): small finalista, mesma engine Rust, n=100 — int8 (27MB) WER 28,21%/CER 10,99% vs fp32 (92MB) WER 28,45%/CER 10,93%. Δ 0,24pp/0,06pp dentro do ruído → **int8 não degrada acurácia**, deploy do int8 (3,4× menor) é seguro. Refuta quantização mista/QAT p/ o nosso caso (nada a recuperar). Override `MACAW_MODEL` no runtime p/ A/B de modelo (`crates/macaw-cli/src/transcribe.rs`). Evidência: `wiki/medicoes/runtime-rust-int8-vs-fp32.md`.
- **M6 task #26 RESOLVIDA — binário standalone resolve a `libonnxruntime` sozinho (era 40× lento) `[MEDIDO]`** (`crates/macaw-cli/src/ort_setup.rs`, NOVO): o `ort` (`load-dynamic`) lê `ORT_DYLIB_PATH`, setado pelo `.cargo/config.toml` **só sob cargo** — o binário standalone caía numa `libonnxruntime` lenta do sistema (inferência até 40× mais lenta). `ensure_ort_dylib()` roda no startup do `main()`: respeita um env válido, senão **resolve a lib vendorizada subindo a árvore** (`vendor/onnxruntime-*/lib/libonnxruntime.so`, relativo ao executável e ao manifest) e a seta; **se não achar, FALHA ALTO** com mensagem acionável (fail-fast, nunca degrada em silêncio — error-handling.md § 1). Prova: `env -u ORT_DYLIB_PATH macaw-cli transcribe` agora acha a lib e roda a **RTFx 28,8×** (antes: >30s/timeout). TDD: 3 testes do resolver (acha subindo a árvore / None quando ausente / ignora vendor sem a lib). clippy `-D warnings` limpo.
- **Teste flaky `test_slow_endpoint_does_not_block_metrics`** (`crates/macaw-cli/tests/server_concurrency_test.rs`): sob contenção de CPU (suíte inteira em paralelo), o `http_get` falhava no `TcpStream::connect` (accept do servidor recusava transitoriamente antes de estar pronto) — starvação, não serialização. Adicionado retry curto no connect (10× / 20ms) que elimina o flaky sem mascarar o bug que o teste caça (serialização apareceria na asserção de timing, não no connect). Workspace: 69 passed / 0 failed em runs repetidos (testing.md § 3: flaky é bug)
- **M6 runtime v0 — fixes do `/review` (4 agentes, verdict NEEDS_FIXES)** em `crates/macaw-asr/`: (T-01) adicionado o teste da semântica CENTRAL do CTC — repetição separada por blank não colapsa (`[1,0,1]→[1,1]`), regressão que pega qualquer quebra de `decode.rs:41`; (T-02) os testes de integração (`transcribe_smoke`, `real_speech`) faziam `return` reportando PASSED quando o fixture falta (verde-fictício no CI) → agora `#[ignore]` honesto (listados como IGNORED, rodam com `--ignored`); (T-03/04) casos negativos dos erros tipados `Vocab::load`→`VocabNotFound`/`InvalidVocab` e `AsrEngine::load`→`ModelNotFound`, e `detok` de id fora do range (descarte silencioso documentado como contrato); (T-05/06/07/08) argmax/detok um comportamento por teste + fixture temp único por processo + bordas (NaN, empate, `vocab==0`, `t_len==0`, `blank!=0`); (ARCH-02) blank id `0` mágico → `const ICEFALL_BLANK_ID`; (ERR-01) comentário do fail-safe de `ctc_greedy` corrigido (é guarda de bounds, não mandato de `error-handling.md`). Cobertura do decode: 5→20 testes de unidade. Workspace: 63 passed / 2 ignored, clippy `-D warnings` limpo. Review: `knowledge-base/reviews/m6-runtime-v0-review-2026-07-26.md`. **Pendente (não-fabricado):** Fase 3 (wiring wav→texto no macaw-cli + métrica) segue bloqueada pela task #25 (fbank 128→80-bin)
- **Code-quality skill — detector Rust D2 gerava 98 falso-positivos de "symbol fabrication"** (`.claude/skills/code-quality/scripts/detectors/rust.py`): ao rodar o gate no workspace Rust, o detector marcava como "crate fabricado" (HARD → FAIL_HARD) todo `use` de (a) stdlib do Rust (`std`/`core`/`alloc`, 57×), (b) crates internos do próprio workspace Cargo (`jvscribe_asr`/`jvscribe_audio`/`jvscribe_cli`, 40×) e (c) imports com alias `use x as y` (o ` as y` poluía o nome do crate, 1×) — nenhum é fabricação de símbolo. Corrigido: pular a stdlib, ler os nomes de package dos `Cargo.toml` do workspace para não acusar membros locais, e tirar o ` as <alias>` antes de consultar crates.io. Resultado: 98 → 0 falso-positivos, verdict FAIL_HARD → limpo no eixo D2 (cross-check `cargo machete`: zero deps mortas). TDD: 3 testes de regressão em `.claude/skills/code-quality/tests/test_rust_detector.py` (105/105 do skill verdes)
- `jvscribe/run_zipformer_ctc.sh` (2 bugs pegos no run do small): o decode chamava `./zipformer/ctc_decode.py` (permission-denied, pois o `patch_ctc_decode.py` escreve sem +x) → agora `python3 ./...`; e o guard do lang-dir olhava `tokens.txt` (que existe sem o lang completo) → agora olha `L.pt`, o artefato final do `prepare_lang_bpe`
- `jvscribe/prep_mls.py` (2 bugs descobertos rodando na instância): `corpus_dir` passado ao `prepare_mls` é o **parent** que contém `mls_portuguese_opus/` (o recipe faz `corpus_dir.glob("mls_*")`), não o dir do idioma; e a estrutura de retorno é `manifests[lang][split]` (lhotse `mls.py:94,133`), não `[split][lang]`. Adicionado `output_dir` de cache para re-runs não re-escanearem os opus
- `jvscribe/prep_icefall.py`: `_download` agora cria o `PARQUET_DIR` antes do `curl` (o `curl -o` falhava com exit 23 "write error" quando o diretório não existia — descoberto ao rodar o piloto real na vast.ai) e usa `curl -sfL` (`-f`: falha explícita em HTTP 4xx/5xx em vez de gravar página de erro como se fosse parquet). Teste de regressão em `jvscribe/tests/test_prep_icefall.py` (`test_download_cria_pqdir_antes_do_curl`)

## [0.4.0] - 2026-07-25

### Added

- Pipeline de corpus de M3 (`scripts/corpus/`): pseudo-labeling com filtro por concordância entre 2 transcritores whisper + manifests Lhotse com augmentação telefônica on-the-fly. Componentes: `telephone_channel.py` (cadeia G.711 8 kHz em memória via scipy+audioop, nunca em disco), `agreement_filter.py` (CER par-a-par normalizado PT-BR + τ calibrado empiricamente), `pseudo_label.py` (2 whisper sequenciais RAM-safe), `build_manifest.py` (RecordingSet→SupervisionSet→CutSet Lhotse + telephone on-the-fly), `run_pipeline.py` (orquestrador). 22 testes verdes. **Evidência `[MEDIDO]`** rodando sobre 20 clips reais de FLEURS pt_br (i7-1355U): CER par-a-par média 0,055 ± 0,051 (σ), IC95% da média [0,032, 0,077], **τ=0,072 com IC95% bootstrap [0,038, 0,164]**, **manifest filtrado a 16 cuts aprovados**, augmentação on-the-fly confirmada a 8 kHz (`knowledge-base/corpus/m3-cer-distribution.md`)
- Mapa de licenças das fontes de corpus PT-BR com veredito comercial + volume declarado + Q-09 respondida (`knowledge-base/corpus/m3-licenses.md`); risco de licença do TAGARELA (NC-SA) assumido explicitamente pelo dono do projeto
- Blueprint de discovery de M3 (corpus) — `knowledge-base/discoveries/blueprints/m3-corpus-blueprint.md` (SHIPPABLE 99,1). Deep research de 3 agentes (speech-data-scientist, audio-dsp-engineer, general-purpose) respondeu 8 questões: augmentação telefônica on-the-fly via `input_transform` scipy+audioop (o `Narrowband` nativo do lhotse não cobre A-law/banda); filtro por concordância = predicado `CutSet.filter` com CER par-a-par e threshold calibrado empiricamente; lhotse exige torch; e o mapa de licenças das fontes PT-BR com veredito comercial. Achado dominante: o dataset TAGARELA (8.972 h) é CC-BY-NC-SA-4.0 (não-comercial) — risco de licença assumido explicitamente pelo dono do projeto
- `README.md` público na raiz — HERO orientado a resultado (transcrição PT-BR em tempo real sobre CPU), tabela de estado dos milestones e a conclusão `[MEDIDO]` de M2 (transducer ~2× mais rápido que AED em CPU, com link ao artefato de medição e nota de honestidade sobre a frota BYOD). Segue `.claude/rules/public-copy.md`

### Changed

- `CLAUDE.md` § estado atualizado de "discover travado / bloqueado por M2" para "M2 concluído — 2 finalistas (Zipformer+CTC, FastConformer+CTC), vencedor em M4"; tabela de bloqueios re-ancorada de "Bloqueado por M2" para "Bloqueado até M4", preservando a não-travagem (§ 0)

### Deprecated

### Removed

### Fixed

- Findings do `/review` de M3 (1 BLOCKER + 3 HIGH + 6 MEDIUM/LOW) corrigidos: o manifest agora aplica de fato o filtro por concordância (`filter_cutset` — antes incluía os cuts descartados, contradizendo a Goal); `pairwise_cer` não estoura mais quando uma hipótese é vazia (silêncio → discordância máxima); o relatório `[MEDIDO]` separa spread (±σ) de incerteza (IC95%) e reporta IC bootstrap de τ + hardware + comando exato; teste de sequencialidade dos modelos usa hooks de ciclo de vida em vez de `__del__` frágil (`knowledge-base/reviews/m3-corpus-review-2026-07-25.md`)

### Security

## [0.3.0] - 2026-07-25

### Added

- Decisão de arquitetura de M2 formalizada (`knowledge-base/adrs/0001-m2-architecture-finalists.md`): **Zipformer+CTC e FastConformer+CTC** nomeados como os 2 finalistas a pilotar em M4, com Moonshine-AED como braço de controle. Decisão por evidência medida — RTFx na CPU (n=10, com dispersão): Zipformer transducer 20M = 15,90 ± 2,06× vs Moonshine tiny 27M = 7,93 ± 0,72× (o transducer é ~2× mais rápido, com separação limpa; `knowledge-base/measurements/m2-rtfx-candidates.md`). LC-BiMamba descartado (ONNX inviável), Paraformer descartado (streaming como artefato separado). Vencedor NÃO travado — WER 8 kHz é o piloto de M4 (`knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md`, SHIPPABLE 100)

- Painel "Régua de medição (M1)" no dashboard de teste (`macaw-cli serve`): mostra a tabela de WER do baseline pt-BR (lida do relatório real) e um botão "Rodar benchmark rápido" que roda 10 iterações do encoder ao vivo e reporta RTFx + latência p50/p95/p99 com selo de aprovação/reprovação vs os alvos (RNF-07 ≥6×, RNF-02 p99 ≤500ms). Endpoints `/m1` e `/bench` em `std::net`, sem dependência nova (`crates/macaw-cli/src/app.rs`, `dashboard.html`)

### Changed

- `PRD.md` § 8 (filtro por concordância) passa a referenciar o entregável concreto de M3 (`scripts/corpus/`, blueprint + `m3-licenses.md`); a alegação Granary "~50% dos dados" registrada como hipótese a testar em M4, não premissa
- RTFx dos candidatos de M2 **re-medido com dispersão** (média ± desvio, min–max, n=10) em vez de só mediana, conforme a disciplina de evidência exige para `[MEDIDO]`. A re-medição na mesma clip (contagem de tokens idêntica) corrigiu a magnitude da vantagem do transducer de ~3× para **~2×** (Zipformer 15,90 ± 2,06× vs Moonshine tiny 7,93 ± 0,72×) — a diferença face à medição inicial é carga de CPU, o que reforça o soak sob carga em M4. A direção (transducer > AED) permanece com separação estatística limpa. Números propagados a ADR/blueprint/PRD; script + log salvos como evidência reprodutível (`knowledge-base/measurements/m2-rtfx-candidates.md`, `m2-rtfx-measure.py`, `m2-rtfx-run-2026-07-25.log`) (review F1)
- Rótulo de proveniência `[FONTE-REPO]` (fato lido no código de um peer clonado) **registrado formalmente** na disciplina de evidência (`.claude/rules/asr-evidence-discipline.md` § 1) — antes era usado nos artefatos de M2 sem definição no contrato. Exige citação `arquivo:linha` que exibe o fato; é mais forte que `[LITERATURA]` (fonte em disco, reproduzível) e mais fraco que `[MEDIDO]` (não roda experimento) (review F4)
- Disciplina de rotulagem dos artefatos de M2 endurecida após review: RTFx do FastConformer reclassificado de `[LITERATURA]` para `[ESTIMATIVA]` (analogia de decoder, encoders diferem); "diferença amplia para áudio longo" reclassificada para `[ESTIMATIVA]` com mecanismo; citações de streaming corrigidas para linhas que exibem o fato (`test_paraformer_streaming.py:13`, `zipformer.py:487/:573`); "7 tensores de cache" precisado para "7 categorias por encoder" (review F2/F3/STREAM-ADR-01/STREAM-ADR-02/BP-03)

### Deprecated

### Removed

### Fixed

- Teste de concorrência do servidor (`server_concurrency_test`) não é mais flaky: usava porta fixa 7391 (colidia sob `cargo test` paralelo/TIME_WAIT) e um bound de latência absoluto (1s, sensível a carga de CPU). Corrigido para porta efêmera (`bind` na porta 0) via novo `app::run_with_listener`, e asserção relativa (`/metrics` mais rápido que a duração do `/fixture` — prova de não-serialização load-independent) (`crates/macaw-cli/tests/server_concurrency_test.rs`, `crates/macaw-cli/src/app.rs`)
- Teste de custo de CPU do VAD (`vad_cost_test`) não é mais flaky sob `cargo test --workspace` paralelo: o gate usava o **máximo absoluto** de uma janela isolada (dominado por preempção do scheduler sob carga), reprovando intermitentemente com "3× real-time". Corrigido para basear o gate no **p99** (métrica de cauda robusta a outlier de amostra única, exigida por RNF-02); o máximo permanece como log `[MEDIDO]`. Validado 3/3 isolado + 2/2 no workspace sob carga máxima de CPU (`crates/macaw-audio/tests/vad_cost_test.rs`) (review CV-01)

### Security

## [0.2.1] - 2026-07-24

### Added

- Soak sustentado de M1 (RNF-04/05) medido de verdade (`scripts/bench.sh 3000 --load`, ~15 min sob carga concorrente de 10 cores, encoder preso aos P-cores): **RTFx sob carga 11,32×** (RNF-07 ✅), **latência p99 907ms** (RNF-02 ❌ — o encoder emprestado de 600M não sustenta a cauda sob carga, esperado), **razão térmica 2,09** (sem throttling em 15 min). A régua captou honestamente que o modelo emprestado viola RNF-02 sob carga (`knowledge-base/measurements/m1-harness-measurement.md`)

- Baseline de M1 completado para **3 modelos sobre pt-BR real** (`scripts/baseline_fleurs_ptbr.py`): FLEURS pt_br (português brasileiro, transcrição humana) degradado 16k→8k pela cadeia `telephone_augment.sh` (augmentação ponta-a-ponta), medido com faster-whisper base/small/medium — WER **21,3% / 9,6% / 4,5%** [IC95] (`knowledge-base/measurements/m1-baseline-report.md`). Resolve os achados de review CV-1 (1→3 modelos), CV-2 (augmentação exercitada no baseline) e CV-3 (pt-PT→pt-BR)

## [0.2.0] - 2026-07-24

### Added

- Harness de medição de M1 (`crates/macaw-audio/src/harness.rs`): `RtfxMeter` (RTFx sustentado com descarte de warmup), `LatencyHistogram` (p50/p95/p99 reusando o percentil de `metrics.rs`, janela limitada), `ThermalRatio` (RNF-04) e `SampleCounter` atômico — todos com erro tipado (`HarnessError`), sem panic. Modo `macaw-cli bench` como caller de produção + `scripts/bench.sh` que fixa os P-cores via `taskset` e gera carga concorrente sem `stress-ng` (medido: encoder emprestado 600M dá RTFx 17,81× sustentado vs 1,5× frio — o warmup importa; `knowledge-base/measurements/m1-harness-measurement.md`)
- Cadeia de augmentação telefônica 8 kHz em `sox` (`scripts/telephone_augment.sh`): 16k→8k + banda 300-3400 Hz + G.711 a-law round-trip, com teste determinístico de tolerância (8 kHz mono, atenuação > 3400 Hz, fail-fast em input inválido)
- Cálculo de WER com IC 95% via bootstrap por-utterance (`scripts/eval_wer.py`) reusando `jiwer` + normalizador PT-BR próprio (`scripts/text_normalize_ptbr.py`) — reporta sempre `WER [IC95: …]`, nunca ponto isolado (ataca o risco 1 de M1)
- Baseline sobre test set 8 kHz (`scripts/run_baseline.py` + `scripts/baseline_minds14.py`): orquestra o test set + WER, rejeita pseudo-label (invariante `PRD.md` § 7.3), emite relatório com rótulo `[MEDIDO]`. Medição real sobre minds14 pt-PT (fala telefônica bancária real 8 kHz nativa, transcrição humana): **WER = 73,0% [IC95: 49,8%–104,6%]** para faster-whisper-base, com bloco de proveniência (comando/hardware/seed/n_boot) e caveats honestos (pt-PT vs pt-BR, code-switching, modelo fraco = piso não teto, IC largo = risco 1) — `knowledge-base/measurements/m1-baseline-report.md`
- App web local de teste (`macaw-cli serve` + `scripts/app.sh`): dashboard no navegador que mostra ao vivo o roteamento de falante (você/cliente), saúde do sink, backlog e deriva, com botão para rodar o forward pass do encoder — servidor HTTP mínimo em `std::net`, sem dependência nova (`crates/macaw-cli/src/app.rs`, `dashboard.html`)
- Teste de regressão do servidor do app: sobe o servidor numa thread e prova que um endpoint lento (`/fixture`) não bloqueia os polls de `/metrics` (`crates/macaw-cli/tests/server_concurrency_test.rs`)
- Detecção de microfone mudo/baixo no app e no CLI: `check_source_health` + `evaluate_source_health` avisam quando a source padrão está muda ou com volume abaixo de 20% (medido: fala a volume baixo → RMS ≈ 0,0002, indistinguível de silêncio), a falha que o usuário viveu no teste — mic sem volume capta silêncio e a voz do atendente some sem erro visível. Aviso surge como banner no dashboard e na linha "Microfone (você)" (`crates/macaw-audio/src/capture.rs`, `crates/macaw-cli/src/app.rs`, `dashboard.html`)


### Fixed

- Gate `/discover-plan-confidence` dava INVALID para qualquer plano de descoberta: o arquivo `.claude/rules/discover-plan-thresholds.txt` (gerado pelo `roadmap-init`) declarava as bandas de verdict no formato `chave = valor`, mas o parser `_parse_thresholds` lê `TOKEN | valor` (split em `|`) — resultado: dicionário de bandas vazio e verdict INVALID mesmo com score 100/100. Corrigido o formato do arquivo para pipe, preservando os floors originais (90/70/50) e os tokens canônicos do `discover-plan-golden-rule.md`; nenhum hard cap foi afrouxado (`.claude/rules/discover-plan-thresholds.txt`)
- Gate `/code-quality` abortava com "languages.txt malformed line": o `.claude/rules/code-quality-languages.txt` (gerado pelo `roadmap-init`) tinha só `rust` bare, mas o parser espera `LANGUAGE | MANIFEST | STATUS | NOTES`. Corrigido o formato (`rust | Cargo.toml | ENABLED`), com `python` marcado `DEFER` (scripts cobertos por pytest, sem manifesto de pacote) (`.claude/rules/code-quality-languages.txt`)
- VAD de energia não disparava em áudio real de sistema: o ganho estava calibrado para o tom sintético da fixture (RMS ≈ 0,35) e exigia RMS ≈ 0,25, mas áudio real via loopback fica muito mais baixo (medido: vídeo do YouTube pelo monitor do sink → RMS ≈ 0,065), então era classificado como silêncio e o roteamento de falante não acendia o "Sistema". Ganho recalibrado de 2,0 para 15,0 (dispara em RMS ≈ 0,033) — heurística de M0, robustez real vem do Silero em M1 (`crates/macaw-audio/src/vad.rs`)
- App de teste congelava ao rodar o forward pass do encoder: o servidor HTTP era single-threaded e bloqueante, então carregar o encoder de 2,3 GB travava os polls de métricas e a UI inteira. Corrigido com thread por conexão, guard de single-flight no teste do modelo e cache do engine carregado (`crates/macaw-cli/src/app.rs`)

## [0.1.0] - 2026-07-24

### Added

- Walking skeleton de M0 implementado: workspace Rust de três crates (`macaw-audio`, `macaw-asr`, `macaw-cli`) com captura dual mic+loopback, VAD por stream, roteamento de falante, extração log-mel zero-alocação e forward pass do encoder ONNX de 600M sobre features reais — 34 testes passando, clippy limpo (`knowledge-base/implementations/m0-walking-skeleton-implementation.md`)
- Blueprint e plano de M0 aprovados com verdict SHIPPABLE nos gates de descoberta e de confiança de plano (`knowledge-base/discoveries/blueprints/m0-walking-skeleton-blueprint.md`, `knowledge-base/plans/m0-walking-skeleton-plan.md`)
- Evidência experimental de captura e de sincronia entre streams: loopback provado via libpulse, drift em regime medido como ≈ 0 com offset de partida constante de 1,44s (`knowledge-base/discoveries/m0-capture-probe-evidence.md`, `m0-drift-evidence.md`)
- Custo do VAD medido e resolvido de desconhecido: 3,32 µs média, 3,66 µs p99, 17,94 µs max no i7-1355U — 1784× real-time no pior caso (`crates/macaw-audio/tests/vad_cost_test.rs`)
- Escopo do projeto definido em `PRD.md`: modelo ASR PT-BR e motor de inferência em CPU, com 11 requisitos funcionais e 8 não-funcionais (`PRD.md`)
- Critério de aceite de "real-time verdadeiro" com cinco condições simultâneas — RTFx sustentado ≥ 3×, latência p99 ≤ 500 ms, backlog zero, estabilidade térmica ≥ 80% em 30 min, medição sob carga concorrente (`PRD.md` § 6)
- Arquitetura-alvo definida: encoder Zipformer streaming com decodificação CTC, monolíngue PT-BR, ~80M parâmetros, nativo em 8 kHz (`PRD.md` § 8.1)
- Suite de avaliação de fala espontânea PT-BR com recorte regional adotada como referência — NURC-Recife, NURC-SP, SP2010, ALIP, C-ORAL Brasil I, MuPe, CETUC (`PRD.md` § 7.3)
- Levantamento do estado da arte com 30+ referências classificadas por nível de verificação (`sota-techniques-asr-ptbr-cpu.md`)
- Registro das 15 decisões arquiteturais com racional e alternativas descartadas (`knowledge-base/grills/asr-ptbr-cpu-realtime-grill.md`)
- Plano de execução em cinco fases, começando por validação de premissa a custo zero (`PRD.md` § 9)
- Registro de riscos com oito itens rastreados e sete questões em aberto (`PRD.md` § 10, § 11)
- Pesquisa de arquiteturas alternativas ao eixo Conformer/Zipformer, runtimes Rust nativos e modelos de referência para edge (`deep-research-arquiteturas-alternativas.md`)

- Roadmap macro do projeto com 9 milestones (M0-M8), do walking skeleton ao piloto com atendentes reais (`ROADMAP.md`)
- Critério de ship do V1 definido: WER ≤ 25% no test set de call center 8 kHz, com os cinco critérios de real-time atendidos, sustentado por ~20 atendentes durante 4 semanas sem intervenção manual (`ROADMAP.md`)
- Métrica north-star definida: horas de áudio transcritas localmente por mês, com taxa de correção por minuto como guarda de qualidade (`ROADMAP.md`)
- Catálogo de 8 projetos de referência clonados para estudo, com licença, decisão de gate e mapeamento para milestones (`knowledge-base/references/_catalog.md`)
- Supervisão fonética auxiliar no treino, descartada na inferência: cabeça CTC de fonemas em camada intermediária, com custo zero em produção e ganho esperado de 10-20% relativo em WER (`PRD.md` § 8.1)
- Casamento de hotwords em espaço fonético para nomes próprios raros, requisito RF-08b (`PRD.md` § 8.2)

- Documento de entrada do projeto com roteamento de tarefa para agent e para skill de ciclo, estado travado da arquitetura e as regras invioláveis locais (`CLAUDE.md`)
- Responsáveis declarados por milestone: cada um dos nove milestones passa a nomear seus agents e, quando aplicável, a skill de ciclo que o conduz (`ROADMAP.md`)
- Time de doze agents especialistas cobrindo pesquisa ASR, dados e linguística PT-BR, inferência em CPU, sistemas/áudio/Rust, avaliação experimental e coordenação técnica (`.claude/agents/`)
- Disciplina de evidência como contrato compartilhado por todos os agents: rotulagem obrigatória de proveniência de cada número, separação entre hipótese, evidência e conclusão, e doze falácias que invalidam um artefato (`.claude/rules/asr-evidence-discipline.md`)
- Estado "discover contínuo" registrado como regra travada: nenhum agent escolhe encoder, decoder ou tamanho fora do ADR de M2, e o trabalho independente de arquitetura fica explicitamente liberado (`.claude/rules/asr-evidence-discipline.md` § 0)

### Changed

- Risco de volume de corpus promovido a bloqueante de nível 1: a receita de referência para modelos monolíngues pequenos usa 15.000-94.000 h por idioma, contra as 8.972 h atualmente disponíveis (`deep-research-arquiteturas-alternativas.md` § 1)
- Faixa de tamanho do modelo abandona o alvo fixo de ~80M e passa a ser varredura de três pontos (~30M / ~80M / ~123M) decidida por curva WER × RTFx medida, após benchmarks em CPU x86 mostrarem 165 ms para 123M (`deep-research-arquiteturas-alternativas.md` § 5.2)
- Arquitetura do modelo marcada como **pendente**: encoder, decoder e tamanho passam a ser resultado de um ciclo de descoberta seguido de piloto comparativo, com cinco candidatos e oito critérios de decisão fixados previamente (`PRD.md` § 8.1)
- Decoder e word spotter removidos da fase de trabalho independente de arquitetura — ambos dependem da escolha de decodificação (CTC, autorregressivo ou recorrente) e aguardam a decisão (`PRD.md` § 8.2, § 9)
- DoD de M0 corrigido: o critério de transcrição real-time de 5 minutos foi movido para M5/M6, por ser estruturalmente impossível com o modelo emprestado de 600M offline — impossibilidade que é a própria premissa do projeto; M0 prova o encanamento features→modelo (`ROADMAP.md` M0, `knowledge-base/discoveries/m0-borrowed-model-dod-analysis.md`)
- Claude Code passa a operar sem prompts de permissão neste repositório: `defaultMode` vira `bypassPermissions` e as listas `deny`/`ask` foram removidas a pedido do dono do projeto; os hooks de segurança (git-safety, boundary-check, stop-validation) seguem ativos e continuam sendo a única barreira automática (`.claude/settings.json`)

### Fixed

- Corrigida extrapolação indevida que sustentava a escolha de Zipformer com benchmarks de CPU medidos em arquitetura Moonshine — modelos sem parentesco arquitetural (`PRD.md` § 8.1)
- Corrigida rejeição de decoder autorregressivo baseada no desempenho do Whisper: a lentidão decorre da janela fixa de 30 s e de 1,5B parâmetros, não da arquitetura encoder-decoder (`PRD.md` § 8.1)

### Changed

- Corpus de treino definido como TAGARELA (8.972 h, 91% PT-BR), substituindo o conjunto CORAA + MLS + Common Voice previsto na pesquisa inicial (`PRD.md` § 8.3)
- Domínio de áudio fixado no padrão de call center brasileiro — 8 kHz banda estreita, G.711 a-law, filtro 300-3400 Hz — substituindo a premissa inicial de banda larga 16 kHz (`PRD.md` § 4)
- Alvos de WER recalibrados para 15-25% em call center 8 kHz, substituindo o alvo inicial de < 10% que comparava benchmarks não equivalentes (`PRD.md` § 7.1)
- Decisão de treinar o modelo do zero em vez de comprimir um checkpoint multilíngue existente, por preservação de capacidade dedicada ao PT-BR (`PRD.md` § 8.1)

### Fixed

- Correções do review pré-merge de M0 (dois BLOCKERs + quatro HIGH): caminho absoluto no `.cargo/config.toml` trocado por relativo (build reprodutível); detecção de sink mudo e medidor de deriva ganharam caller de produção no CLI, com teste de integração provando o caminho; RTF do encoder remedido com aquecimento e n=10; histórico de métricas limitado a janela deslizante para não crescer sem limite em chamada longa (`knowledge-base/reviews/m0-walking-skeleton-review-2026-07-24.md`)

### Removed

- Módulo `ring::SampleRing` removido: código morto apontado no review — construído e testado isolado, nunca integrado ao pipeline, que usa canal mpsc (`knowledge-base/reviews/m0-walking-skeleton-review-2026-07-24.md`)
- Três exports públicos órfãos removidos na auditoria de code-quality de M0, por YAGNI: `AsrEngine::with_vocab`, `AsrEngine::vocab_len` (vocabulário é decode, bloqueado por M2) e `DriftMeter::latest_drift_ms` (redundante com `record` + `history`) (`knowledge-base/audits/m0-walking-skeleton-code-quality.md`)
- CORAA excluído do plano de dados: a licença CC-BY-NC-ND proíbe obras derivadas, o que inviabiliza treino (`PRD.md` § 8.3)

### Security

- Risco de licença do corpus TAGARELA (CC-BY-NC-SA-4.0, não-comercial e ShareAlike) formalmente registrado e assumido em 2026-07-24, com o caminho de saída documentado (`PRD.md` § 8.3)
- Dependência de compliance LGPD registrada como risco R2: mascaramento de PII no dispositivo pode consumir orçamento de CPU já dimensionado (`PRD.md` § 10)
