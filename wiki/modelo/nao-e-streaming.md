---
type: Restrição de arquitetura
title: O modelo não é streaming
description: O encoder é não-causal. Cada atualização reprocessa a janela inteira — 10,6× de retrabalho medido por hop.
tags: [streaming, causal, latencia, m6, restricao]
timestamp: 2026-07-31T00:00:00Z
---

# O modelo não é streaming

É **não-causal**: a atenção enxerga o contexto inteiro nos dois sentidos.

## Três confirmações independentes

| fonte | evidência |
|---|---|
| metadado do artefato | `comment: "non-streaming zipformer2 CTC"`, carimbado pelo exportador do k2-fsa |
| grafo ONNX | entradas `x`, `x_lens`; saídas `log_probs`, `log_probs_len` — **nenhum tensor de estado** |
| scripts de treino | `run_ft_*.sh` nunca passam `--causal`; o default do icefall é `False` |

Um modelo streaming teria tensores de cache entrando e saindo do grafo — é o
`GetEncoderInitStates()` que o `sherpa-onnx` usa (`csrc/online-zipformer2-transducer-model.h:32`).

## O que isso custa

O motor de tempo real **simula** streaming com janela deslizante + LocalAgreement-2 (a técnica
do Whisper-Streaming). Funciona, mas cada hop reprocessa a janela toda:

| o que se processa | tempo |
|---|---|
| a janela inteira de 6 s (o que fazemos) | **121 ms** |
| só os 0,5 s novos (o que um modelo com cache faria) | **11 ms** |

**10,6× de retrabalho por hop** `[MEDIDO]`. O custo é linear nos frames (~0,2 ms/frame), então
não há explosão quadrática de atenção nesses comprimentos — é retrabalho puro.

Ressalva: a razão real seria menor que 10,6×, porque entradas pequenas pagam overhead fixo por
chamada (1,0 s custa 0,164 ms/frame contra 0,229 ms/frame de 0,5 s).

## Por que isso é o piso da latência

Com dois canais decodificando em série, a latência tem piso
`hop + decode(própria) + decode(do outro canal)`. Na melhor configuração com texto ainda
utilizável, o p99 chega a **513 ms** contra o alvo de 500 ms do RNF-02.

Nenhuma calibração remove esse termo. Ver
[../otimizacao/o-que-nao-se-aplica.md](../otimizacao/o-que-nao-se-aplica.md).

## O caminho de saída

Treinar com `--causal 1` (chunked attention masking) e reexportar com tensores de estado.
Isso é trabalho de GPU, não de runtime.

E **não custa acurácia**: `arXiv:2506.14434` — *Unifying Streaming and Non-streaming
Zipformer-based ASR* — mostra um único encoder servindo os dois modos com right-context
dinâmico, entregando **−7,9% de WER relativo**.
