---
type: Lições
title: Armadilhas de treino já pagas com run inteiro
description: LR de cabeça fresca, fp16, codec-aug, disco cheio. Cada uma custou um run.
tags: [treino, armadilhas, lr, fp16, augmentacao]
timestamp: 2026-07-31T00:00:00Z
---

# Armadilhas de treino

## LR de cabeça fresca

`0.0001` numa cabeça recém-inicializada **quebra o treino**: platô em blank, WER 100%. O valor
que funciona é da ordem de **`0.03` na cabeça** e `0.002` no corpo.

## fp16 colapsa sob augmentação

O `grad_scale` colapsa quando a augmentação introduz choque. Os runs usam **`--use-fp16 0`**.

## Full-finetune com codec-aug colapsa o greedy

`[MEDIDO]` 2×: o greedy vai para ~98%. Daí o `run_ft_freeze.sh`, que **congela o encoder
profundo** (63M fixos na representação boa) e adapta só frontend + cabeças — ~0,9M treináveis,
1,4% dos parâmetros. É o equivalente barato de um adapter: com o corpo fixo, o modelo não
**pode** driftar para blank.

## `--enable-musan 0` no run de convergência

A augmentação foi desligada **de propósito** para isolar a convergência primeiro. Religá-la é
uma das alavancas de regularização — ver [corpus.md](corpus.md).

## Disco cheio corrompe o último `.pt`

Já aconteceu: 150 GB enchem com checkpoints de ~1 GB, e o último sai truncado. Pode nem
levantar erro na hora. Pode-se detectar pelo tamanho — um modelo de 64M em fp32 ocupa ~257 MB.

Poda proativa durante o treino, e verificar o tamanho antes de confiar num download.
