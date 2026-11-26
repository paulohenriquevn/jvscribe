---
type: Medição
title: M4 — a cabeça de fonema transferiu para o medium
description: Ablação que fechou o deliverable de M4: WER 28,86% → 27,49%, −4,74% relativo.
tags: [medicao, m4, fonema, ablacao]
timestamp: 2026-07-31T00:00:00Z
---

# M4 — deliverable final: Zipformer-CTC medium (64M) + cabeça de fonema

> ⚠️ **Proveniência histórica.** Os caminhos e comandos citados abaixo são da árvore de
> diretórios vigente na data desta medição e **não resolvem no repositório atual** — inclusive
> o runtime Rust, removido em 2026-07-30. Ficam preservados como registro de *como* o número
> foi produzido: reescrevê-los para os caminhos de hoje documentaria um comando que nunca
> foi executado.

**Data:** 2026-07-28 · **Corpus:** MLS-PT ~161h train, FLEURS held-out test (919 cuts,
21.471 palavras) · **Recipe:** icefall real `zipformer/train.py` + patch de fonema
`training/prep_phoneme_head.py` (Regra 9) · **Hardware:** vast.ai RTX 3090 · **Decode:**
`ctc-greedy-search` avg=10. Fecha a pendência que o ADR 0003 criou (a ablação de fonema
fora medida no small; a transferência ao medium era `[ESTIMATIVA]`).

## Hipótese (escrita antes de medir)

A cabeça de fonema auxiliar, que deu **−4,64% relativo de WER no small**, **transfere ao
medium** com a mesma ordem de grandeza (a supervisão fonética regulariza o encoder
independentemente do tamanho). Refutada se: a melhora relativa no medium ficasse < 3%, ou
o IC bootstrap incluísse 0.

## Evidência `[MEDIDO]`

medium com e sem a cabeça, treinados 30 épocas no **mesmo** corpus/GPU, decodados com
**mesmo** protocolo (`ctc-greedy-search` avg=10, mesmo FLEURS test). Load do checkpoint do
candidato: `--use-phoneme-ctc 1` instancia a cabeça (559→chaves batem), que é ignorada no
decode (só `ctc_output` decide o greedy). Params: **64.282.409** (64,25M do medium +
31.806 da cabeça).

| Config | WER | CER |
|---|---|---|
| medium SEM cabeça (baseline) | **28,86%** | 10,94% |
| **medium + cabeça de fonema** | **27,49%** | **10,53%** |

**IC bootstrap pareado** (por utterance, B=10.000, seed=42, `bootstrap_wer_ci.py`):

| Métrica | Ponto | IC 95% |
|---|---|---|
| Δ absoluto | **1,37 p.p.** | [0,80 · 1,95] |
| Melhora relativa | **4,74%** | [2,79% · 6,72%] |
| P(melhora > 0%) | **100,0%** | — |
| P(melhora ≥ 3% da DoD) | **95,7%** | — |

## Conclusão (apenas o que a evidência sustenta)

**A cabeça de fonema transfere ao medium** — melhora **inequivocamente significativa**
(P(Δ>0)=100%, IC exclui 0) e da **mesma ordem** que no small (medium −4,74% rel vs small
−4,64% rel). A DoD de ≥3% relativo é **atingida no ponto** (4,74%), e desta vez com
**P(≥3%)=95,7% ≥ 95%** (o small ficara em 94,1%, fronteiriço) — o medium é ligeiramente
mais robusto no critério. O CER também cai (10,94% → 10,53%). O **deliverable final de M4**
é o **Zipformer-CTC medium (64M) + cabeça de fonema, int8 = 27,49% WER / 10,53% CER**
(wideband FLEURS, avg=10).

## Validação em CPU — o deliverable roda em CPU, então o número que importa é o do runtime `[MEDIDO]`

O WER de 27,49% acima é o **decode Python (fp32) na GPU**. O produto roda **int8 em CPU**
(runtime Rust `macaw-cli transcribe`). Eval na i7-1355U de referência, test FLEURS completo:

| Fonte | WER | CER |
|---|---|---|
| **Runtime Rust CPU (int8, full 919)** | **27,46%** | **10,54%** |
| Decode Python (fp32, full 919) | 27,49% | 10,53% |

**Δ 0,03pp — o runtime CPU NÃO degrada** vs o decode de treino (cadeia `kaldi_fbank → int8
ONNX → ctc_greedy` funcionalmente equivalente ao decode icefall; mesmo resultado do small).
**int8 lossless no medium** confirmado por desconfundir com fp32 no mesmo n=300 (int8 28,56%
vs fp32 28,66%, Δ dentro do ruído — o +1pp do n=300 era subconjunto, não quantização).
**RTFx ≈ 35-64×** na i7-1355U (cabeça de fonema fora do grafo → igual ao medium puro; ADR
0003) — real-time com folga sobre o piso RNF-07 (6×). Reprodução:
`MACAW_MODEL=model.medium-phoneme.int8.onnx python3 training/scripts/eval_runtime_wer.py --n 919`.

**Limites honestos (§2):**
- **WER wideband FLEURS**, não 8 kHz call center — a penalidade telefônica (o probe do
  DISC-05 mediu ~31% rel de gap simulado, piso) e o WER de produção são de **M5**.
- Peso da loss de fonema = 0,3 `[ESTIMATIVA — literatura]`, não variado (herdado do small).
- Frota (Q-01) não medida — o RTFx do medium sob soak/carga (ADR 0003) é o teto da máquina boa.

## Reprodução

```bash
# instância: decode avg=10 do exp-medium-ctc-phoneme (flags de tamanho do medium + fonema)
./zipformer/ctc_decode.py --epoch 30 --avg 10 --use-averaged-model 1 \
  --exp-dir zipformer/exp-medium-ctc-phoneme --use-phoneme-ctc 1 \
  --phoneme-targets-json data/pt/phoneme_targets.json --decoding-method ctc-greedy-search \
  --num-encoder-layers 2,2,3,4,3,2 --feedforward-dim 512,768,1024,1536,1024,768 \
  --encoder-dim 192,256,384,512,384,256 --encoder-unmasked-dim 192,192,256,256,256,192
# local: métricas + IC
python3 training/scripts/cer_from_recogs.py training/results/m4-medium-phoneme/recogs-clean-avg10.txt
python3 training/scripts/bootstrap_wer_ci.py \
  training/results/m4-zipformer-medium/recogs-clean-avg10.txt \
  training/results/m4-medium-phoneme/recogs-clean-avg10.txt
```

Modelo exportado + verificado: `models/m4-final-medium-phoneme/`. Recogs: `training/results/m4-medium-phoneme/`.
