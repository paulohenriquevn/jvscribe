---
type: medicao
title: E12 — realçar o áudio antes do ASR piora, e a subtração espectral é catastrófica
description: >-
  Três técnicas de realce testadas no recorte mais difícil (NURC-SP quality=low). Todas pioram.
  Subtração espectral custa +15,72 p.p. Confirma localmente um achado consolidado da literatura.
tags: [medicao, realce, denoising, pre-processamento, nurc, e12]
timestamp: 2026-08-01T00:00:00Z
---

# E12 — dá para melhorar o áudio antes de entregar ao modelo?

## A pergunta

Se o áudio ruim custa WER (E11 mostrou que banda estreita custa ~6 p.p.), a ideia natural é
**consertar o sinal antes do reconhecedor**. É o que o dono perguntou, e é o que a intuição manda.

## Evidência

`[MEDIDO]` NURC-SP `quality=low` (o recorte mais difícil que este projeto mediu), n=100, greedy,
régua estrita:

| tratamento | WER | Δ |
|---|---|---|
| **nenhum (cru)** | **50,20%** | — |
| pré-ênfase 0,97 | 50,36% | +0,16 |
| realce de agudos +12 dB acima de 1500 Hz | 50,44% | +0,24 |
| **subtração espectral** (α=1,5, ruído dos 200 ms iniciais) | **65,92%** | **+15,72** |

**As três pioram.** As duas equalizações são praticamente neutras (dentro do ruído); a subtração
espectral é **catastrófica** — 31% relativo de degradação.

## Não é a primeira vez neste projeto

O `probes/tta_feature_align_probe.py` (DISC-05) já tinha tentado a mesma ideia no domínio das
features — transformação afim global por mel-bin para trazer o domínio telefônico de volta às
estatísticas de wideband. Resultado registrado: **−24,6 p.p.**

⚠️ **Esse número vive apenas num docstring**, citado de segunda mão em
`probes/blank_penalty_probe.py`. Não há artefato dele em `wiki/medicoes/`. Um resultado negativo
dessa magnitude precisa estar na wiki, não escondido num comentário — enquanto não estiver, a
mesma ideia será reproposta.

## Por que piora — o mecanismo

`[LITERATURA]` verificado em 2026-08-01. O achado é consolidado e recente:

| fonte | achado |
|---|---|
| [`arXiv:2512.17562`](https://arxiv.org/abs/2512.17562) — *When De-noising Hurts* | realce degrada ASR **em todas as condições de ruído e em todos os modelos** testados |
| [`arXiv:2603.04710`](https://arxiv.org/pdf/2603.04710) — *When Denoising Hinders* | separação/denoising piora ASR zero-shot |
| [`arXiv:2501.02452`](https://arxiv.org/pdf/2501.02452) | o conserto é **treinar junto** (módulo de ponte), não encaixar um realçador pronto |

O mecanismo é sempre o mesmo: **o realce troca uma degradação que o modelo já viu no treino por
um artefato que ele nunca viu.** Modelos ponta-a-ponta modernos já são robustos a ruído natural; o
"musical noise" da subtração espectral, a descontinuidade espectral e a perda de pistas acústicas
são um domínio novo, e pior que o original.

Nossos 50,20% de baseline são a prova disso na direção positiva: o modelo aguenta um áudio com
99% da energia abaixo de 1,5 kHz e SNR de 17,8 dB. Ele não aguenta o que a subtração espectral faz
com esse mesmo áudio.

## Conclusão

**Realce genérico pré-ASR está refutado para este sistema.** Não é "não tentamos direito" — é o
resultado esperado pela literatura, reproduzido aqui e já reproduzido antes em outro domínio.

O que a literatura aponta como caminho que funciona é **outro**: treinar o realçador **junto** com
o reconhecedor, ou treinar o reconhecedor **na condição degradada** (augmentação). Os dois exigem
GPU e mudam o modelo — não são pré-processamento.

## Limitações

- **Três técnicas clássicas, não neurais.** Modelos de realce neural (DeepFilterNet, DNS-challenge)
  **não** foram testados. A literatura acima os inclui no achado negativo, mas isso é
  `[LITERATURA]`, não medição nossa. Um realçador neural forte poderia se comportar diferente — e
  custaria orçamento de RTFx que o E7 mostrou não render por outras vias.
- **n=100, um recorte, greedy.** Suficiente para um efeito de 15 p.p.; insuficiente para afirmar
  que os +0,16 e +0,24 das equalizações são reais e não ruído.
- **Não testamos extensão de banda (BWE).** É a técnica que ataca diretamente o fator que E11
  mediu como causal. Continua `[DESCONHECIDO]`, e é a única desta família que eu ainda
  investigaria — com a expectativa temperada por tudo acima.
