---
type: Arquitetura
title: Zipformer-CTC — grafo, stacks e onde o custo mora
description: 64,29M parâmetros em 6 stacks. O encoder_embed tem 1% dos pesos e 22% do custo.
tags: [arquitetura, zipformer, encoder, profile]
timestamp: 2026-07-31T00:00:00Z
---

# Arquitetura

```
áudio 16 kHz → fbank 80-bin (janela 25 ms, passo 10 ms, kaldi/HTK) → (T, 80)
  → encoder_embed  Conv2dSubsampling   0,61M   (T/2, 192)
  → encoder        Zipformer2 6 stacks 63,38M  (T/4, 512)
  → ctc_output     Linear(512→500)     0,26M   log-probs
  → phoneme_output Linear(512→69)      0,04M   ← só no treino
```

## Subamostragem `[MEDIDO]`

| entrada | saída | fator |
|---|---|---|
| 100 frames (1,0 s) | 23 | 4,3× |
| 600 frames (6,0 s) | 148 | 4,1× |

**Um frame de saída a cada ~41 ms** — é a granularidade máxima de timestamp que o CTC pode dar.

## Os seis stacks

| stack | camadas | dim | downsampling | parâmetros |
|---|---|---|---|---|
| 0 | 2 | 192 | 1 | 2,06M |
| 1 | 2 | 256 | 2 | 3,83M |
| 2 | 3 | 384 | 4 | 11,66M |
| **3** | **4** | **512** | **8** | **30,34M** |
| 4 | 3 | 384 | 4 | 11,66M |
| 5 | 2 | 256 | 2 | 3,83M |

**O stack 3 concentra 48% do encoder** — mais parâmetros onde há menos frames.

Os fatores de downsampling não são default assumido: estão nos pesos
(`encoder.encoders.{1..5}.downsample.bias` com shapes 2/4/8/4/2, e `downsample_output.bias` 2).

As quatro flags que reconstroem isto são **obrigatórias** e não estão dentro do `.pt` —
ver [../treino/retomar-o-treino.md](../treino/retomar-o-treino.md).

## O contraste que o profile revelou

| módulo | % dos parâmetros | % do custo |
|---|---|---|
| `encoder_embed` | **1,0%** | **22,0%** |
| `encoder` | 98,6% | 75,6% |
| `ctc_output` | 0,4% | 0,3% |

O `encoder_embed` tem 1% dos pesos e come 22% do tempo, porque é o único módulo que processa a
entrada em **resolução plena** (100 frames/s × 80 bins) antes de qualquer subamostragem. Suas
convoluções custam 321 µs por nó — o operador mais caro do grafo.

Detalhe em [../medicoes/m6-profile-por-operador.md](../medicoes/m6-profile-por-operador.md).
