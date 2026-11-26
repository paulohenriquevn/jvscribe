---
type: Medição
title: Q-14 e RNF-04 — o regime sustentado custa 20,6% a mais, mas não degrada
description: >-
  30 min contínuos: a queda vista em T1 e T2 não era térmica, era carga concorrente. O RNF-04
  passa pela primeira vez. Mas o teto de parâmetros cai de 376M para 294M.
tags: [medicao, m10, q14, rnf04, soak, sustentado, teto]
timestamp: 2026-09-14T20:00:00Z
---

# Q-14 / RNF-04 — 30 minutos contínuos `[MEDIDO]`

Data: 2026-09-14 · i7-1355U, `taskset -c 0-3`, `num_threads=2`, int8, greedy · chunk **1120 ms**,
2 canais · `nemotron-3.5-asr-streaming-0.6b` · 30 minutos ininterruptos.

## A pergunta

Duas medições anteriores viram o RTFx cair com o tempo, e **nenhuma das duas foi desenhada para
medir isso**: T1 observou 2,19× → 1,77× ao longo de 10 rodadas; T2 observou 2,47× → 1,94× ao longo
de 400 utterances. Se a queda fosse térmica e se estabilizasse ~20% abaixo do pico, o teto de
376M do [`m10-t1b`](m10-t1b-latencia-e-teto.md) cairia junto — e todo o dimensionamento do M10
com ele.

O `ROADMAP.md` também registra **RNF-04 (estabilidade térmica ≥ 80% aos 30 min)** como nunca
exercitado em condição válida.

## Evidência

| | valor |
|---|---|
| duração | 30 minutos contínuos |
| mediana | **3,44×** agregado = **1,72× por canal** |
| primeiros 3 min | 3,68× |
| últimos 3 min | 3,59× |
| **degradação** | **+2,4%** (o fim é 2,4% mais lento que o início) |
| p10 / p90 | 2,65× / 3,90× |
| pior minuto | 2,41× (1,20× por canal) |
| **RNF-04** | ✅ **PASSA** — 97,6% do inicial aos 30 min, contra o alvo de 80% |

Primeiros cinco minutos: 3,78 · 3,51 · 3,68 · 4,10 · 3,48
Últimos cinco minutos: 3,56 · 3,58 · 3,57 · 3,59 · 3,91

## Conclusão 1 — não há degradação térmica

**A queda vista em T1 e T2 não era térmica; era carga concorrente.** Em T2 havia download de
artefatos rodando em paralelo, o que o próprio documento registrou como contaminação do RTFx. Numa
corrida limpa de 30 minutos a série é plana: a diferença entre o primeiro e o último terço é de
2,4%, dentro do ruído que a wiki já documenta (~20% de variância por carga de CPU).

**RNF-04 passa pela primeira vez neste projeto.** A ressalva de `m10-t1` sobre "sinal de
degradação não diagnosticado" está resolvida: o sinal existia, e a causa não era a que se temia.

## Conclusão 2 — mas o regime sustentado é 20,6% mais caro, e o teto cai

O que muda não é a estabilidade — é o **nível**. T1b mediu 4,15× agregado em rajada curta; o soak
mede **3,44×** na mesma configuração:

```
fator sustentado / rajada = 0,829   →   o regime contínuo custa 20,6% a mais
```

A causa provável é de medição, não de hardware: rajadas curtas de 8 repetições aproveitam cache
quente e turbo boost que 30 minutos de trabalho contínuo não sustentam. **O número honesto para
dimensionar é o sustentado**, porque é o regime em que o produto opera.

Reaplicando o modelo de custo de T1b com o fator:

| chunk | teto (rajada) | **teto (sustentado)** | |
|---|---|---|---|
| 560 ms | 237M | **182M** | −23% |
| **1120 ms** | **376M** | **294M** | **−22%** |
| 2240 ms | 516M | 406M | −21% |

**O teto a 1120 ms é ~294M, não 376M.**

## Conclusão 3 — o Nemotron 600M reprova o RNF-01 mesmo a 1120 ms

1,72× por canal contra o alvo de 3×. A latência maior o melhorou muito (era 1,22× a 560 ms em T1),
mas não o bastante. Isso **confirma** a decisão do ADR-003: ele entra como professor, não como
produto.

## Consequência para o plano

A faixa-alvo de **250–350M** do [plano M10](../../docs/plans/m10-sota-ptbr.md) sobrevive, mas a
margem some: 294M é o teto, não o alvo. Dimensionar em **250–280M** deixa folga para o que esta
medição ainda não cobriu.

## Limitações

1. **Sem softphone (RNF-05).** A máquina rodava o soak e mais nada além do ambiente de trabalho
   normal. Carga concorrente real vai piorar o número — e é justamente ela que o pior minuto
   (2,41×) provavelmente capturou.
2. **Uma clipe repetida em laço**, não áudio variado. Cache de features e de disco favorecem o
   número; áudio sempre novo tenderia a ser mais lento.
3. **O fator 0,829 vem de comparar duas sessões diferentes**, não de um experimento pareado.
   Rajada e soak não rodaram lado a lado, e a wiki já documenta ~20% de ruído entre sessões — o
   que é da mesma ordem do efeito medido. **O fator é a melhor estimativa disponível, não uma
   separação limpa.**
4. **Um modelo só.** O fator sustentado foi medido no Nemotron de 600M e aplicado ao modelo de
   custo inteiro. Se ele depender do tamanho, os tetos das outras linhas estão errados.
