---
type: Medição
title: RNF-05 — carga concorrente é o critério mais restritivo, e nunca tinha sido medido
description: >-
  Softphone sozinho custa 16%. Softphone mais CRM custa 61,7% e derruba o por-canal para 0,98x —
  abaixo de 1,0, onde o backlog cresce sem limite. O teto cai de 294M para 230M.
tags: [medicao, m10, rnf05, carga, concorrencia, teto, rnf]
timestamp: 2026-09-14T21:00:00Z
---

# RNF-05 — o RTFx sob carga concorrente `[MEDIDO]`

Data: 2026-09-14 · i7-1355U · reconhecedor preso a `taskset -c 0-3`, **a carga não** (quem decide
onde ela roda é o escalonador, como na máquina real) · chunk 1120 ms, 2 canais ·
`nemotron-3.5-asr-streaming-0.6b` int8 · 6 rodadas em round-robin.

## A pergunta

O `ROADMAP.md` exige os cinco critérios de real-time medidos **"sob carga concorrente"**. Toda
medição deste projeto — M6, T1, T1b, Q-14 — rodou com a máquina praticamente ociosa. O
`wiki/medicoes/index.md` listava RNF-05 como não exercitado desde o início.

O notebook do atendente durante uma chamada não está ocioso: roda softphone (codec, jitter
buffer, eco), o CRM da operação, navegador, e o que mais a empresa instalar.

## Evidência

| cenário | agregado | **por canal** | delta | RNF-01 (≥3×/canal) |
|---|---|---|---|---|
| ocioso | 5,11× | 2,55× | — | ❌ |
| **softphone** (0,5 núcleo) | 4,29× | 2,15× | **−16,0%** | ❌ |
| **softphone + CRM** (2,5 núcleos) | 1,95× | **0,98×** | **−61,7%** | ❌ |

Separação estatística, `comparar_pareado`, n=6:

- softphone − ocioso: **−1,230×**, IC95% [−1,887; −0,828]
- softphone+CRM − ocioso: **−3,653×**, IC95% [−4,698; −3,028]

Nos dois casos o IC não cruza zero.

## Conclusão 1 — abaixo de 1,0 por canal o sistema não acompanha o tempo real

O cenário `softphone + CRM` entrega **0,98× por canal**. Abaixo de 1,0 o áudio chega mais rápido
do que é processado e **o backlog cresce sem limite** — exatamente o modo de falha que o
`docs/ARCHITECTURE.md` descreve ter medido antes do backpressure existir, quando o atraso subiu de
392 ms para 18.798 ms e ficou lá.

O backpressure do motor impede o colapso, mas ao preço declarado: descarta áudio antigo. Sob essa
carga o produto **perde transcrição**, não apenas atrasa.

## Conclusão 2 — nenhum cenário passa o RNF-01 com este modelo

Nem o ocioso. 2,55× por canal contra o alvo de 3×. Isso reforça, por uma terceira via, o que T1 e
Q-14 já haviam estabelecido: o Nemotron de 600M é professor, não produto.

## Conclusão 3 — o teto de parâmetros cai de novo

Combinando o fator sustentado de [`m10-q14`](m10-q14-soak-sustentado.md) (0,829) com o fator de
carga medido aqui:

| cenário | teto a 1120 ms |
|---|---|
| só sustentado, sem carga | 294M |
| **sustentado + softphone** | **230M** |
| sustentado + softphone + CRM | **48M** |

E o que o modelo **atual de 64M** entregaria, sob os mesmos fatores:

| cenário | por canal | |
|---|---|---|
| ocioso | 7,08× | ✅ |
| softphone | 5,95× | ✅ |
| softphone + CRM | 2,71× | ❌ |

**O modelo de 64M que o projeto já tem reprova o RNF-01 sob carga pesada.** Não por ser lento —
por não sobrar CPU.

## O que este resultado significa para o M10

A faixa-alvo do encoder cai mais uma vez. A sequência de correções desta sessão:

```
174M (T1, errado)  →  376M (T1b, rajada)  →  294M (Q-14, sustentado)  →  230M (RNF-05, com softphone)
```

**Dimensionar em 180–220M** deixa margem para o que ainda não foi medido — e a margem importa,
porque cada medição mais realista desta sessão derrubou o número.

## Limitações — e a mais importante é sobre a carga

1. **A carga é sintética.** `queimador` consome CPU em ciclos curtos para imitar codec e jitter
   buffer, mas **não é um softphone**. Não faz I/O de rede, não toca o driver de áudio, não
   compete por cache da mesma forma. O número de 16% para "softphone" é plausível; o de 61,7%
   para "softphone + CRM" **é provavelmente pessimista**, porque 2,5 núcleos a 100% é mais
   agressivo que um CRM real.
2. **O cenário realista não foi medido.** Medir com softphone de verdade em chamada real exige
   montagem que este teste não fez. O que está medido é a **forma** da degradação, não a
   magnitude no notebook do atendente.
3. **O ocioso aqui (5,11×) difere do soak (3,44×)** porque este teste faz passadas curtas com
   pausas entre cenários, e aquele roda 30 minutos contínuos. A comparação válida deste documento
   é **entre cenários**, que é pareada; o nível absoluto vem do soak.
4. **Um modelo só, um chunk só.** O fator de carga foi medido no Nemotron a 1120 ms e aplicado ao
   modelo de custo inteiro.

## O que fica em aberto

**Medir com softphone real em chamada real** continua sendo a única forma de fechar RNF-05 de
verdade. Este documento tira o critério de "nunca exercitado" e o coloca em "exercitado com carga
sintética" — que é progresso, não conclusão.
