---
type: Componente de treino
title: Cabeça de fonema auxiliar
description: Linear(512→69) que regulariza o encoder no treino e sai do grafo de inferência. Ganho medido de −4,74% relativo de WER.
tags: [fonema, treino, regularizacao, m4]
timestamp: 2026-07-31T00:00:00Z
---

# Cabeça de fonema auxiliar

`phoneme_output` — `Linear(512 → 69)`, 0,04M parâmetros (0,1% do modelo). São **69 unidades
fonéticas** do PT-BR.

## É supervisão de treino, não de inferência

Ela **sai do grafo ONNX**. O papel é regularizar o encoder: forçá-lo a representar informação
fonética além da ortográfica. No `state_dict` do checkpoint ela aparece como
`phoneme_output.1.weight` / `.bias` — as duas chaves que sobram ao carregar um harness CTC-only.

## Ganho medido

`[MEDIDO]` M4, ablação com e sem a cabeça, mesmo corpus e mesmo test set:

| | WER |
|---|---|
| medium sem cabeça de fonema | 28,86% |
| **medium + cabeça de fonema** | **27,49%** |

**−4,74% relativo**, IC95% [2,79; 6,72], P(ganho ≥ 3%) = 95,7%.

O ganho **transferiu do small para o medium** — o que sustenta mantê-la no modelo final.

Para treinar com ela: `--use-phoneme-ctc 1 --phoneme-targets-json <caminho>`. Ver
[../treino/retomar-o-treino.md](../treino/retomar-o-treino.md).
