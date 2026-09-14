---
type: Medição
title: T1b — latência compra capacidade, e o teto de T1 estava errado
description: >-
  53% do custo do encoder é pago POR INVOCAÇÃO e some quando o chunk cresce. Dobrar a latência
  de 560 ms para 1,12 s eleva o teto de 237M para 376M parâmetros e melhora o WER ao mesmo tempo.
tags: [medicao, m10, t1b, latencia, chunk, rtfx, teto, correcao]
timestamp: 2026-09-14T12:00:00Z
---

# T1b — o custo por invocação, e a correção do teto `[MEDIDO]`

Data: 2026-09-14 · i7-1355U, `taskset -c 0-3`, `num_threads=2`, int8, greedy, 2 canais ·
`sherpa-onnx` 1.13.8.

> ⚠️ **Este documento corrige [`m10-t1-teto-de-cpu.md`](m10-t1-teto-de-cpu.md).** O teto de
> **174M** publicado lá está errado. Ver § A correção.

## A pergunta

O dono declarou em 2026-09-14 que aceita latência em troca de qualidade. Isso parecia um
trade-off, e não é: numa arquitetura cache-aware, chunk maior melhora o WER **e** o RTFx ao
mesmo tempo. A pergunta operacional é **quanto** de cada um, e a resposta depende de uma
decomposição que T1 não fez.

## O modelo de custo, agora com os dois termos separados

T1 ajustou `tempo = a + b·P` e encontrou `a = 68 ms/s`. Aquele `a` mistura duas coisas que se
comportam de forma oposta quando a latência muda: o que é pago **por invocação** encolhe com
chunk maior, o que é pago **por segundo de áudio** não muda. Cinco pontos separam os termos:

| modelo | chunk | custo medido | RTFx agregado | por canal |
|---|---|---|---|---|
| FastConformer ~115M | 480 ms | 112,1 ms/s | 8,92× | 4,46× |
| FastConformer ~115M | 1040 ms | 78,3 ms/s | 12,77× | 6,39× |
| Nemotron ~600M | 320 ms | 520,6 ms/s | 1,92× | 0,96× |
| Nemotron ~600M | 560 ms | 360,8 ms/s | 2,77× | 1,39× |
| Nemotron ~600M | 1120 ms | 241,1 ms/s | 4,15× | 2,07× |

Regressão em `1/T` por modelo, depois em `P`:

```
tempo(T, P) [ms por segundo de áudio] = (7,69 + 0,19509·P)/T + (29,53 + 0,17218·P)
                                         └──── por invocação ────┘  └── por segundo ──┘
```

com `T` em segundos e `P` em milhões de parâmetros. Erro máximo de previsão sobre os cinco
pontos: **1,4%**.

| termo | valor | o que é |
|---|---|---|
| α | 7,69 ms/invocação | overhead de chamada, independente do modelo |
| β | 0,195 ms/invocação por M | **o modelo, pago por chunk** — cache, cópia de estado |
| γ | 29,53 ms/s | featurização; nunca encolhe |
| δ | 0,172 ms/s por M | o encoder propriamente |

**O achado: β > δ.** Para o encoder, **53% do custo é pago por invocação** e apenas 47% por
segundo de áudio. É por isso que dobrar o chunk rende ~50% de RTFx — e é o que torna latência
uma moeda que compra capacidade.

Separação estatística, 2 canais, n=8, `comparar_pareado`:

- Nemotron 320 ms → 1120 ms: **+2,208×**, IC95% [+2,156; +2,254]
- FastConformer 480 ms → 1040 ms: **+4,043×**, IC95% [+3,637; +4,476]

Nos dois casos o IC não cruza zero.

## O teto de parâmetros é uma função da latência

Resolvendo o modelo para o alvo do RNF-01 (3× por canal = 6× agregado = 166,7 ms/s):

| chunk | teto | WER do Nemotron em pt `[LITERATURA]` |
|---|---|---|
| 320 ms | **145M** | 5,81% |
| 480 ms | 209M | — |
| **560 ms** | **237M** | 5,65% |
| 1040 ms | 361M | — |
| **1120 ms** | **376M** | **5,48%** |
| 2240 ms | 516M | não publicado |

E o que modelos concretos entregariam por canal:

| | 560 ms | 1120 ms |
|---|---|---|
| 64M (o modelo atual) | 6,53× | 8,54× |
| 150M | 4,12× | 5,66× |
| 300M | 2,51× ❌ | 3,56× ✅ |

Os WER da última coluna vêm do model card do `nemotron-3.5-asr-streaming-0.6b` (modo LangID),
não de medição própria — são `[LITERATURA]` e servem só para mostrar a forma da curva. A curva
**satura**: os 560 ms que separam 560 ms de 1,12 s compram 0,17 pp.

## A correção

`m10-t1-teto-de-cpu.md` derivou `b = 0,5667 ms/s por milhão` comparando o FastConformer **com
chunk de 480 ms** contra o Nemotron **com chunk de 560 ms**. Os chunks eram diferentes, então
aquele `b` absorveu parte do efeito de latência e ficou inflado — 0,567 contra os 0,172 que a
medição com chunk controlado mostra.

Consequência: **o teto a 560 ms não é 174M, é 237M.** A conclusão qualitativa de T1 sobrevive
intacta (o custo não é linear, há um piso fixo, o Nemotron de 600M reprova o RNF-01 em 2
P-cores), mas o número foi revisado para cima em 36%.

O erro é o mesmo que a disciplina deste projeto já nomeia: comparar duas configurações que
diferem em **mais de uma variável** e atribuir toda a diferença a uma delas.

## Limitações

1. **Os WER são `[LITERATURA]`**, do model card. A medição própria em FLEURS pt
   ([`m10-t2-regua-publica.md`](m10-t2-regua-publica.md)) rodou só a 560 ms.
2. **Dois tamanhos de modelo** definem a reta em `P`. A linearidade entre 115M e 600M não foi
   verificada com um ponto intermediário.
3. **O vocabulário difere** entre os dois modelos (1.025 contra 13.088 tokens), e o joiner é
   invocado a cada passo. Parte do `β` atribuído ao tamanho do modelo é, na verdade, tamanho de
   vocabulário — o que torna o teto **conservador** para um monolíngue PT-BR.
4. **RNF-04 e RNF-05 seguem não exercitados**: sem soak de 30 min e sem carga concorrente. O
   sinal de degradação com uso prolongado registrado em T1 não foi diagnosticado.
5. **Acima de 1120 ms não há artefato publicado**, então a linha de 2240 ms é extrapolação do
   modelo, não medição.

## Conclusão

Latência não é o preço da qualidade neste desenho — é o que **paga** por ela. Cada duplicação
do chunk corta pela metade o termo `(α + β·P)/T`, que responde por mais da metade do custo do
encoder, e ainda melhora o WER porque o modelo vê mais contexto antes de decidir.

Para o M10 isso significa que **o tamanho do modelo e o orçamento de latência são uma decisão
só**, e não duas. A 1,12 s de chunk o teto é de 376M — quase seis vezes o modelo atual de 64M.
