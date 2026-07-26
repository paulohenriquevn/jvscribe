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

### Added

- **M6 runtime v0 — TRANSCRIÇÃO DE FALA REAL validada `[MEDIDO]`** (`crates/macaw-asr/tests/real_speech_test.rs`): o runtime Rust (ctc_logits→ctc_greedy→detok) decodifica um utterance real do FLEURS test (features corretas do lhotse) → **86% word-overlap** com a referência ("após o acidente gibson foi movido para um hospital mas morreu pouco tempo depois" → só 2 palavras foneticamente próximas erradas). **Prova end-to-end que o decode está 100% funcional em fala real.** O único gap para o demo wav→texto é o fbank do macaw-audio (128-bin NeMo vs 80-bin icefall, task #25), NÃO o decode
- **M6 runtime v0 Fase 2 — inferência do modelo real em Rust `[MEDIDO]`** (`crates/macaw-asr/src/lib.rs`): `AsrEngine::ctc_logits()` + `transcribe()` rodam o contrato REAL do nosso ONNX icefall (`x`(1,T,80)/`x_lens`→`log_probs`), corrigindo o achado do deep-review (o `encode()` de M0 era placeholder NeMo com nomes errados que só devolvia o shape). Teste de integração no `model.int8.onnx` real: 60 frames → T=13 (subsampling 4× do Zipformer), vocab=500, pipeline logits→greedy→detok roda sem erro (`tests/transcribe_smoke_test.rs`). ADR-1: adicionar, não mudar `encode()` (11/11 testes do crate verdes). Falta a Fase 3 (wav→texto com features casadas) para provar transcrição de fala real
- **M6 runtime v0 — decoder CTC greedy em Rust `[MEDIDO]`** (`crates/macaw-asr/src/decode.rs`): implementado o `ctc_greedy` (argmax por frame + colapso blank/repetição, portado de sherpa-onnx `offline-ctc-greedy-search-decoder.cc:42`, Regra 9) + `detok` BPE (▁→espaço) + `argmax`. Domínio puro (sem ONNX), fail-safe a entrada curta. **5/5 testes fixture verdes** (`tests/ctc_decode_test.rs`), clippy limpo, 57 LoC. Fase 1 do plano `m6-runtime-v0` (CYCLE de M6: discover SHIPPABLE → plan SHIPPABLE 100 → implement). Zero dep nova

- **M6 early (real-time de-risk com o modelo atual)** — `training/bench_rtfx.py --soak-min N`: modo soak que roda o int8 continuamente por N min na i7-1355U, logando RTFx por janela de 30s para revelar throttle térmico (RNF-04 exige RTFx sustentado ≥ 80% do pico ≥ 10 min). Iniciado M6 com o Zipformer-CTC small que já temos, conforme decisão do dono (2026-07-26): valida os critérios de real-time que NÃO dependem de M5. Nota honesta: soak/carga/int8 são validáveis já; a latência p99 streaming (RNF-02) + equivalência batch≡streaming exigem um modelo causal (`train --causal 1`), que fica para quando um GPU liberar

- **M4 fase 4 — corpus NeMo p/ o 2º finalista** (`training/prep_nemo.py`): converte o MESMO corpus (MLS-PT 161h train + FLEURS dev/test) para o formato de manifest do NeMo (`{audio_filepath, duration, text}`), reusando `prepare_mls` + o build do FLEURS (Regra 9) — comparação justa FastConformer-CTC vs Zipformer-CTC no mesmo test. Testes: `training/tests/test_prep_nemo.py`. Instância NeMo (imagem `nvcr.io/nvidia/nemo:24.12`) provisionada
- **M4 fase 5 — RTFx na CPU-alvo `[MEDIDO]`** (`training/bench_rtfx.py`): export do small para ONNX int8 (27MB) + benchmark na **i7-1355U de referência** → **RTFx 41-68× a 1 thread / 49-90× a 2 threads**, contra o piso de **≥6× (RNF-07)** = **7-15× de folga**. Fecha o eixo decisivo do objetivo CPU: o small tem margem enorme para tempo real. Régua reutilizável testada. Caveats: offline (não streaming), clip único (não soak RNF-04). Testes: `training/tests/test_bench_rtfx.py`
- **M4 — experimento de penalidade telefônica** (`training/make_telephone_test.py`, recomendado pelo `asr-chief-scientist`): degrada o held-out FLEURS pela cadeia telefônica do M3 (banda 300-3400 Hz + G.711 A-law, reusa `scripts/corpus/telephone_channel.py` — Regra 9) e re-decodifica o checkpoint de 161h JÁ treinado — mede o multiplicador do domínio 8 kHz **sem treinar nada**, atacando o maior risco identificado (o alvo é 8 kHz telefônico, o WER medido era wideband limpo). Testes: `training/tests/test_make_telephone_test.py`
- **M4 fase 2 — curva WER×tamanho em 161h `[MEDIDO]`:** small (22M) = **29,97%** vs medium (64M) = **28,86%** (avg=10, held-out FLEURS). **Retornos decrescentes fortes: 3× os params compram só −1,1 p.p.** — regime data-bound, favorece o `small` para o objetivo CPU real-time (quase o mesmo WER a fração do compute). large (147M) treinando p/ completar a curva do DoD
- **M4 fase 2 — PRIMEIRO WER real em 161h `[MEDIDO]`:** Zipformer-CTC **small (22,1M)** treinado 30 épocas em MLS-PT 161h → **WER held-out (FLEURS) = 29,97%** (avg=10) / 33,99% (avg=1). **Salto de 96% (piloto 10h) → 30% (161h)** confirma plenamente a tese data-bound (o gargalo é corpus, não arquitetura — PRD R9). Modelo saudável (74% das palavras corretas, erros balanceados, não o colapso-para-blank do piloto). Model-averaging **inverteu como a teoria prevê**: no run convergido (val loss 0,23) o avg **ajuda** (ao contrário do piloto não-convergido onde degenerava). Evidência: `training/results/m4-decision-161h-results.md`. Medium/large treinando na sequência
- **M4 fase 2 — orquestração de treino** (`training/run_zipformer_ctc.sh`): train+decode de UM tamanho Zipformer-CTC no corpus `data/pt`, encapsulando o conhecimento do piloto (lang-dir completo com `tokens.txt`, `--enable-musan 0`, decode sem averaging cego — testa avg=1 e avg=10, o melhor vence). Flags dos 3 tamanhos (small 22M / medium 64M / large 147M) copiados do `RESULTS.md` do icefall (Regra 9). Uso: `bash run_zipformer_ctc.sh <small|medium|large>`
- **M4 fase 1 — corpus de decisão** (`training/prep_mls.py`): monta o corpus para comparar as arquiteturas com dado adequado — **train = MLS-PT ~161h** (CC-BY, humano) via `lhotse.recipes.prepare_mls` (Regra 9 — a recipe do lhotse lê o layout OpenSLR tar/opus, não reimplementamos), **dev/test = FLEURS held-out humano** (mesmo test set do piloto, para comparação justa). Emite `cv-pt_cuts_{train,dev,test}` no formato do datamodule real do icefall; reusa `normalize_ptbr`/`build` do `prep_icefall` sem duplicar (audit D2). Testes de contrato: `training/tests/test_prep_mls.py`. Decisão do dono (2026-07-25): corpus CC-BY limpo ~161h (não ~500h pseudo-labelado) — suficiente para ranquear as 2 arquiteturas
- **Piloto FLEURS-only de M4 executado na recipe REAL do icefall (vast.ai RTX 3090, ~$0,22 `[MEDIDO]`):** Zipformer-CTC small (22,1M params, CTC puro) treinado 30 épocas do zero em FLEURS pt_br (~10h) → decode `ctc-greedy-search` no held-out. **WER test = 96,52% `[MEDIDO]`** (train 95,19% — train≈test ⇒ **underfit/colapso-para-blank**, não overfit; contraste com o smoke de 1h que overfitou). Throughput **41,9s/época `[MEDIDO]`**. Achado metodológico: model-averaging (avg-15) sobre trajetória não-convergida **degenera** o modelo (100% vazio) — sem averaging = 96,52%. Prova o pipeline ponta-a-ponta na recipe real (os 757 corretos provam que o decode não tem bug); confirma a tese data-bound (10h é insuficiente; TAGARELA/M5 é a resposta). **NÃO decide o finalista de M4** (1 finalista, dados mínimos, sem RTFx). Evidência: `training/results/m4-pilot-fleurs-results.md` + logs. Decoder adaptado (librispeech→commonvoice, Regra 9): `training/patch_ctc_decode.py`
- Adaptador de dados `training/prep_icefall.py` — emite o corpus multi-fonte (FLEURS + MLS-PT, ~161h+) no formato EXATO que o datamodule real do icefall carrega (`cv-{lang}_cuts_{train,dev,test}.jsonl.gz` + fbank). É o único código nosso para o piloto; o treino/loss/model vêm da recipe real do icefall (Regra 9). Runbook: `training/run_pilot_icefall.md`. Aguarda crédito GPU (~$50) para o piloto real. Testes determinísticos da parte pura (normalização PT-BR preserva diacríticos + estrutura das fontes): `training/tests/test_prep_icefall.py` (7 casos); flag `--limit` para smoke local do gerador de cuts

- Pipeline de treino de M4 (`training/`): `prep_fleurs` (FLEURS pt_br → manifests Lhotse + fbank), `gen_phonemes` (alvos fonéticos G2P), `train_ctc` (Zipformer-CTC do zero + cabeça de fonema auxiliar — reusa os módulos do icefall, CTC via torch), `decode_ctc` (WER greedy). **Provado end-to-end numa GPU real** (vast.ai RTX 3090, imagem oficial `k2fsa/icefall`, ~$0,35): treina, converge, decoda, produz WER `[MEDIDO]`. Achado honesto: o smoke (1 h de corpus) overfita — WER held-out ~95%+; a ablação da supervisão fonética é inconclusiva nesse volume, só testável no piloto de ~500 h (`training/results/m4-smoke-results.md`, `knowledge-base/implementations/m4-pilot-implementation.md`)

- Blueprint de discovery de M4 (piloto comparativo) — `knowledge-base/discoveries/blueprints/m4-pilot-blueprint.md` (SHIPPABLE 100). Deep research de 3 agentes (asr-chief-scientist, ptbr-phonetics-scientist, ml-infra-engineer) respondeu 8 questões: recipe icefall Zipformer-CTC (train.py paramétrico, 3 tamanhos por escala), **G2P PT-BR medido** (cobertura/determinismo 100% sobre FLEURS pt_br, mas GPLv3 — só treino offline; PER absoluto `[DESCONHECIDO]`), e a **estimativa de custo com fórmula**: piloto ~$98-200, M5 completo ~$1.350-2.000/run. Achados que reenquadram M4: a supervisão fonética NÃO existe pronta na recipe (só CTC de subword — exige construir a cabeça de fonema); k2 é incompatível com o torch instalado (treino exige imagem GPU separada)

### Changed

- **Limpeza de `training/` pós-audit `/loop-system-design`** (relatório: `knowledge-base/audits/2026-07-25-training-system-design.md`, score 3,5/5, 0 críticos/altos): o **cluster smoke** (`train_ctc.py`, `decode_ctc.py`, `prep_fleurs.py`, `gen_phonemes.py`) foi movido para `training/smoke/` (quarentena) — remove o risco de copy-paste ao lado do único código de produção `prep_icefall.py` (findings B1/D3) e resolve a duplicação/drift do `normalize_ptbr` (D2) deixando a produção com uma cópia só. `prep_icefall.py`: removidos imports mortos `numpy`/`glob` (D4) e parametrizado `--num-jobs` para o prep de ~500h de M5 (SC1). ADR sugerido (formaliza a decisão Regra-9 de reusar a recipe): `knowledge-base/audits/000X-m4-reuse-icefall-recipe.md`
- **Correção de rumo em M4 (honestidade):** o `train_ctc.py` (wrapper self-contained) foi rebaixado a SMOKE ONLY — tem bug confirmado contra a recipe real do icefall (não passa `src_key_padding_mask` ao encoder → atende frames de padding) + cabeça de fonema ad-hoc + configs por escala. O smoke overfitou (WER treino 18% vs held-out 99%), o que mascarou os defeitos. O **piloto de 500 h passa a usar a recipe REAL do icefall** (`train.py`/`model.py`/`asr_datamodule.py`, `--use-ctc 1 --use-transducer 0`) sem reescrever loop/loss/model (Regra 9) — runbook em `training/run_pilot_icefall.md`

### Deprecated

### Removed

### Fixed

- **M6 runtime v0 — fixes do `/review` (4 agentes, verdict NEEDS_FIXES)** em `crates/macaw-asr/`: (T-01) adicionado o teste da semântica CENTRAL do CTC — repetição separada por blank não colapsa (`[1,0,1]→[1,1]`), regressão que pega qualquer quebra de `decode.rs:41`; (T-02) os testes de integração (`transcribe_smoke`, `real_speech`) faziam `return` reportando PASSED quando o fixture falta (verde-fictício no CI) → agora `#[ignore]` honesto (listados como IGNORED, rodam com `--ignored`); (T-03/04) casos negativos dos erros tipados `Vocab::load`→`VocabNotFound`/`InvalidVocab` e `AsrEngine::load`→`ModelNotFound`, e `detok` de id fora do range (descarte silencioso documentado como contrato); (T-05/06/07/08) argmax/detok um comportamento por teste + fixture temp único por processo + bordas (NaN, empate, `vocab==0`, `t_len==0`, `blank!=0`); (ARCH-02) blank id `0` mágico → `const ICEFALL_BLANK_ID`; (ERR-01) comentário do fail-safe de `ctc_greedy` corrigido (é guarda de bounds, não mandato de `error-handling.md`). Cobertura do decode: 5→20 testes de unidade. Workspace: 63 passed / 2 ignored, clippy `-D warnings` limpo. Review: `knowledge-base/reviews/m6-runtime-v0-review-2026-07-26.md`. **Pendente (não-fabricado):** Fase 3 (wiring wav→texto no macaw-cli + métrica) segue bloqueada pela task #25 (fbank 128→80-bin)
- **Code-quality skill — detector Rust D2 gerava 98 falso-positivos de "symbol fabrication"** (`.claude/skills/code-quality/scripts/detectors/rust.py`): ao rodar o gate no workspace Rust, o detector marcava como "crate fabricado" (HARD → FAIL_HARD) todo `use` de (a) stdlib do Rust (`std`/`core`/`alloc`, 57×), (b) crates internos do próprio workspace Cargo (`macaw_asr`/`macaw_audio`/`macaw_cli`, 40×) e (c) imports com alias `use x as y` (o ` as y` poluía o nome do crate, 1×) — nenhum é fabricação de símbolo. Corrigido: pular a stdlib, ler os nomes de package dos `Cargo.toml` do workspace para não acusar membros locais, e tirar o ` as <alias>` antes de consultar crates.io. Resultado: 98 → 0 falso-positivos, verdict FAIL_HARD → limpo no eixo D2 (cross-check `cargo machete`: zero deps mortas). TDD: 3 testes de regressão em `.claude/skills/code-quality/tests/test_rust_detector.py` (105/105 do skill verdes)
- `training/run_zipformer_ctc.sh` (2 bugs pegos no run do small): o decode chamava `./zipformer/ctc_decode.py` (permission-denied, pois o `patch_ctc_decode.py` escreve sem +x) → agora `python3 ./...`; e o guard do lang-dir olhava `tokens.txt` (que existe sem o lang completo) → agora olha `L.pt`, o artefato final do `prepare_lang_bpe`
- `training/prep_mls.py` (2 bugs descobertos rodando na instância): `corpus_dir` passado ao `prepare_mls` é o **parent** que contém `mls_portuguese_opus/` (o recipe faz `corpus_dir.glob("mls_*")`), não o dir do idioma; e a estrutura de retorno é `manifests[lang][split]` (lhotse `mls.py:94,133`), não `[split][lang]`. Adicionado `output_dir` de cache para re-runs não re-escanearem os opus
- `training/prep_icefall.py`: `_download` agora cria o `PARQUET_DIR` antes do `curl` (o `curl -o` falhava com exit 23 "write error" quando o diretório não existia — descoberto ao rodar o piloto real na vast.ai) e usa `curl -sfL` (`-f`: falha explícita em HTTP 4xx/5xx em vez de gravar página de erro como se fosse parquet). Teste de regressão em `training/tests/test_prep_icefall.py` (`test_download_cria_pqdir_antes_do_curl`)

### Security

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
