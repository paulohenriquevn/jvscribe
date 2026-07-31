---
type: Achado de hardware
title: CPU híbrida — spin-wait em barreira, não limite de memória
description: Seis threads executam 3× mais instruções para o mesmo trabalho. O cache miss é idêntico.
resource: jvscribe/common/cpu.py
tags: [cpu, hibrida, threads, perf, ipc]
timestamp: 2026-07-31T00:00:00Z
---

# CPU híbrida e contagem de threads

A máquina de referência é híbrida: `cpu0-3` a **5000 MHz** (2 P-cores com hyperthreading) e
`cpu4-11` a **3700 MHz** (8 E-cores).

## O mecanismo, via `perf`

| | intra=2 | intra=6 |
|---|---|---|
| tempo | **65,9 ms** | 81,2 ms |
| **IPC** | **1,87** | 1,22 |
| **instruções** | **30,9 G** | **90,9 G** |
| cache miss | 26,9% | 25,4% |

O cache miss é **igual** nos dois — logo **não é memory-bound**, como o IPC baixo isolado
sugeriria. Seis threads executam **3× mais instruções para o mesmo trabalho**: spin-wait em
barreira. Numa CPU híbrida cada barreira do matmul espera o E-core.

## O que ficou e o que não

`intra_op_num_threads` passa a vir da topologia (`cpu.detectar()`), que lê o sysfs em
tempo de execução — então **se adapta sozinho** ao trocar de máquina.

Mas o ganho é `[MEDIDO]` **em inferência isolada**. No nível de sistema é `[DESCONHECIDO]`: com
a máquina em load 3–4, `intra=2`, `4` e `6` são indistinguíveis (medianas 4,20 / 4,50 / 4,54
com dispersões que se sobrepõem inteiramente).

O default de `intra=2` fica por um argumento que **não depende de velocidade**: se as
configurações são indistinguíveis em vazão, escolhe-se a que ocupa 2 dos 12 lógicos em vez de
6 — e o RNF-05 exige um softphone rodando junto.

**Afinidade é caso à parte e foi revertida**: [afinidade-de-cpu.md](afinidade-de-cpu.md).
