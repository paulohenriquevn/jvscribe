---
type: Medição
title: M4 — piloto comparativo em FLEURS
description: A corrida que comparou os candidatos no test set público.
tags: [medicao, m4, fleurs, piloto]
timestamp: 2026-07-31T00:00:00Z
---

# M4 — Piloto FLEURS-only: primeiro WER held-out na recipe REAL do icefall

**Data:** 2026-07-25 · **Custo:** ~$0,22 `[MEDIDO]` (vast.ai RTX 3090, 71 min) · **Status:** pipeline
validado ponta-a-ponta; WER honesto medido; **NÃO decide o finalista de M4** (1 finalista, dados
mínimos, sem RTFx).

Este piloto foi o **Stage B** do plano de infra (Stage A = probe; ver `run_pilot_icefall.md`). O
corpus (FLEURS ~10h) foi escolha explícita do dono: o mais rápido/barato para provar o pipeline
com número honesto, escalando depois. TAGARELA (8.972h) é o corpus de M5 — não cabe num piloto
barato (1,76 TB, machine-label sem test split, CC-BY-NC-SA).

## Setup `[MEDIDO]`

| Item | Valor |
|---|---|
| Recipe | icefall `egs/commonvoice/ASR/zipformer/train.py` (REAL, não wrapper) — Regra 9 |
| Modelo | Zipformer-CTC **small, 22.118.279 params**; `--use-ctc 1 --use-transducer 0` (CTC puro) |
| Config | `num-encoder-layers 2,2,2,2,2,2`, `encoder-dim 192,256,256,256,256,256` (flags do RESULTS.md) |
| Treino | 30 épocas, `base-lr 0.04`, fp16, spec-aug on, musan off, vocab BPE 500, `max-duration 400` |
| Corpus | FLEURS pt_br: train 2793 cuts (~10h), dev 386, **test held-out** (21471 palavras de ref) |
| Hardware | vast.ai RTX 3090; imagem `k2fsa/icefall:torch2.4.1-cuda12.1` (k2 1.24.4, torch 2.4.1+cu121) |
| Adaptador de dados | `training/prep_icefall.py` (nosso único código; emite `cv-pt_cuts_{train,dev,test}`) |
| Decoder | `ctc_decode.py` do librispeech adaptado ao commonvoice (Regra 9), `ctc-greedy-search` |

## Throughput `[MEDIDO]`

- **41,9s ± 1,3 / época** (n=10, timestamps do `train.log`); 30 épocas = **20,9 min de GPU**.
- Compute do run: **~$0,05** (throughput medido × $0,1356/h). Total do piloto ~$0,22 (boot+prep+idle).
- Loss de treino (val) caiu monotonicamente: época 2 = 1,006 → época 29 = 0,822 → o modelo aprendeu.

## WER `[MEDIDO]`

Comando: `ctc_decode.py --epoch 30 --avg 1 --use-averaged-model 0 --decoding-method ctc-greedy-search`

| Conjunto | %WER | ins | del | sub | ref words |
|---|---|---|---|---|---|
| **test (held-out)** | **96,52%** | 10 | 19394 | 1320 | 21471 |
| train | 95,19% | 16 | 54340 | 4837 | 62186 |

Evidência bruta: `training/results/archive/m4-pilot-fleurs-raw.tar.gz` (arquivada em M9/T4.2 — 193 KB). **Não foi apagada**: ao contrário dos demais decodes, este diretório não tem `recogs-*.txt` par, então os `errs-*` são o único dado por-utterance sobrevivente e não são recomputáveis.

## Hipótese → Evidência → Conclusão

**H1 (pré-registrada):** "10h do zero é catastroficamente pouco; o WER held-out será altíssimo."
- **Evidência:** WER test = 96,52%. **Conclusão:** H1 confirmada. Erro dominado por **deletions**
  (19394 de 20724) = o CTC sub-emite (colapso parcial para blank), assinatura de dados insuficientes.

**H2 (emergente):** "o modelo está underfit, não overfit."
- **Evidência:** train (95,19%) ≈ test (96,52%) — gap de ~1,3pt, ambos deletion-dominated. Um modelo
  overfit teria train muito melhor que test (como o smoke de 1h: train 18% / test 99%).
- **Conclusão:** **UNDERFIT / colapso para blank**, não memorização. A recipe real (spec-aug +
  dropout + regularização) impede o overfit que o wrapper smoke sofria; mas 10h/30 épocas não bastam
  para aprender alinhamento CTC. Modo de falha **diferente** do smoke, mesma raiz: falta de dados.

**Achado metodológico `[MEDIDO]` (vale para M5):** o **model-averaging** (`--avg 15 --use-averaged-model 1`)
**degenerou** o modelo → saída 100% vazia (WER 100,00%, 0 correct). Sem averaging (epoch 30 puro) →
96,52% (757 corretos). Causa: média sobre trajetória **não-convergida** (loss ainda caindo nas épocas
16-30). Em M5 (convergido) o averaging ajuda; num run curto/instável ele **atrapalha**. Não usar
averaging cego em runs curtos.

## O que este piloto PROVA e o que NÃO prova

**Prova `[MEDIDO]`:**
- O pipeline roda ponta-a-ponta na recipe REAL do icefall: `prep_icefall` → BPE → `train.py` (CTC puro)
  → `ctc_decode` → WER, numa GPU real. Os 757 corretos provam que o **decode não tem bug** (bug daria
  0 sempre).
- Custo e throughput reais de um run small nesta GPU.

**NÃO prova (honestidade — `asr-evidence-discipline`):**
- **Não decide o finalista de M4.** É 1 finalista (Zipformer-CTC), 1 tamanho, dados mínimos. FastConformer
  não foi treinado. Sem curva WER×RTFx. Sem RTFx (que é medida na CPU-alvo i7-1355U, não nesta GPU —
  seria a falácia §3 #4).
- **Não é o WER de produção.** 96,52% é o piso de um modelo faminto de dados, não o alvo (PRD § 7).
- **Não valida a supervisão fonética** (não foi construída neste run; a ablação é de M5 com corpus grande).

## Próximo passo real (M5, não este piloto)

Repetir com o corpus grande (TAGARELA pseudo-labelado + filtrado via pipeline M3, ~centenas a milhares
de h), instância com disco adequado, convergência real, e então: averaging faz sentido, curva WER×RTFx
nos 3 tamanhos, ablação fonética no held-out. Extrapolação de custo `[ESTIMATIVA]` (linear no throughput
medido): ~$31-44/run small em 8.972h numa 3090 — re-medir em M5.
