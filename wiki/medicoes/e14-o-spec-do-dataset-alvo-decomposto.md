---
type: medicao
title: E14 — o spec do dataset alvo, decomposto fator a fator
description: >-
  Simulação fiel do canal de produção (8 kHz, 300-3400 Hz, G.711 μ-law, speech ratio, ruído de
  linha). O canal custa <1 p.p. e o codec custa ZERO; o ruído custa ~5. O elefante é espontaneidade.
tags: [medicao, dominio, telefonia, g711, ulaw, ruido, vad, e14]
timestamp: 2026-08-03T00:00:00Z
---

# E14 — o spec do dataset alvo, fator a fator

## O spec

Recebido do dono em 2026-08-03, descrevendo o dataset de produção:

| característica | valor |
|---|---|
| taxa / canais | 8000 Hz, mono |
| **speech ratio** | **18% a 63%** (logo 37–82% não é fala) |
| nível | pico normalizado ~0,95 · **RMS baixo 0,03–0,09** |
| banda | 300–3400 Hz |
| codec | **G.711 μ-law**, quantização de 8 bits |
| SNR | variável — ruído de linha, eco potencial |
| fala | **espontânea** — prosódia irregular, hesitação, interrupção |

## Método

Ablação **cumulativa** sobre o mesmo áudio do FLEURS, reusando o kernel (`audio.channel.apply_band`
para 8 kHz + banda, `audio.codecs.apply_codec(…, "g711u")` para o μ-law) e adicionando o que
faltava: perfil de ganho, razão de fala e ruído de linha.

## Evidência

`[MEDIDO]` FLEURS n=20, greedy, régua estrita:

| condição | WER | Δ | inserções |
|---|---|---|---|
| 0. original 16 kHz | 15,16% | — | 15 |
| 1. + 8 kHz, banda 300–3400 Hz | 15,70% | +0,54 | 16 |
| 2. **+ G.711 μ-law 8 bits** | 15,70% | **+0,00** | 17 |
| 3. + pico 0,95 / RMS 0,06 | 16,06% | +0,36 | 18 |
| 4. + speech ratio 40% | 16,61% | +0,55 | 17 |

E o fator isolado, com o desenho fatorial (n=16, canal completo em todas as condições):

| condição | WER | subs | del | ins |
|---|---|---|---|---|
| nem silêncio nem ruído | 15,05% | 49 | 6 | 10 |
| **só silêncio (fala = 40%)** | **14,12%** | 45 | 6 | 10 |
| só ruído (SNR 20 dB) | 19,91% | 65 | 7 | 14 |
| **os dois — o spec** | **18,98%** | 62 | 7 | 13 |

Curva de SNR, com o ruído passando pelo mesmo canal de 300–3400 Hz:

| SNR | WER |
|---|---|
| sem ruído | 15,05% |
| 30 dB | 15,74% |
| 25 dB | 17,82% |
| 20 dB | 18,29% |
| 15 dB | 22,45% |

## Conclusão

### O codec custa ZERO, e isso contraria a intuição

**G.711 μ-law 8 bits: 15,70% → 15,70%.** A companding logarítmica é **transparente** para o
modelo. Quem orça "o custo do codec" está orçando nada — o custo é da **banda**, que vem junto mas
é outro fator, e vale +0,54 p.p.

### O silêncio AJUDA, não atrapalha

A hipótese que eu levantei — CTC alucina em silêncio longo, e o `speech ratio` de 18–63% seria
perigoso — **está refutada**. Com 60% de silêncio o WER **cai** de 15,05% para 14,12%, e as
inserções ficam em 10, iguais. O CTC trata silêncio nativamente (é o que o blank faz), e o *padding*
ainda dá quadros de acomodação nas bordas.

### O ruído domina o canal, e é o único que dói

+4,86 p.p. a 20 dB, e a curva acelera abaixo de 25 dB. É o único fator do spec que custa caro.

### Somando o que o spec descreve

| fator | custo `[MEDIDO]` |
|---|---|
| 8 kHz + banda 300–3400 | +0,54 |
| G.711 μ-law | **0,00** |
| perfil de ganho (pico 0,95 / RMS baixo) | +0,36 |
| speech ratio 40% | **−0,93** (ajuda) |
| ruído de linha 20 dB | +4,86 |
| **fala espontânea** | **não simulável** |

**O canal inteiro — 8 kHz, banda, codec, ganho, silêncio — custa menos de 1 p.p. somado.** Todo o
resto do gap de produção é **ruído** e, sobretudo, **espontaneidade**, que augmentação não simula
(E11).

`[ESTIMATIVA]` projetando sobre a régua estrita (12,75% em FLEURS): fala **lida** através deste
canal com ruído fica em ~**18%**; fala **espontânea** através dele, usando o NURC-SP como âncora do
fator de espontaneidade, fica em **30–40%**. O critério de ship é **≤25%** — a conta não fecha pela
espontaneidade, não pelo canal.

## Dois defeitos do meu próprio simulador, encontrados e corrigidos

Registro porque quem repetir vai tropeçar neles:

1. **O ruído era somado DEPOIS do filtro de banda.** O hum de 60 Hz fica *abaixo* dos 300 Hz e numa
   linha real seria filtrado; no meu simulador ele passava intacto. Corrigido: o ruído entra
   **antes** da banda. Custo do defeito: 19,68% contra 18,29% reais a 20 dB.
2. **A primeira corrida atribuiu +18,77 p.p. ao ruído.** Era o defeito acima **mais** interação com
   a normalização de ganho. Medido limpo, o ruído custa **+4,86**. Um fator de quase 4× —
   se eu tivesse publicado o primeiro número, a conclusão do projeto seria outra.

## Limitações

- **n=16–20, uma corrida.** Serve para separar fatores de ordem 1 p.p. de fatores de ordem 5 p.p.;
  não serve para afirmar magnitude fina.
- **O eco não foi simulado.** O spec menciona "eco potencial" e o projeto já tem AEC integrado
  (LocalVQE), mas o custo do eco neste canal é `[DESCONHECIDO]`.
- **O ruído é sintético** — hum de 60 Hz + branco. Ruído de linha real tem tons de sinalização,
  crosstalk e picos impulsivos que isto não reproduz.
- **A projeção para fala espontânea é `[ESTIMATIVA]`** que compõe dois fatores medidos em corpora
  diferentes. Composição de ganhos não é aditiva — vale como ordem de grandeza, não como previsão.
