---
type: Índice
title: Otimização do runtime
description: O que foi medido e aplicado, o que não se aplica a este pipeline, e o que foi tentado e revertido.
tags: [otimizacao, runtime, m6]
timestamp: 2026-07-31T00:00:00Z
---

# Otimização do runtime

| alavanca | ganho | estado |
|---|---|---|
| **Treino causal + export com estado** | **~10,6×** | não feito — é trabalho de GPU |
| Sessão ONNX (arena ON + `inter_op`) | −17,1% IC95% [−36,9; −17,8] ms | ✅ aplicado |
| [Cache incremental de fbank](../motor/fbank-incremental.md) | elimina 21,6% de retrabalho | ✅ aplicado |
| Fusão da ativação Swoosh | até ~15% | não tentado |
| **FLToP CTC** | **~0%** | ❌ [não se aplica](o-que-nao-se-aplica.md) |
| **Blank layer-skipping** | **~0%** | ❌ [não se aplica](o-que-nao-se-aplica.md) |
| **Afinidade de CPU** | 25% isolado, **−46% no sistema** | ❌ [revertida](afinidade-de-cpu.md) |

## Conceitos

- [o-que-nao-se-aplica.md](o-que-nao-se-aplica.md) — FLToP e blank-skip, com a fonte de cada
- [afinidade-de-cpu.md](afinidade-de-cpu.md) — a otimização que piorou o sistema, e por quê
- [topologia-de-cpu.md](topologia-de-cpu.md) — CPU híbrida, spin-wait e contagem de threads
