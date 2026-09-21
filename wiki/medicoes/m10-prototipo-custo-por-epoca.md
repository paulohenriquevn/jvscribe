---
type: Medição
title: Protótipo Colab — 0,85 h por época, e a Fase 3 reprecificada em 10×
description: >-
  Três épocas completas de zipformer 66M sobre 295 h do TAGARELA numa L4. O custo medido
  põe a Fase 3 uma ordem de grandeza abaixo do que o plano estimava.
tags: [medicao, m10, colab, custo, treino, learning-rate, fase-3]
timestamp: 2026-09-21T18:06:00Z
---

# Protótipo no Colab — custo por época `[MEDIDO]`

Data: 2026-09-21 · Colab Pro, NVIDIA L4 (23 GB) · torch 2.11.0+cu128, k2 1.24.4, python 3.13 ·
zipformer causal 66,4M, transducer podado + CTC · `--max-duration 700 --base-lr 0.015`.

## O corpus, medido

| | |
|---|---|
| shards baixados (estratificados de 1.764) | 31 |
| utterances brutas | 124.970 |
| **mantidas** | **113.311 (90,7%)** |
| descartadas por sotaque pt-pt | 10.992 (**8,8%**) |
| alucinação + ratio + vazio | 667 (0,53%) |
| **duração após o filtro** | **296,8 h** |
| shows distintos / maior show | 187 / 7,0% |
| features em disco (`lilcom_chunky`) | **9,1 GB — 31 MB/h** |
| wavs decodificados intermediários | 33 GB |

Fbank: **44 min** com `--num-jobs 4`. A verificação de `storage_type` passou.

**31 MB/h confirma a medição de storage** ([m10-t3-fbank-e-storage](m10-t3-fbank-e-storage.md),
27 MB/h em FLEURS) e refuta os 115 MB/h do backend numpy. Em 5.000 h: 155 GB contra 575 GB.

## O custo

| | |
|---|---|
| **3 épocas completas** | 2,55 h |
| **por época** | **0,85 h — 51 min** |
| custo na L4 `[ESTIMATIVA de unidades/h]` | 4,1 unidades ≈ **$0,41** |
| checkpoints | 3 × 1.063 MB |

## A Fase 3 reprecificada

O [plano](../../docs/plans/m10-treino-vastai.md) estima a Fase 3 em **$600–1.500**, por
proporção a um run de M5 cujo custo não está registrado em lugar nenhum. É o risco R1.

Escalando o número medido — 0,85 h por época por 295 h de corpus:

| corpus | épocas | h de GPU | Colab L4 | A100 vast.ai |
|---|---|---|---|---|
| 1.500 h | 20 | 87 h | $42 | $28 |
| 5.000 h | 10 | 144 h | $69 | $46 |
| 5.000 h | **40** | 577 h | **$277** | **$185** |
| 5.000 h | 20 | 289 h | $138 | $92 |

**Mesmo a 40 épocas — o regime dos recipes do icefall — a Fase 3 custa menos que o piso de
$600 do plano.** A estimativa por proporção errava por ~2–5×, e a ordem de grandeza da
dúvida some.

⚠️ **O gargalo passa a ser tempo, não dinheiro.** 577 h são **24 dias** de L4 contínua, o que
o Colab Pro não sustenta (background execution é recurso do Pro+). Isso reforça a vast.ai
para a Fase 3 — não pelo custo, pelo prazo.

## O que o run NÃO mostra

**O modelo não converge em 3 épocas, e não era para converger.** Os recipes do icefall rodam
30–50. Mas a curva tem um sinal que precisa ser observado na próxima rodada:

| | tot_loss | simple | pruned | ctc | validação |
|---|---|---|---|---|---|
| ép. 1, batch 0 | 8,99 | 7,37 | 6,89 | 4,66 | 8,882 |
| ép. 1, batch 1000 | 1,476 | 0,799 | 0,930 | 2,048 | — |
| ép. 2, batch 1400 | 1,710 | 0,747 | 0,859 | 2,401 | **1,731** |
| ép. 3, batch 50 | 1,790 | 0,738 | 0,845 | 2,882 | **1,909** |

1. **`simple_loss` e `pruned_loss` estagnam** em ~0,73/0,86 já no fim da época 1 e não melhoram
   mais — 2,5 épocas sem progresso nas perdas do transducer.
2. **`ctc_loss` sobe**: 2,05 → 2,88.
3. **A validação piora** entre a época 2 e a 3: 1,731 → 1,909.

Não é a divergência da tentativa anterior — não houve NaN, nem clipping em massa, e o vigia
não disparou. É estagnação com a CTC se degradando, e **a causa não está determinada**.

## Limitações

1. **Unidades/h da L4 é `[ESTIMATIVA]`.** As horas são medidas; a conversão para dinheiro não.
2. **A extrapolação linear é um piso.** Batch maior usa melhor a GPU; corpus maior move o
   gargalo para I/O. A escala real tende a ser mais barata por hora de áudio e mais lenta por
   época do que a reta sugere.
3. **Três épocas não dizem nada sobre WER.** Nenhum decode foi rodado.
4. **A estagnação não foi diagnosticada.** LR, escala da CTC (`--ctc-loss-scale 0.2`) e
   qualidade do pseudo-rótulo são candidatos, nenhum testado.
5. **O dev split é uma fatia contígua**, não shows disjuntos — a validação pode compartilhar
   locutor com o treino. Para custo isso é irrelevante; para o número 1.909, não.
