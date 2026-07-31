---
type: Medição
title: M5 — modelo em escala
description: O finetune que produziu o modelo entregue, e o diagnóstico de overfitting.
tags: [medicao, m5, wer, overfitting]
timestamp: 2026-07-31T00:00:00Z
---

# M5 — Resultados finais (fine-tune espontâneo PT-BR)

Deliverable de M5: **Zipformer-CTC medium (64M) + cabeça de fonema**, fine-tunado em
CORAA+TAGARELA, quantizado int8, medido **no hardware-alvo (notebook CPU, ONNX Runtime)**.
Todo número carrega rótulo de proveniência (`.claude/rules/asr-evidence-discipline.md § 1`).

## Modelo entregue

- **Arquitetura:** Zipformer-CTC medium 64M + fonema aux (herdada de M4, ADR 0003).
- **Deliverable:** média de checkpoints (`avg` de checkpoint-124000 + checkpoint-112000 do
  run de 10 épocas) — a alavanca de averaging derrubou o WER (ver abaixo).
- **Formato:** ONNX int8 (70 MB) exportado via `export-onnx-ctc.py` (cabeça de fonema
  removida na inferência — é auxiliar de treino). Artefatos: `model.int8.onnx`,
  `bpe.model` (vocab 500), `tokens.txt`.

## Números medidos `[MEDIDO]`

Ambiente: **notebook i7 12-core, ONNX Runtime int8, CPU, greedy CTC**, test CORAA humano
completo (12.676 utts, 11,24 h de áudio). Comando: `decode_onnx_local.py --threads 6 --batch 8`.

| Recorte | WER | CER | Alvo | Status |
|---|---|---|---|---|
| **Wideband espontâneo** (modelo médio) | **23,31%** | 11,28% | ≤25% / < M4 27,46% | ✅ PASSA |
| **Real-time (RTFx CPU)** | **34,69×** | — | RNF-07 ≥6× | ✅ PASSA (5,8×) |
| **Telefônico-proxy 8 kHz** (bandpass, single) | **31,97%** | 16,46% | ≤25% | ❌ não bate — e o proxy era otimista |
| **Call center REAL 8 kHz** (áudio humano-transcrito) | **40,13%** | — | ≤25% | ❌ gap real ~15 pp (ver caveats) |

**Contexto:** o wideband 23,31% já está **abaixo do M4 (27,46%)**, que era em fala **lida**
(FLEURS, mais fácil); M5 mede fala **espontânea** (mais difícil). O averaging levou o single
de 25,81% (full-test int8) para **23,31%**.

## Trajetória do run (evidência) `[MEDIDO]`

WER wideband (subset 1k, greedy, GPU) por *low* de época — o padrão é: melhor logo após cada
fronteira de época (o WER degrada dentro da época = overfitting ao pseudo-rótulo TAGARELA):

| início de época | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|
| WER | 42,5 | 36,5 | 33,7 | 32,6 | 29,1 | 28,5 | 25,96 | **24,73** |

Config vencedora (após diagnóstico registrado no `CLAUDE.md § Contexto que evita erros
repetidos`): base-lr **0,03** (não
0,0001, que prendia o head fresco no prior de blank → WER 100%), fp16, max-dur 500, 10 épocas,
eager-load + num-workers 2, encoder do M4 + heads frescos (bpe.model do M4 perdido).

## DoDs

