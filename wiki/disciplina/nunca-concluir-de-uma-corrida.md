---
type: Regra de método
title: Nunca conclua de uma corrida só
description: Três erros documentados neste projeto. O gate é bootstrap pareado com melhor=None quando o IC cruza zero.
resource: jvscribe/common/stats.py
tags: [medicao, bootstrap, ic95, ruido]
timestamp: 2026-07-31T00:00:00Z
---

# Nunca conclua de uma corrida só

Este projeto declarou vencedor a partir de corrida única **três vezes** e errou nas três:

| conclusão | o que era |
|---|---|
| "intra=8 é 30,9% melhor" | não reproduziu |
| "158,8 ms vs 169,1 ms" | a **mesma** configuração — 35 ms de ruído |
| "afinidade nos P-cores é 25% melhor" | no sistema real piorou 46% |

## O erro não é de quem mede — é da ferramenta permitir

`jvscribe/common/stats.py::comparar_pareado()`:

- devolve **`melhor=None`** quando o IC95% do delta cruza zero;
- **recusa** amostras com n < 3, em vez de devolver um número que ninguém pode contestar;
- exige listas do mesmo tamanho — o pareamento pressupõe correspondência 1-para-1.

Um dos 9 testes é literalmente *"configurações idênticas nunca produzem vencedor"*.

## Por que pareado

As configurações são medidas em **round-robin**, uma após a outra na mesma rodada: a carga da
máquina entra igual nas duas e some na diferença.

Foi o que separou 15,99% de 17,32% de WER quando a comparação não-pareada não separava. E foi o
que mostrou que `intra=2` e `intra=6` são **indistinguíveis** quando as medianas sugeriam o
contrário.

## Máquina sob carga não mede

Mesma configuração, harness ao vivo, quatro corridas: **3,51× · 2,90× · 2,82× · 2,50×**.

Confira `uptime` antes. O `calibrate.py` avisa acima de load 1,0 — o aviso não é decorativo.

## O harness ao vivo VALIDA, não compara

Ele depende de alto-falante, microfone e timing de reprodução. Para comparar configuração use
`runtime_bench.py` (pareado) ou `stress_test.py` (determinístico).
