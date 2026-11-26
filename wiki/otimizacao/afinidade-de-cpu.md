---
type: Experimento revertido
title: Afinidade de CPU — 25% melhor isolada, 46% pior no sistema
description: sched_setaffinity é herdado pelos filhos. Os parec da captura passavam a disputar os mesmos P-cores.
tags: [afinidade, p-cores, regressao, medicao]
timestamp: 2026-07-31T00:00:00Z
---

# Afinidade de CPU — tentada, medida, revertida

## A medição isolada dizia sim

Numa CPU híbrida (2 P-cores a 5,0 GHz + 8 E-cores a 3,7 GHz), fixar o processo nos P-cores:

| configuração | mediana |
|---|---|
| P-cores `0-3`, intra=2 | **70,2 ms** |
| todos, intra=6 | 94,0 ms |

**25% melhor.** E o `perf` confirmava o mecanismo: IPC **1,87** contra 1,22, e **30,9 G** contra
90,9 G de instruções para o mesmo trabalho.

## No sistema real deu o oposto

RTFx ao vivo caiu de **4,60× para 2,33×**.

Causa, verificada diretamente: **`sched_setaffinity` é herdado pelos processos filhos.**

```
afinidade do processo ANTES:       [0..11]
afinidade do processo DEPOIS:      [0, 1, 2, 3]
afinidade de um SUBPROCESSO filho: [0, 1, 2, 3]   ← o `parec` da captura herda
```

Os dois `parec` da captura passaram a disputar os mesmos 2 P-cores físicos com a inferência,
matando a captura de fome.

E no soak determinístico (sem subprocessos) a afinidade era **neutra**: 6,49× fixado contra
6,88× livre.

## Decisão

**Ganho zero e um modo de falha real → removida.** Há teste de regressão que falha se alguém
reintroduzir qualquer função que mute afinidade de processo no módulo de topologia.

## A lição, que vale além deste caso

**Benchmark de componente não transfere para o sistema.** A medição isolada estava certa sobre
o componente e errada sobre o produto. O que faltava era medir o sistema — e o sistema tem
subprocessos, um segundo canal e captura concorrente que o micro-benchmark não tinha.

Ver [../disciplina/nunca-concluir-de-uma-corrida.md](../disciplina/nunca-concluir-de-uma-corrida.md).
