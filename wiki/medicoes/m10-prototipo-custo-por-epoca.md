---
type: Medição
title: Protótipo Colab — 0,89 h por época, e a divergência que a mediu
description: >-
  Primeiro treino real do M10. Diverge por LR alto contra batch pequeno, mas entrega o
  número que o run existia para produzir: o custo por época numa L4.
tags: [medicao, m10, colab, custo, treino, divergencia, learning-rate]
timestamp: 2026-09-21T14:10:00Z
---

# Protótipo no Colab — custo por época `[MEDIDO]`

Data: 2026-09-21 · Colab Pro, NVIDIA L4 · torch 2.11.0+cu128, k2 1.24.4, python 3.13 ·
zipformer causal 66,4M, transducer podado + CTC · 112.311 cuts do TAGARELA (31 shards).

## O número

| | |
|---|---|
| setup (start → batch 0) | 59 s |
| **época 1 (batch 0 → checkpoint)** | **0,89 h — 53 min** |
| custo na L4 `[ESTIMATIVA de unidades/h]` | 4,3 unidades ≈ **$0,43 por época** |

Isto **retira o risco R1** do [plano de treino](../../docs/plans/m10-treino-vastai.md), que
estimava a Fase 3 por proporção a um run de M5 cujo custo não está registrado em lugar
nenhum.

**Custo por época mede throughput, não convergência.** O forward e o backward custam o
mesmo numa época que aprende e numa que diverge — por isso o número vale, embora o modelo
não valha nada.

## O que quebrou

A loss desce de 9,0 para 1,5 nos primeiros 400 batches — o modelo **estava aprendendo** —
e depois sobe de volta, monotonicamente, por mais de 3.000 batches até virar NaN.

| marco | tot_loss |
|---|---|
| época 1, batch 0 | 9,011 |
| época 1, batch 750 (mínimo) | **1,514** |
| época 1, batch 2000 | 1,724 |
| validação da época 1 | 1,921 |
| **validação da época 2** | **2,284** |
| época 2, batch ~1400 | NaN → `bad-model-0.pt` |

## A causa: a razão LR/batch, não o LR sozinho

`encoder_embed.conv.0.weight` domina `tot_sumsq` desde o batch 0 — chega a 0,93 da norma
total do gradiente. O `percent-clipped` sobe de 0% a **67%**: dois terços dos batches
sendo cortados pelo otimizador.

| | batch efetivo | base-lr | razão |
|---|---|---|---|
| `RESULTS.md` do recipe | ~2.200 s (2×1000 ou 4×550) | 0,045 | **2,0e-5** |
| esta execução | 300 s (1×300) | 0,030 | **1,0e-4** |

**Cinco vezes mais quente.** E os dois erros vieram de fontes diferentes:

- `--base-lr 0.03` foi importado da lição de M5 — que era **finetune de cabeça fresca sobre
  encoder pré-treinado**. Aqui o treino é **do zero**. A lição foi aplicada fora do regime
  que a produziu.
- `--max-duration 300` foi escolhido por medo de OOM. O log mostra pico de **9.090 MB** numa
  L4 de 24 GB — folga de 2,5× que não estava sendo usada, e que teria dado batch maior
  **e** mais throughput.

## Correção aplicada

`--max-duration 700` + `--base-lr 0.015` → razão 2,1e-5, a do recipe. Não verificado: nenhum
run rodou com esta configuração ainda.

O notebook ganhou um **vigia de divergência** — mata o treino quando a `tot_loss` fica 25%
acima do mínimo por 4 logs seguidos. Os 75 minutos gastos depois que o problema já era
visível no log são o custo de não ter isso.

## Limitações

1. **Unidades/h da L4 é `[ESTIMATIVA]`**, não medida. As horas são medidas; a conversão para
   dinheiro não.
2. **Uma época só.** A segunda não terminou, então não há como ver se o custo por época é
   estável — carregamento de features e cache do dataloader podem mudar da 1ª para a 2ª.
3. **A extrapolação linear para 5.000 h é um piso**, não uma estimativa: batch maior usa
   melhor a GPU e corpus maior move o gargalo para I/O.
4. **O corpus efetivo não foi registrado.** A célula que imprime `HORAS_TREINO` rodou, mas a
   saída não foi capturada — 112.311 cuts, duração total não anotada.
