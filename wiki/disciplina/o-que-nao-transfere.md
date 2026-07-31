---
type: Regra de método
title: O que não transfere
description: Componente ≠ sistema. Isolado ≠ sob carga. Uma máquina ≠ a frota. Cada um custou um erro.
tags: [metodo, falacias, generalizacao]
timestamp: 2026-07-31T00:00:00Z
---

# O que não transfere

## Componente → sistema

A afinidade de CPU era **25% melhor** medida isoladamente e **46% pior** no pipeline real, porque
o sistema tem subprocessos de captura que o micro-benchmark não tinha. Ver
[../otimizacao/afinidade-de-cpu.md](../otimizacao/afinidade-de-cpu.md).

## Isolado → sob carga

O RTFx do modelo isolado é 40×; com dois canais, captura e features, o pipeline entrega ~4×.
Taxas somam pelo **inverso**: ASR a 3× somado a diarização a 3× dá 1,5×. É por isso que o
RNF-07 exige ASR isolado ≥ 6× para o pipeline fechar os 3× do RNF-01.

## Uma máquina → a frota

Todo dimensionamento assume um i7 híbrido medido. O parque BYOD real é `[DESCONHECIDO]` (Q-01) e
provavelmente muito pior. **Extrapolar daqui para "a frota" é a falácia mais provável neste
projeto.**

## Benchmark público → call center

FLEURS é leitura de notícias em banda larga. Telefonia 8 kHz custa fator 2–3× `[LITERATURA]`, e
fala espontânea é regime mais difícil. Um WER de 15,99% em FLEURS **não** é um WER de 15,99% em
produção.

## GPU → CPU

Regimes de memória e paralelismo diferentes. Um speedup reportado em GPU não sustenta conclusão
sobre CPU — foi assim que o FLToP entrou no roadmap: o paper mede num regime em que o decoder é
90% do tempo, e aqui ele é 0,3%. Ver
[../otimizacao/o-que-nao-se-aplica.md](../otimizacao/o-que-nao-se-aplica.md).

## Arquitetura → arquitetura sem parentesco

O erro original registrado no PRD: benchmarks medidos em Moonshine sustentando a escolha de
Zipformer. Modelos sem parentesco não transferem número.