- **DoD wideband espontâneo:** ✅ 23,31% (bate M4 e ≤25%).
- **DoD real-time CPU (RNF-07):** ✅ 34,69× (o requisito central — cabe no notebook do atendente).
- **DoD#3 telefônico 8 kHz ≤25%:** ❌ **em aberto.** Baseline honesto no **call center REAL** =
  **40,13% [MEDIDO]** (`measure_callcenter.py`, greedy, modelo entregue) — pior que o proxy
  bandpass (31,97%), que subestimava o canal (falácia § 3 #6). A **continuação D2**
  (warm-start + augmentação on-the-fly) **FALHOU** `[MEDIDO]`: colapsou o modelo para near-blank
  (WER ~98% em wideband e telefônico; `ctc_output.norm` 245→108) por LR alto (0,006 vs ~0,0045
  recomendado) + choque de augmentação a 100% sobre um modelo convergido. Caminho corrigido em
  `knowledge-base/discoveries/blueprints/m5-8khz-telephone-wer-blueprint.md`.
  **Caveats do 40,13%** (direciona, não conclui — § 3 #12): 9 min → IC largo; 2 interlocutores
  no mono; granularidade de 30s; máscaras de PII contam como erro.

## Validação real-world (qualitativa)

Clip real de call-center 8 kHz nativo (`callcenter/`, não versionada — LGPD): o modelo **sem**
augmentação telefônica transcreveu de forma **fragmentada** ("alão"≈alô, "é sério", "tudo bem é
que quem tá falando", "todo lugar") — confirma que o DoD#3 exige a continuação D2. RTFx 18,4×
mesmo nessa clip.

## Metodologia de reprodução

1. Treino: `run_finetune.sh 10` na instância (icefall commonvoice zipformer + patches M5).
2. Averaging: `average_checkpoints([ckpt-124000, ckpt-112000])`.
3. Export ONNX: `export-onnx-ctc.py --epoch 98 --avg 1` (checkpoint médio, fonema removido).
4. Medição: `decode_onnx_local.py` no notebook (ONNX int8, CPU) sobre `cv-pt_cuts_test.jsonl.gz`
   (CORAA humano) e `coraa_tel` (telefônico-proxy). WER via `jiwer`.

## Proveniência

Todos os WER/RTFx acima são `[MEDIDO]` (comando + hardware + full-test). A referência de
viabilidade ≤25% em espontâneo é `[LITERATURA]` (Parakeet-TDT 0.6B + TAGARELA, 10-21%, porém
600M = 9× o nosso 64M). Backup dos artefatos: `models/m5-final-medium-phoneme/finetune/`.

## Phase 2 — baseline D1 (real-codec mono-falante) `[MEDIDO]`

`measure_realcodec.py --checkpoint avg_124_112 --n 500 --codec pool` (CORAA test mono-falante
degradado pelo codec-pool GSM/Opus/G.711): **36,88% WER**. Contexto: bandpass-proxy dava 31,97%
(otimista — codec inócuo); call real mono-misto 40,13%. O codec-pool realista é a condição de
deploy honesta (D1). O FT (Phase 4) precisa cobrir ~12 pp para o alvo ≤25%.

## Phase 4 — full-FT colapsa (2× MEDIDO) → pivô para encoder-freeze `[MEDIDO]`

FT gentil corrigido (single-ckpt, LR 0,002, codec-pool p=0,5, fp32) **colapsou igual ao D2**:
`checkpoint-4000 D1 = 97,83%` · `checkpoint-8000 D1 = 98,58%` (near-blank, piorando). Confirma
que **full-FT deste CTC convergido + codec-aug colapsa o greedy** (2 runs independentes), apesar
de `ctc_loss` de treino saudável (~1,1). **Full-FT descartado como método.**

**Pivô (collapse-proof):** encoder profundo (63,4M) **CONGELADO**, treina só encoder_embed
(0,61M) + ctc_output (0,26M) + fonema (0,035M) = ~0,9M (~1,4%, equivalente a adapter). Runbook
`training/run_ft_freeze.sh` (patch `FREEZE_ENCODER=1` em train.py da instância). Em curso.

## Phase 4b/c — encoder-freeze também colapsa; métrica validada `[MEDIDO]`

- **Métrica D1 validada SÃ:** `avg_124_112` (modelo bom) no codec-pool atual (opus60%@6kbps) =
  **35,53%** (≈ 36,88% do pool antigo). Logo o colapso dos FTs NÃO é artefato de métrica.
- **Encoder-freeze (corpo 63M fixo, treina frontend+cabeças) COLAPSOU pior:** `checkpoint-4000
  D1 = 100,00%` (0 corretas, blank puro). O frontend treinável drifta e alimenta blank ao encoder
  congelado — congelar o corpo não protege.
- **Veredito (3 configs medidos):** full-FT (LR 0,006/avg ~98%; LR 0,002/single ~98%) e
  encoder-freeze (100%) — **codec-aug fine-tuning colapsa este CTC para blank de forma robusta**,
  enquanto o modelo bom dá 35,53% no mesmo teste. Causa: atrator de blank do CTC + augmentação
  agressiva; encontra blank por qualquer parâmetro treinável.
- **Último teste em curso:** p=0,15 (85% do batch limpo = âncora), musan off, modelo cheio —
  isola "intensidade de augmentação" como causa. Decide entre "aug gentil funciona" e o veredito
  honesto de que a abordagem por FT não fecha o DoD#3 (→ follow-up: curriculum-aug research OU
  dado telefônico real).

## VEREDITO CONCLUSIVO DoD#3 (2026-07-30) `[MEDIDO]`

**4 configs de fine-tuning com codec-aug, TODAS colapsam o greedy para blank** (métrica D1 validada
sã: modelo bom = 35,53% no mesmo pool):

| Config | WER D1 |
|---|---|
| avg_124_112 (baseline, sem FT) | 35,53% ✅ |
| full-FT LR 0,006/avg | ~98% |
| full-FT LR 0,002/single | 97,83→98,58% |
| encoder-freeze (frontend+cabeças) | 100% |
| p=0,15 + musan off (aug mínima) | 97,77% |

**Causa-raiz isolada:** o run M5 original SEM augmentação convergiu (avg_124_112 = 35% real-codec /
23% wideband); adicionar augmentação telefônica dispara o atrator de blank do CTC — robusto até em
p=0,15. **A abordagem por fine-tuning simples NÃO fecha o DoD#3 com este modelo.**

### Estado honesto de M5
- ✅ **DoD wideband** 23,31% · ✅ **DoD real-time** 34,69× RTFx.
- ❌ **DoD#3 telefônico ≤25%: NÃO atingido.** Melhor honesto = **~36% real-codec** (modelo entregue).
- **Follow-up (novo milestone) para ≤25%:** (a) research anti-colapso — curriculum de augmentação
  a partir de p≈0 com ramp lento + label-prior CTC (arXiv:2406.02560); e/ou (b) **dado telefônico
  real em escala** (o gargalo confiável, hoje ausente: Nexdata 104h comercial ou pseudo-label do
  call center). O n-gram LM (grátis, ~10% rel) soma mas sozinho não fecha o gap.

Nada aqui é declarado sem número medido. GPU pausada (sem mais experimentos — 4 colapsos = conclusivo).

## ⚠️ CORREÇÃO DE CAUSA-RAIZ (2026-07-30) — o colapso era BUG DE CONFIG, não a augmentação `[FONTE-REPO]`

Controle decisivo: FT **sem augmentação nenhuma** também colapsou (**99,57%, 16 corretas**). A
augmentação NUNCA foi a causa. Bug em `load_model_params` (train.py:335): matching de `--init-modules`
por prefixo `"encoder."` casa `encoder.*` (63M) mas NÃO `encoder_embed.*` (frontend Conv 0,6M). Com
`--init-modules "encoder,ctc_output,phoneme_output"` (D2 + 5 tentativas), o **`encoder_embed` ficava
ALEATÓRIO** → alimenta blank ao encoder bom → colapso, com ou sem aug (o run original a LR 0,03/10
épocas re-treinava o frontend, por isso não colapsava). **Fix: adicionar `encoder_embed` ao
init-modules** (confirmado no log). Experimento corrigido em curso; conclusões anteriores de
"codec-aug colapsa" RETRATADAS.

## Trajetória FT corrigido (exp-m5-ft-fixed) `[MEDIDO]`

Com o bug do `encoder_embed` corrigido, o FT NÃO colapsa mais (produz texto real). Trajetória D1
(real-codec, 500 cuts): baseline sem-FT **35,53%** → ckpt-4000 **42,84%** → 8000 **40,50%** →
12000 **39,97%**. Descendo mas **platôando ACIMA do baseline** e desacelerando (−2,34→−0,53pp).
Leitura honesta: o FT na MESMA base (CORAA+TAGARELA) adiciona robustez a codec, não informação —
o teto ~36% é **data-limited**. ≤25% parece improvável por esta via (aguardando épocas 2-3 +
averaging + LM para confirmar). O fix validou o método; o limite agora é DADO, não bug.

## VEREDITO FINAL DoD#3 (2026-07-30) `[MEDIDO]` — data-limited, metodo correto

FT corrigido (sem o bug) rodado ate fim da epoca 1. Trajetoria D1: 42,84 -> 40,50 -> 39,97 ->
**39,38%**, plato ACIMA do baseline 35,53%, caindo ~0,5pp/4000 batches (<=25% exigiria ~16 epocas).
O FT overfita a mesma base (CORAA+TAGARELA) e nao supera o modelo entregue. Conclusao medida:
- DoD#3 (telefonico <=25%): NAO atingivel com o modelo 64M + dados atuais.
- Melhor telefonico = modelo ENTREGUE ~35,53% real-codec (o FT nao ajuda; +LM ~32% [ESTIMATIVA]).
- O colapso anterior era um BUG (encoder_embed random), nao a augmentacao — corrigido e entendido.
  Corrigido, o teto real e DADO, nao metodo. Caminho a <=25%: dado telefonico real (follow-up).

### M5 — placar honesto final
DoD wideband 23,31% OK · DoD real-time 34,69x RTFx OK · DoD#3 telefonico ~36% (nao <=25%, data-limited).
