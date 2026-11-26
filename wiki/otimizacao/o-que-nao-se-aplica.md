---
type: Prior art avaliado
title: FLToP e blank-skipping não se aplicam a este pipeline
description: Duas otimizações do DoD do M6 que comprariam ~0%. Com a fonte de cada uma.
tags: [flotp, blank-skip, prior-art, m6, amdahl]
timestamp: 2026-07-31T00:00:00Z
---

# O que não se aplica

O DoD do M6 no `ROADMAP.md` lista *"FLToP e blank layer-skipping se CTC"*. Fui às fontes: os
dois comprariam ~0% neste pipeline.

## FLToP CTC — `arXiv:2510.09085`

*Frame-Level Token Pruning via Relative Threshold*. Reporta **10,5× de speedup e 2,78× menos
memória**.

Mas:

- o baseline é **beam search com beam=1000** (`Algorithm 1: Beam Search FLToP CTC Decoding`);
- o paper afirma que **não se aplica a greedy argmax** — "greedy decoding selects only the
  single highest-probability token per frame, making token pruning unnecessary";
- ele reduz a **busca do decoder**, não o forward do encoder. A premissa é um regime em que
  "CTC decoding can account for as much as 90% of the processing time" — encoder em GPU, beam
  search em CPU.

**Nosso `ctc_output` custa 0,3%** e o decode é greedy (`argmax` do numpy). Por Amdahl, speedup
infinito de 0,3% rende ~0.

> FLToP passa a valer **se migrarmos para beam search + LM** — que é uma alavanca de WER de
> **4,7% relativo** `[MEDIDO]` ([`e6-beam-lm.md`](../medicoes/e6-beam-lm.md)), não os 10–20%
> que aqui se afirmava, e não de latência. Ver [../treino/corpus.md](../treino/corpus.md).

## Blank layer-skipping — `arXiv:2305.11558` + recipe do icefall

*Blank-regularized CTC for Frame Skipping in Neural Transducer*. Reporta 4× contra transducer
padrão.

O mecanismo, na descrição do recipe `zipformer_ctc_blankskip`: a saída do encoder calcula a
posterior CTC e, para cada frame de saída, o frame é descartado se a posterior de blank passar
de um limiar. Isso acelera o que roda **depois** do encoder — o **joiner do transducer**, que é
executado por frame.

**Somos CTC puro** (`--use-transducer 0`): não há joiner. Descartar frames após o encoder não
devolve tempo de encoder, que já rodou.

## O que economizaria encoder de verdade

**Skipformer** — `arXiv:2403.08258`. Usa uma saída CTC **intermediária** para dividir frames em
cruciais / pulados / ignorados, e só os cruciais seguem para os blocos seguintes. Reduz a
sequência em 22× no LibriSpeech.

Mas é **mudança de arquitetura com retreino**, não otimização de runtime.

## A lição

O profile por operador é o que separa uma otimização aplicável de uma inaplicável. Sem ele, as
duas pareciam razoáveis — estavam no roadmap. Ver
[../medicoes/m6-profile-por-operador.md](../medicoes/m6-profile-por-operador.md).
