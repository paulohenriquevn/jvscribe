---
slug: m5-8khz-telephone-wer
milestone_id: M5
created_at: 2026-07-29
goal: Reduzir o WER 8 kHz telefônico mono-falante do finalista M5 para ≤25% (IC95%) via fine-tune gentil com augmentação de codec realista + n-gram LM.
---

# Plan: WER 8 kHz telefônico ≤25% (fine-tune gentil + codec-pool + LM)

> **Version 1.0** — Fecha o DoD#3 de M5 (telefônico 8 kHz ≤25%), hoje em aberto: o baseline
> honesto no canal real é **40,13% [MEDIDO]** (o proxy bandpass 31,97% subestimava). A causa
> dominante é confusão acústica (substituições 23,7%, TM#1), atacada pela **augmentação de codec
> realista** (o modelo foi treinado só com G.711 A-law, o codec mais inócuo) num **fine-tune
> gentil corrigido** (a continuação D2 anterior colapsou por LR alto + choque de augmentação),
> medido na condição **certa** (mono-falante real-codec) e complementado por **n-gram LM** no
> decode. Resultado esperado: WER 8 kHz mono-falante ≤25% com IC95%, sem regredir o wideband.

## Goal

> "Permitir que o modelo finalista M5 (Zipformer-CTC medium 64M) transcreva fala telefônica
> 8 kHz mono-falante com **WER ≤ 25% (IC95%)**, medido por `measure_callcenter.py` sobre o test
> CORAA mono-falante degradado por codec realista, sem regredir o WER wideband (≤ 24%)."

## Context

M4 fixou a arquitetura (ADR 0003, medium 64M+fonema). M5 entregou o modelo (wideband 23,31%
[MEDIDO], RTFx 34×), mas o **DoD#3 (telefônico 8 kHz ≤25%)** ficou em aberto. A 1ª tentativa de
fechá-lo — a continuação "D2" (fine-tune full com augmentação on-the-fly, base-lr 0,006, fp32,
warm-start de checkpoint médio) — **colapsou o modelo** (near-blank, WER ~98% em wideband e
telefônico [MEDIDO]; `avg_124_112` no mesmo ambiente = 22,09%, provando que não foi ambiente).

Um deep-research (3 cientistas do time) + testes de mesa produziram o blueprint
`knowledge-base/discoveries/blueprints/m5-8khz-telephone-wer-blueprint.md`, cujas decisões D1–D5
este plano executa. Descobertas-chave: (a) medíamos a condição errada — produção é mono-falante
por canal; (b) a augmentação usava o codec mais inócuo (G.711), não os que transferem (GSM/AMR/
Opus); (c) o colapso do D2 veio de LR alto + augmentação a 100% num modelo convergido.

## Baseline Context (deep review of current state)

### Files that will be touched

| File | LoC today | Last commit (sha + date) | Why it exists today | Invariants to preserve |
|---|---|---|---|---|
| `scripts/corpus/telephone_channel.py` | 75 | `6f14c7d` (2026-07-25) | Cadeia telefônica on-the-fly em RAM: resample 16k→8k, banda 300-3400 Hz, **G.711 A-law fixo** | Não materializar WAV em disco (DoD M3 item 3); manter a assinatura in-RAM; float [-1,1] entra e sai |
| `scripts/corpus/telephone_channel_transform.py` | 206 | `276ab09` (2026-07-29) | Adapter lhotse on-the-fly que aplica a cadeia num dataloader | Interface de transform lhotse (`__call__` sobre cut/samples); determinismo sob seed |
| `scripts/tests/test_telephone_channel_transform.py` | 178 | `276ab09` (2026-07-29) | Testes do adapter | AAA; determinístico |
| `scripts/tests/test_corpus_telephone.py` | — (existe) | — | Testes da cadeia G.711 | idem |
| `training/measure_callcenter.py` | 112 | `d25cb17` (2026-07-29) | Mede WER em áudio real 8 kHz (segmenta por transcrição humana, jiwer) | Dado local (LGPD); genérico por argumento |
| `training/tests/test_measure_callcenter.py` | 43 | `d25cb17` (2026-07-29) | Testes do parser/normalizador do medidor | pura, sem I/O |
| `scripts/corpus/codec_pool.py` (NEW) | 0 | — | (a criar) pool de codecs realistas via ffmpeg/torchaudio | — |
| `scripts/tests/test_codec_pool.py` (NEW) | 0 | — | (a criar) testes do pool de codecs | — |
| `training/build_realcodec_testset.py` (NEW) | 0 | — | (a criar) gera test CORAA mono-falante degradado por codec | — |
| `training/tests/test_build_realcodec_testset.py` (NEW) | 0 | — | (a criar) testes do builder | — |
| `training/ctc_lm_decode.py` (NEW) | 0 | — | (a criar) prefix-beam CTC + n-gram LM shallow-fusion | — |
| `training/tests/test_ctc_lm_decode.py` (NEW) | 0 | — | (a criar) testes do decoder LM | — |
| `training/run_ft_codec.sh` (NEW) | 0 | — | (a criar) runbook do FT gentil corrigido (instância) | — |

### Current callers / dependents

- **Símbolo:** `telephone_channel` / cadeia em `scripts/corpus/telephone_channel.py`
  - **Callers (produção):** `scripts/corpus/telephone_channel_transform.py` (adapter on-the-fly)
  - **Callers (testes):** `scripts/tests/test_corpus_telephone.py`, `scripts/tests/test_telephone_channel_transform.py`
  - **External (consumido por outro repo):** não — uso interno do pipeline de treino.
- **Símbolo:** `parse_transcript`/`normalize`/`greedy` em `training/measure_callcenter.py`
  - **Callers (testes):** `training/tests/test_measure_callcenter.py`
  - **External:** não.
- Enumeração via `grep -rln`; a cadeia telefônica só é consumida pelo adapter (grep confirmou 1 caller de produção).

### Domain glossary

- **Codec tandem** — encadear >1 codec (ex.: AMR no celular → G.711 no gateway); degrada mais que single-pass.
- **Shallow fusion** — somar `log p_AM + α·log p_LM` no decode (n-gram), sem re-treinar o AM.
- **Bandwidth-embedding** — feature auxiliar (ex.: flag "é telefônico") concatenada ao input p/ o modelo condicionar a banda.
- **Peaky/blank collapse** — regime em que o CTC emite quase só blank (atrator trivial); foi o modo de falha do D2.
- **Curriculum (de augmentação)** — subir a probabilidade/severidade da augmentação ao longo das épocas, não ligar tudo de golpe.

### Architecture boundaries affected

Toca a camada de **preparação de corpus** (`scripts/corpus/`) e **treino/avaliação** (`training/`).
Não cruza fronteiras do runtime Rust (M6). Respeita `.claude/rules/architecture.md § 3` (módulos
coesos: o pool de codecs é um módulo próprio, não incha `telephone_channel.py`). Respeita a Regra 9
(`parsimony-ladder.md` rung 4): reusar ffmpeg/torchaudio, não reimplementar codecs.

## Prior Art & Related Work

- **Internal blueprint:** `knowledge-base/discoveries/blueprints/m5-8khz-telephone-wer-blueprint.md`
  § "Ranking unificado de alavancas", § "Testes de mesa (2026-07-29) e decisões" (D1–D5),
  § "Divergência entre cientistas" (8kHz-nativo refutado).
- **Reference projects (`knowledge-base/references/`):** icefall `egs/librispeech/ASR/zipformer_adapter/`
  e `zipformer/optim.py:841-900` (scheduler Eden — porquê o warm-start de avg reinicia no pico de LR);
  `docs/source/recipes/Finetune/from_supervised/finetune_zipformer.rst` (LR de FT ≈ 1/10);
  `lhotse/features/kaldi/extractors.py` (FbankConfig sr=16000).
- **External literature:** Vu et al., *Audio Codec Simulation based Data Augmentation for Telephony
  ASR* (APSIPA 2019) — HighDC/MixCodec reduz 7–13 pp; Zeyer/Zhou et al., *Why does CTC result in
  peaky behavior?* (arXiv:2105.14849) — atrator de blank; Li et al./Microsoft, *Improving Wideband
  ASR using Mixed-Bandwidth Training* (ICASSP 2013) — bandwidth-embedding +13% rel NB.
- **Projeto:** `.claude/rules/asr-evidence-discipline.md` (rótulos), `.claude/rules/testing.md`
  (TDD/pytest), `.claude/rules/parsimony-ladder.md` (Regra 9).

## Objective

- [ ] Sub-goal 1 — Pool de codecs realistas (`codec_pool.py`) integrado à cadeia telefônica, com p-gate e amostragem por-stream, testado.
- [ ] Sub-goal 2 — Test CORAA **mono-falante real-codec** construído e o modelo entregue medido nele com IC95% (a métrica âncora D1).
- [ ] Sub-goal 3 — Decoder prefix-beam CTC + n-gram LM (shallow fusion) numpy-safe, testado, medindo ganho relativo.
- [ ] Sub-goal 4 — FT gentil corrigido (single-ckpt, LR 0,002, warmup 4000, `--use-mux 1`, codec-pool p=0,5 curriculum, +bandwidth-embedding) executado sem colapso (blank-rate monitorado).
- [ ] Sub-goal 5 — WER 8 kHz mono-falante do modelo FT medido ≤25% (IC95%) com wideband ≤24% — o Goal.

## ADRs

### D1 — Métrica âncora = CORAA mono-falante + codec realista

**Decisão:** medir o DoD#3 no test CORAA humano (mono-falante) degradado pelo codec-pool.

**Rationale:** produção é 1:1 canais separados (mono-falante); o proxy bandpass (31,97%) é otimista e o call mono-misto (40,13%) é mais difícil que produção; CORAA humano dá N grande → IC estreito. **Alternativa rejeitada:** manter o bandpass-proxy — subestima (falácia § 3 #6); usar só o call mono-misto — condição errada + IC largo com 9 min.

**Consequences:** mede a condição de deploy; exige um builder de test degradado.

### D2 — FT gentil corrigido (não full-FT agressivo)

**Decisão:** base-lr 0,002, warmup 4000, single-ckpt warm-start (não avg), `--use-mux 1`, codec p=0,5 em curriculum.

**Rationale:** o D2 anterior colapsou (near-blank) por LR 0,006 + avg (Eden reinicia no pico) + augmentação 100% (atrator de blank, arXiv:2105.14849; icefall FT ≈ 1/10 do LR). **Alternativa rejeitada:** full-FT como o D2 — colapsou (medido); adapter/LoRA (encoder congelado) — plano B se o FT gentil ainda colapsar (menor risco, menor teto).

**Consequences:** menor risco de colapso; preserva o wideband via mux.

### D3 — Augmentação de codec-pool (não G.711 fixo)

**Decisão:** pool ponderado {G.711 μ/a (audioop, tier brando), GSM-FR + Opus baixo-bitrate (tier agressivo); AMR-NB quando `libavcodec-extra`}.

**Rationale:** G.711 é o codec mais inócuo (APSIPA 2019); os agressivos transferem (+7–13 pp). **Alternativa rejeitada:** manter G.711 fixo — é o platô medido; só um codec agressivo — Málek: misturar vários generaliza melhor.

**Consequences:** nova dependência de processo (ffmpeg) ou torchaudio (na instância).

### D4 — Tooling de codec = torchaudio `AudioEffector` + audioop + ffmpeg offline

**Decisão:** `AudioEffector` (on-the-fly) + audioop (G.711 in-RAM) + ffmpeg (offline no builder).

**Rationale:** Regra 9 (não reinventar codec); `AudioEffector` é in-process (bom p/ dataloader); `apply_codec` está deprecado; audioop já cobre G.711 in-RAM. **Alternativa rejeitada:** ffmpeg subprocess por-amostra no treino — lento, I/O em disco; reimplementar GSM/Opus — Regra 9.

**Consequences:** torchaudio precisa estar na instância (está — icefall usa); local só p/ eval offline.

### D5 — LM = n-gram (KenLM) shallow-fusion numpy-safe (NÃO pyctcdecode)

**Decisão:** prefix-beam próprio + KenLM via kaldilm/subprocess, isolando o numpy.

**Rationale:** pyctcdecode+kenlm já corrompeu o numpy neste projeto; icefall usa kaldilm/KenLM; n-gram cabe no CPU (RTFx folga); ganho 10–15% rel em áudio difícil. **Alternativa rejeitada:** pyctcdecode — quebrou numpy (medido); LM neural rescoring — caro/arriscado p/ real-time.

**Consequences:** isola o risco de dependência; decoder prefix-beam próprio testável.

### D6 — Bandwidth-embedding auxiliar (feature "é telefônico")

**Decisão:** concatenar uma feature auxiliar de banda ao input no FT.

**Rationale:** +13% rel NB sem degradar WB (Li et al.), custo CPU ~zero. **Alternativa rejeitada:** 8kHz-nativo fewer-bins — divergência resolvida (convenção pré-E2E; icefall/ESPnet SWBD fazem upsample+80bins); nada — perde alavanca barata.

**Consequences:** muda a dim de entrada no treino/inferência do FT (documentar; não afeta o M5 já entregue).

## Drawbacks & Risks

| Drawback / Risk | Severity | Mitigation | Owner |
|---|---|---|---|
| O FT gentil pode ainda colapsar (blank) sob augmentação | Alta | Monitor de blank-rate por época (early-stop); plano B adapter/LoRA (D2 alt.); começar p baixo em curriculum | ml-infra |
| O DoD ≤25% pode não ser alcançável só com estas alavancas | Média | Medir cada alavanca isolada; se platôar acima de 25%, escalar para dado real 8 kHz (blueprint #7/#8) | asr-chief |
| `libavcodec-extra` (AMR) pode não instalar na instância | Baixa | AMR é opcional; pool funciona com G.711/GSM/Opus (todos no ffmpeg padrão) | audio-dsp |
| Test de 9 min do call center tem IC largo | Média | Métrica âncora vira CORAA real-codec (N grande); o call é stress-test secundário | eval |
| torchaudio na instância pode tocar numpy (histórico de quebra) | Média | Não instalar/atualizar torchaudio com treino ativo; validar import antes | ml-infra |

## Unresolved Questions

- Q1 — A augmentação de codec deve ser aplicada por-stream (só cliente) ou a todo áudio de treino? (D4 do blueprint deixou em aberto; o treino atual é mono — decidir no T1.2.)
- Q2 — O bandwidth-embedding vale o custo de mudar a dim de entrada do artefato exportado? (medir T4 vs sem embedding.)
- Q3 — Qual peso α do LM (shallow fusion) minimiza WER no dev real sem overfit ao dev de 9 min?
- Q4 — Quantas horas de FT (épocas) até o WER 8 kHz platôar? (`[DESCONHECIDO]` até T4.)

## Dependency Graph

```
Phase 1 (codec-pool, CPU) ──▶ Phase 2 (real-codec eval, CPU) ──▶ Phase 5 (medição/verdict)
        │                              │                                  ▲
        │                              ▼                                  │
        └────────────────────▶ Phase 4 (FT gentil, GPU) ─────────────────┘
Phase 3 (LM decode, CPU) ───────────────────────────────────────────────▶ Phase 5
```

- Phases 1, 3 podem correr em paralelo (CPU, independentes).
- Phase 2 depende de Phase 1 (usa o codec-pool p/ degradar o test).
- Phase 4 depende de Phase 1 (usa o pool no treino) e precisa de GPU (re-provisionar).
- Phase 5 (verdict) depende de 2, 3, 4.

---

## Phase 1: Codec-pool de augmentação (CPU, TDD)

**Objective:** substituir o G.711-fixo por um pool de codecs realistas amostrável, testado.

### T1.1 — Módulo `codec_pool.py`

#### Objective
Criar `apply_codec(samples, sr, codec, rng)` e `sample_codec(rng, weights)` para um pool
{g711a, g711u, gsm, opus_low} (AMR opcional), reusando torchaudio/audioop/ffmpeg.

#### Why this step (action + reasoning)
1. **O que faz:** introduz um módulo coeso de codecs realistas com amostragem ponderada.
2. **Por que agora:** é o prerequisito CPU do FT (D5 do blueprint) e ataca a causa-raiz do platô
   (G.711 inócuo, ADR D3). Feito antes da GPU para não desperdiçar compute (parsimony).

#### Evidence
`scripts/corpus/telephone_channel.py:1-40` (cadeia atual = G.711 A-law fixo). Blueprint
§ "Causa-raiz do platô telefônico" (APSIPA: G.711 inócuo). `ffmpeg -encoders` local: g711/gsm/opus OK, AMR ausente [MEDIDO].

#### Files to edit
```
scripts/corpus/codec_pool.py (NEW) — apply_codec + sample_codec + pool ponderado
scripts/tests/test_codec_pool.py (NEW) — RED tests primeiro
```

#### Deep file dependency analysis
Novo módulo; sem callers ainda (T1.2 o consome). Não altera `telephone_channel.py` (composição, não modificação — OCP).

#### Deep Dives
- `apply_codec`: float[-1,1] → (encode→decode no codec) → float[-1,1], mesma taxa de saída (16k após resample). G.711 via audioop (já existe); gsm/opus via `torchaudio.io.AudioEffector` (in-process).
- Invariante: saída finita, comprimento ≈ entrada (±frame do codec), passthrough se codec=identity.

#### Concurrency tests
(none — single-threaded) por amostra; o dataloader chama por-item em workers independentes (sem estado compartilhado; RNG por-worker semeado).

#### TDD
```
test_sample_codec_respeita_pesos — seed fixo → distribuição esperada (GWT)
test_apply_codec_g711_altera_e_mantem_comprimento — assert out != in, len≈, finito
test_apply_codec_gsm_degrada_mais_que_g711 — energia de banda alta cai mais no gsm
test_apply_codec_passthrough_quando_identity — assert allclose(out, in)
```
RED → GREEN → REFACTOR.

#### Acceptance criteria
- Todos os testes passam; `apply_codec` cobre g711a/g711u/gsm/opus_low; AMR degrada graciosamente se ausente (skip com log).
- Arquivo < 200 LoC (`architecture.md`).

#### DoD
`PYTHONPATH=scripts python3 -m pytest scripts/tests/test_codec_pool.py -q` verde.

### T1.2 — Integrar pool na cadeia/adapter com p-gate e curriculum

#### Objective
`telephone_channel_transform.py` passa a amostrar do pool com probabilidade `p` (schedulable) e por-stream.

#### Why this step
1. **O que faz:** liga o pool ao transform on-the-fly com p-gate + hook de curriculum.
2. **Por que agora:** o FT (Phase 4) precisa da augmentação já parametrizável (p, curriculum) — ADR D2/D3.

#### Evidence
`scripts/corpus/telephone_channel_transform.py:1` (adapter atual, G.711 fixo). Blueprint D3 (p=0,5, curriculum), TM#2 (codec importa).

#### Files to edit
```
scripts/corpus/telephone_channel_transform.py — usar codec_pool; parâmetro p e schedule
scripts/tests/test_telephone_channel_transform.py — RED tests do p-gate/determinismo
```

#### Deep file dependency analysis
O adapter é o único caller de produção da cadeia (Baseline § callers). Muda a fonte do codec de fixo→pool; mantém a interface de transform lhotse (invariante).

#### Concurrency tests
(none — single-threaded) por-item; RNG por-worker.

#### TDD
```
test_transform_aplica_com_prob_p — seed fixo, p=1 aplica, p=0 passthrough (GWT)
test_transform_deterministico_sob_seed — mesma seed → mesma saída
test_curriculum_sobe_p_por_epoca — p(epoch) monotônico
```

#### Acceptance criteria
- Testes passam; interface lhotse preservada; p e curriculum expostos.

#### DoD
`pytest scripts/tests/test_telephone_channel_transform.py -q` verde.

---

## Phase 2: Avaliação mono-falante real-codec (CPU, TDD)

**Objective:** construir a métrica âncora (D1) e medir o modelo entregue nela.

### T2.1 — Builder do test CORAA real-codec + medição com IC95%

#### Objective
`build_realcodec_testset.py` aplica o codec-pool ao test CORAA (mono-falante, humano) e
`measure_callcenter.py` reporta WER + bootstrap IC95%.

#### Why this step
1. **O que faz:** cria o test de deploy-condition e o baseline honesto do modelo atual.
2. **Por que agora:** sem a métrica certa (D1) não há como validar o Goal nem o FT (falácia § 3 #6/#12).

#### Evidence
Blueprint D1. `training/measure_callcenter.py:1` (harness existe; falta IC). CORAA test é humano, N grande.

#### Files to edit
```
training/build_realcodec_testset.py (NEW) — degrada CORAA test com codec_pool (local)
training/measure_callcenter.py — adicionar bootstrap IC95% (reusa scripts/corpus se houver)
training/tests/test_build_realcodec_testset.py (NEW) — RED
training/tests/test_measure_callcenter.py — RED p/ o IC
```

#### Deep file dependency analysis
`build_realcodec_testset.py` importa `codec_pool` (T1.1). `measure_callcenter.py` ganha função de IC (não quebra a assinatura CLI; callers = testes).

#### Failure scenarios
Ver § Failure scenarios (ffmpeg/torchaudio ausência, áudio corrompido).

#### Concurrency tests
(none — single-threaded) — builder e medição rodam em processo único, sem estado compartilhado.

#### TDD
```
test_builder_produz_cuts_com_sr_correto — N cuts, sr=16000, features extraíveis
test_bootstrap_ic_em_dados_toy — IC95% de WER toy dentro do esperado (determinístico c/ seed)
```

#### Acceptance criteria
- Baseline do modelo entregue no CORAA real-codec reportado com IC95% [MEDIDO].

#### DoD
`pytest training/tests/test_build_realcodec_testset.py training/tests/test_measure_callcenter.py -q` verde + número registrado em `training/results/`.

---

## Phase 3: n-gram LM shallow-fusion no decode (CPU, TDD)

**Objective:** ganho de WER grátis no decode, numpy-safe.

### T3.1 — Treinar KenLM 4-gram + decoder prefix-beam com shallow fusion

#### Objective
`ctc_lm_decode.py`: prefix-beam sobre log-probs CTC + `α·log p_LM` (KenLM 4-gram).

#### Why this step
1. **O que faz:** adiciona LM ao decode sem tocar modelo/dado (ADR D5).
2. **Por que agora:** é a alavanca mais barata (blueprint #1) e complementa o FT (substituições são LM-addressable, TM#1).

#### Evidence
Blueprint § ranking #1 (10–15% rel); `.claude/rules` memória do projeto (pyctcdecode quebrou numpy → D5 numpy-safe).

#### Files to edit
```
training/ctc_lm_decode.py (NEW) — prefix-beam + KenLM shallow fusion
training/tests/test_ctc_lm_decode.py (NEW) — RED
```

#### Deep file dependency analysis
Novo; consome as log-probs ONNX (mesmo formato do `measure_callcenter.py`). KenLM via kaldilm/subprocess (isola numpy).

#### Failure scenarios
Ver § Failure scenarios (binário KenLM ausente).

#### Concurrency tests
(none — single-threaded).

#### TDD
```
test_prefixbeam_sem_lm_igual_greedy_em_toy — α=0 reproduz o greedy
test_lm_reordena_hipoteses_plausiveis — em logits toy, α>0 prefere sequência do LM (GWT)
test_beam_deterministico_sob_seed
```

#### Acceptance criteria
- α=0 ≡ greedy; α>0 melhora ou empata; ganho relativo medido no dev real reportado.

#### DoD
`pytest training/tests/test_ctc_lm_decode.py -q` verde.

---

## Phase 4: FT gentil corrigido (GPU — re-provisionar)

**Objective:** treinar o modelo adaptado ao canal sem colapso.

### T4.1 — Runbook `run_ft_codec.sh` + bandwidth-embedding

#### Objective
FT do M5 medium+fonema: single-ckpt warm-start, base-lr 0,002, warmup 4000, `--use-mux 1`,
codec-pool p=0,5 em curriculum, +bandwidth-embedding, com monitor de blank-rate.

#### Why this step
1. **O que faz:** executa a alavanca principal (ADR D2/D3/D6) na GPU.
2. **Por que agora:** só depois que o pool (Phase 1) e a métrica (Phase 2) existem — para não requeimar GPU (D5).

#### Evidence
Blueprint D2/D3/D6; colapso D2 [MEDIDO]; icefall `finetune_zipformer.rst` (LR ~1/10), `optim.py:841-900` (Eden pico).

#### Files to edit
```
training/run_ft_codec.sh (NEW) — runbook versionado (a instância roda icefall patchado)
```

#### Deep file dependency analysis
Runbook orquestra o treino na instância; consome o codec-pool (Phase 1) via o transform. O patch de bandwidth-embedding no `train.py` da instância é registrado no runbook (não é artefato versionável do repo — icefall vive em `/workspace`).

#### Deep Dives
- Monitor de blank-rate: decodar um subset a cada N batches; se blank-rate > limiar (early-warning), abortar e reduzir p/LR (evita o colapso do D2).
- Invariante: `--use-mux 1` mantém wideband (antídoto do "forget the init").

#### Concurrency tests
(none — single-threaded) do ponto de vista do runbook; o treino usa dataloader workers com RNG por-worker semeado (sem estado compartilhado mutável).

#### TDD
Fase de GPU/integração — a validação é a **trajetória medida** (blank-rate estável + WER caindo), não teste unitário. Runbook validado por dry-run de sintaxe (`bash -n run_ft_codec.sh`).

#### Acceptance criteria
- Treino completa sem colapso (blank-rate estável); checkpoint produzido; trajetória de WER 8 kHz registrada.

#### DoD
`bash -n training/run_ft_codec.sh` OK + trajetória em `training/results/` mostrando WER 8 kHz caindo sem colapso.

---

## Phase 5: Medição e verdict do DoD#3

**Objective:** medir o modelo FT na métrica âncora + LM e emitir o verdict.

### T5.1 — Eval final com IC95% e verdict

#### Objective
Medir o modelo FT no CORAA real-codec (mono-falante) + LM (α afinado) → WER 8 kHz com IC95%,
e wideband (não-regressão).

#### Why this step
1. **O que faz:** produz a evidência [MEDIDO] do Goal.
2. **Por que agora:** é o gate do DoD#3.

#### Evidence
Goal; D1 (métrica); D3/D5 (alavancas).

#### Concurrency tests
(none — single-threaded) — medição em processo único.

#### Files to edit
```
training/results/m5-8khz-final-results.md (NEW) — números medidos + comando + IC
```

#### TDD
Medição (não unit). Reusa harness testado (Phase 2/3).

#### Acceptance criteria
- WER 8 kHz mono-falante ≤ 25% (IC95%) **E** wideband ≤ 24% → DoD#3 PASS.
- Se > 25%: registrar o gap medido e escalar (dado real 8 kHz — blueprint #7/#8) num plano seguinte.

#### DoD
`training/results/m5-8khz-final-results.md` com número [MEDIDO], comando reprodutível, IC95%.

---

## Coverage Matrix

| Requisito / gap | Task(s) |
|---|---|
| Codec realista (substituir G.711 fixo) — ADR D3 | T1.1, T1.2 |
| Augmentação por-stream + curriculum — ADR D2/D4, Q1 | T1.2, T4.1 |
| Métrica âncora mono-falante real-codec — ADR D1 | T2.1 |
| Baseline honesto do modelo atual + IC95% — falácia § 3 #12 | T2.1 |
| n-gram LM shallow-fusion numpy-safe — ADR D5, Q3 | T3.1 |
| FT gentil sem colapso — ADR D2 | T4.1 |
| Bandwidth-embedding — ADR D6, Q2 | T4.1 |
| WER 8 kHz ≤25% + wideband ≤24% — Goal | T5.1 |
| Épocas até platô — Q4 | T4.1, T5.1 |

## Failure scenarios (external I/O — ffmpeg/torchaudio/KenLM)

| Dependência | Modo de falha | Como o teste reproduz | Comportamento esperado |
|---|---|---|---|
| ffmpeg (encode codec) | binário/encoder ausente (ex.: AMR) | mock/skip do encoder no test | erro tipado claro + skip gracioso do codec ausente (log), pool segue com os disponíveis |
| torchaudio AudioEffector | import falha / versão incompatível | test com import guardado | fail-fast com mensagem acionável (não silenciar) |
| KenLM (LM binary) | binário ausente / modelo corrompido | test com caminho inválido | erro tipado; decoder cai para greedy (α=0) com WARN |
| áudio de test | arquivo corrompido / vazio | cut vazio no builder | pular cut com log; não abortar o batch inteiro |

Nenhum erro engolido (`.claude/rules/error-handling.md`): todos tipados e logados.

## Global DoD

- [ ] Todos os testes unitários das Phases 1–3 verdes (`pytest`).
- [ ] Lint/estilo OK; cada arquivo novo < 200 LoC (`architecture.md`).
- [ ] Todo número reportado com rótulo de proveniência (`asr-evidence-discipline.md § 1`).
- [ ] CHANGELOG `[Unreleased]` atualizado (Regra 6).
- [ ] Sem WAV materializado em disco na augmentação de treino (invariante M3).
- [ ] `run_ft_codec.sh` passa `bash -n`.
- [ ] WER 8 kHz ≤25% (IC95%) + wideband ≤24% medidos — ou gap registrado com plano de escalada.

## Final Phase: Integration Validation

**Objective:** o "eat your own cooking" — a cadeia inteira funciona ponta-a-ponta.

- [ ] `codec_pool` → `telephone_channel_transform` → dataloader (dry-run de 1 batch sem erro).
- [ ] `build_realcodec_testset` → `measure_callcenter` (+IC) → número no CORAA real-codec.
- [ ] `ctc_lm_decode` sobre as log-probs → WER com/sem LM.
- [ ] FT (`run_ft_codec.sh`) → checkpoint → export ONNX → `measure_callcenter` → WER 8 kHz final com IC95%.
- [ ] Chaos pass dos Failure scenarios (ffmpeg/KenLM ausentes → degradação graciosa, não crash).
- [ ] Todos os testes verdes; verdict do DoD#3 registrado com evidência [MEDIDO].
