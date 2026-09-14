---
type: Medição
title: T3/Q-12 — quanto corpus PT existe de verdade nas fontes abertas
description: >-
  YODAS pt tem 262 h, não as 15–25 mil que o plano estimava. O volume está no VoxPopuli — que é
  parlamento europeu, o mais distante possível do call center brasileiro.
tags: [medicao, m10, t3, corpus, granary, yodas, voxpopuli, q12, q13]
timestamp: 2026-09-14T15:00:00Z
---

# T3/Q-12 — o inventário real das fontes abertas `[MEDIDO]`

Data: 2026-09-14 · leitura direta dos manifestos e metadados no Hugging Face, sem baixar áudio.

## A pergunta

O plano M10 assumiu que o YODAS-Granary pt oferecia **15–25 mil horas** `[ESTIMATIVA]`, derivadas
do card do dataset ("5.898.764 amostras, 1,5 TB") e de uma duração média suposta. A meta de
25.000 h do T3 dependia inteiramente desse número. Q-12 pedia medi-lo antes de assumir.

## Evidência

### YODAS pt — medido por duas vias independentes

**Via 1, amostragem dos parquets.** 2.084 arquivos `data/pt*/asr_only/*.parquet`; 10 sorteados
com semente fixa, lidos na coluna `duration`:

| | valor |
|---|---|
| linhas por parquet | 337 (194–616) |
| duração por segmento | média **1,36 s**, mediana **0,98 s** (n=3.368) |
| extrapolação | 701.891 segmentos → **265 h** |

**Via 2, os manifestos do `nvidia/Granary`.** Os cinco `pt/yodas/pt_asr_pt*.jsonl` trazem
`duration` preenchida e podem ser somados sem amostragem:

| shard | linhas | horas |
|---|---|---|
| pt000 | 49.667 | 19 |
| pt100 | 178.917 | 64 |
| pt101 | 182.307 | 66 |
| pt102 | 179.285 | 64 |
| pt103 | 138.962 | 50 |
| **total** | **729.138** | **262** |

As duas vias concordam em **1%** (265 contra 262 h). O número é 262 h.

**O card do dataset erra por ~8×** ao anunciar 5,9M amostras: o manifesto soma 729 mil.

### As outras fontes do Granary pt

| fonte | linhas | horas | proveniência |
|---|---|---|---|
| YouTube-Commons (`ytc`) | 254.656 | **959 h** | `[MEDIDO]` — `duration` preenchida |
| VoxPopuli | 2.282.501 | **~12.700 h** | `[ESTIMATIVA]` — ver abaixo |
| YODAS | 729.138 | **262 h** | `[MEDIDO]` |

**O VoxPopuli não pôde ser medido**: o campo `duration` é a string literal `'None'` em **todas** as
2.282.501 linhas. A estimativa vem da contagem de palavras — 114.463.884 palavras, média de 54,0
por linha — dividida por uma taxa de fala:

| taxa | horas |
|---|---|
| 2,2 palavras/s | 14.453 |
| **2,5 palavras/s** | **12.718** |
| 2,8 palavras/s | 11.356 |

## As duas conclusões, e a segunda é pior

### 1. O volume existe, mas não onde o plano procurava

Granary pt soma **~13.900 h**, o que torna a meta de 25.000 h plausível somando as fontes
existentes. Mas **91% desse volume está no VoxPopuli**, e ele é o único que não pôde ser medido.

### 2. A fonte dominante é do domínio errado — responde parcialmente Q-13

**VoxPopuli é o Parlamento Europeu.** Português europeu, fala preparada, registro formal,
vocabulário institucional. O alvo do projeto é **call center brasileiro**: espontâneo, coloquial,
telefônico, com disfluência e sobreposição.

`e11` já mediu que a banda explica **~1/6** do gap de domínio, e que os outros cinco sextos são
espontaneidade, sotaque e conteúdo — exatamente os eixos em que o VoxPopuli está mais longe do
alvo do que o corpus que o projeto já tem.

Um corpus de 25.000 h dominado por parlamento europeu moveria o WER de FLEURS sem mover o de call
center brasileiro. **Volume não é a mesma coisa que corpus.**

### 3. A granularidade do YODAS é um segundo problema

Segmentos com mediana de **0,98 s** são quase palavras isoladas. Um modelo streaming com chunk de
1120 ms (ADR-006) precisa de utterances mais longas que o próprio chunk para aprender a usar
contexto. As 262 h do YODAS pt entram como dado de baixa utilidade para o regime escolhido.

O VoxPopuli é o oposto: 54 palavras por linha, cerca de 22 s por utterance — boa forma para
contexto longo, domínio errado.

## Limitações

1. **O VoxPopuli é `[ESTIMATIVA]`.** A taxa de 2,5 palavras/s é típica de fala preparada, mas não
   foi verificada contra este áudio. O intervalo de 11.356 a 14.453 h reflete só a incerteza da
   taxa, não a de segmentação ou silêncio.
2. **Nada foi baixado em áudio.** Todos os números vêm de manifesto e metadado. Se houver
   divergência entre manifesto e o que os arquivos contêm, ela não aparece aqui.
3. **A fração pt-BR contra pt-PT não foi medida** em nenhuma fonte — nem no `ytc`, nem no YODAS.
   Q-13 continua aberta para as duas fontes de YouTube.
4. **A amostragem do YODAS usou 10 de 2.084 parquets.** A concordância com o manifesto (1%) dá
   confiança, mas não é censo.

## Consequência para o plano

A premissa de T3 — "YODAS-Granary pt resolve o volume" — **está refutada**. O que sobra:

- **~13.900 h** de Granary pt, dos quais ~12.700 h de domínio errado e não medidos.
- **~1.200 h** medidas e de domínio razoável (`ytc` 959 h + YODAS 262 h), mas o YODAS é fragmentado.
- O corpus que o projeto já viu: **~1.413 h** (`e13`).

Chegar a 25.000 h de **dado útil para call center brasileiro** exige fonte que este inventário não
encontrou. As opções que restam estão fora deste documento: Q-09 (Cem Mil Podcasts), coleta
própria de áudio PT-BR, ou aceitar que o corpus será dominado por domínio distante e compensar em
T6 com síntese.
