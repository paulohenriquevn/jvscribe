---
type: Medição
title: A escala por parâmetros é 0,53 do linear — 2,89× de modelo custa 1,53× de treino
description: >-
  191,7M contra 66,4M sobre o mesmo corpus, na mesma L4. O treino escala muito abaixo
  do linear, e a Fase 3 cai para ~$283 na vast.ai. O modelo grande ainda diverge.
tags: [medicao, m10, custo, escala, parametros, learning-rate, divergencia]
timestamp: 2026-09-21T19:45:00Z
---

# Escala por parâmetros `[MEDIDO]`

Data: 2026-09-21 · Colab Pro, NVIDIA L4 · mesmo corpus (294,6 h), mesma GPU, mesma receita.
Config escolhida contando parâmetros antes de treinar, não adivinhando dimensões.

## A tabela de candidatos

| parâmetros | configuração |
|---|---|
| 66,4M | medium — `2,2,3,4,3,2` / ffw `512…1536` / dim `192…512` |
| 149,7M | large do icefall |
| 169,1M | large + camadas `2,3,4,6,4,3` |
| **191,7M** | **large + largura** — ffw `768,1024,1536,2560,1536,1024`, dim `256,384,512,896,512,384` |
| 258,0M | xlarge |

## O número

| | 66,4M | 191,7M |
|---|---|---|
| `max-duration` | 700 s | 370 s |
| s/batch | 1,97 | 1,64 |
| **× tempo real** | **347×** | **226×** |
| **h por época (294,6 h)** | **0,85** | **1,30** |
| memória de pico | não capturada | **13.398 MB** de 23.034 |

**2,89× de parâmetros custaram 1,53× de treino — 0,53 do linear.**

A sublinearidade é real e tem explicação: a 66,4M com batch de 700 s a L4 estava
**subocupada**. O modelo maior faz matmuls maiores e usa melhor a GPU. O custo por hora de
áudio sobe bem menos que os parâmetros.

**A previsão de memória errou para mais, e na direção segura:** 3,1 GB de fixo + orçamento de
20 GB previu `max-duration 370`; o pico real foi 13,4 GB, deixando 9,6 GB parados. Há folga
para `max-duration` ~600, que daria batch maior e provavelmente mais throughput ainda.

## A Fase 3, com a escala medida

| corpus × épocas | h de GPU | Colab L4 | A100 vast.ai | dias de L4 |
|---|---|---|---|---|
| 1.500 h × 20 | 133 h | $64 | $42 | 6 |
| 1.500 h × 40 | 265 h | $127 | $85 | 11 |
| 5.000 h × 20 | 442 h | $212 | $142 | 18 |
| **5.000 h × 40** | **885 h** | **$425** | **$283** | **37** |

O plano estima **$600–1.500**. A medição põe o cenário mais caro em **$283 na vast.ai** —
abaixo do piso, mesmo a 40 épocas e 200M. **O R1 fecha.**

O que sobra é prazo: 885 h são **37 dias** de L4 contínua. O Colab Pro não sustenta
(background execution é do Pro+). A vast.ai continua na Fase 3 pelo calendário.

## O modelo diverge — e o LR do recipe não transfere

A loss desceu de 8,66 para **1,580 no batch 1450**, subiu de leve até 1,622 no 1650, e no
**batch 1700 virou NaN**: `RuntimeError: Too many grads were not finite`.

A razão lr/batch de **2,1e-5** — a do `RESULTS.md`, que sustentou 3 épocas a 66,4M — produziu
`base-lr 0.00777` a 370 s e **não transferiu para a largura maior**. O NaN veio **antes do pico
do warmup** (batch 1700 de `warm_step` 2000), com o lr ainda subindo.

Correção aplicada, `[ESTIMATIVA]` de um único NaN e não de uma varredura:

- `base-lr × (66,4/P)^0,5` → **0,0045** a 191,7M
- `--warm-step 4000`, porque a instabilidade apareceu durante a subida

## Dois defeitos meus, cobrados aqui

**1. O vigia estava cego.** Ele olhava `tot_loss`, que é média corrente: no batch do NaN ela
foi de 1,580 a 1,622 — **2,7%**, contra o gatilho de 25%. O sinal imediato é o `loss[loss=nan`
do batch. Agora uma ocorrência mata o run.

**2. Exigi época fechada para reportar custo.** Escrevi que custo mede *throughput* e depois
condicionei o número a um checkpoint. Este run mediu 1.650 batches em 45 min — taxa de sobra —
e **não reportou nada**. Taxa não precisa de época: agora o custo sai de `batches × max-duration
/ tempo`, e a época fechada só decide se o *modelo* presta.

## Limitações

1. **Unidades/h da L4 é `[ESTIMATIVA]`.** As horas são medidas; a conversão para dinheiro não.
2. **A taxa vem de 1.650 batches**, ~57% de uma época. Carregamento e cache podem mudar o
   ritmo no restante — mas a janela é longa e o s/batch é estável nos últimos 1.000.
3. **A correção de LR não foi verificada.** Nenhum run rodou com 0,0045 + warm-step 4000.
4. **0,53 do linear vem de dois pontos.** Não diz onde a curva satura nem se 258M mudaria o
   regime.
5. **`max-duration 370` desperdiçou 9,6 GB.** A escala medida seria outra — provavelmente
   melhor — com o batch que a memória permitia.
