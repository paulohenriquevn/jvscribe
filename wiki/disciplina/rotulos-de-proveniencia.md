---
type: Regra de método
title: Rótulos de proveniência — sem rótulo, o número não existe
description: MEDIDO, LITERATURA, FONTE-REPO, ESTIMATIVA, DESCONHECIDO. Cada um exige uma coisa diferente.
tags: [evidencia, rotulos, proveniencia]
timestamp: 2026-07-31T00:00:00Z
---

# Rótulos de proveniência

| rótulo | significa | exige |
|---|---|---|
| `[MEDIDO]` | rodamos o experimento | comando exato, hardware, nº de repetições, dispersão |
| `[LITERATURA]` | reportado por terceiro | citação resolvível + condições do experimento original |
| `[FONTE-REPO]` | fato lido no código de um peer clonado | citação `arquivo:linha` que **exibe** o fato |
| `[ESTIMATIVA]` | derivado por cálculo | fórmula explícita + premissas |
| `[DESCONHECIDO]` | não sabemos | o que seria preciso medir para saber |

Um `[LITERATURA]` **nunca** vira `[MEDIDO]` por conveniência. Um `[ESTIMATIVA]` que sustenta
decisão bloqueante deve virar `[MEDIDO]` antes de a decisão ser travada.

## Promoções que já aconteceram

**Checkpoint averaging** era `[ESTIMATIVA]` — "a média tende a bater abaixo do melhor single".
Virou `[MEDIDO]`: 15,99% contra 17,32%, IC95% do delta [−2,25; −0,43] pp. É o que produziu o
modelo entregue.

## `[FONTE-REPO]` exige que a linha citada EXIBA o fato

Citar uma linha vizinha que não mostra a afirmação é, em miniatura, a falácia que originou a
correção de método deste projeto. Exemplos válidos:

- `sherpa-onnx/csrc/session.cc:149,156` — configura `intra_op` **e** `inter_op`
- `sherpa-onnx/csrc/features.h:106,117,131` — features incrementais por índice de frame
- `sherpa-onnx/csrc/online-zipformer2-transducer-model.h:32` — `GetEncoderInitStates()`

## Ainda `[DESCONHECIDO]` neste projeto

- WER em telefonia 8 kHz e em fala espontânea de call center
- Equivalência batch↔streaming
- Piso da frota BYOD (Q-01)
- RNF-04 (estabilidade térmica) e RNF-05 (carga concorrente) — nunca exercitados
