---
type: medicao
title: E15 — o viés de blank tem sinal OPOSTO em áudio fácil e difícil
description: >-
  No FLEURS, β=0 é ótimo e viés positivo piora. No NURC-SP de baixa qualidade, β≈+0,7 vale −2,3 p.p.
  A calibração de emissão do modelo é dependente do domínio — um valor global seria errado.
tags: [medicao, blank, decoding, dominio, nurc, ctc, e15]
timestamp: 2026-08-03T00:00:00Z
---

# E15 — o viés de blank é dependente do domínio, e o sinal inverte

## A pergunta

"Dá para melhorar os 49–54% do áudio difícil?" Tudo que este projeto mediu até aqui foi em áudio
**fácil** (FLEURS lido, banda larga). A pergunta se as alavancas **transferem** estava aberta.

## O diagnóstico que apontou o caminho

Primeiro, o beam + LM: `[MEDIDO]` NURC-SP `quality=low`, n=60, régua estrita:

| decoder | WER | subs | del | ins |
|---|---|---|---|---|
| greedy | 54,02% | 234 | **116** | 102 |
| beam + LM (α=0,1 β=1,0) | 53,29% | 232 | 109 | 104 |

O beam+LM **transfere** (+0,73 p.p.), mas o perfil de erro é que informa: **deleção é 26% do erro
aqui contra 12,9% no FLEURS**, e inserção é 23%. Os dois extremos da emissão estão elevados — o
modelo erra tanto por engolir quanto por inventar.

## O resultado, e ele inverte o sinal

`[MEDIDO]` mesmo conjunto, viés somado ao logit de blank antes do argmax, posteriores cacheadas
(o viés é aritmética sobre elas, então a comparação é pareada por construção):

| viés | WER | Δ | subs | del | ins |
|---|---|---|---|---|---|
| −1,5 | 60,61% | +6,59 | 267 | 70 | 172 |
| −1,0 | 56,95% | +2,93 | 254 | 84 | 143 |
| −0,5 | 55,12% | +1,10 | 241 | 104 | 120 |
| **0,0** | **54,02%** | — | 234 | 116 | 102 |
| +0,3 | 52,32% | −1,71 | 227 | 124 | 86 |
| +0,5 | 51,83% | −2,20 | 229 | 126 | 75 |
| **+0,7** | **51,71%** | **−2,32** | 230 | 131 | 67 |
| +1,0 | 51,95% | −2,07 | 223 | 147 | 60 |
| +1,6 | 51,59% | −2,44 | 213 | 173 | 38 |
| +2,0 | 51,71% | −2,32 | 200 | 193 | 32 |

**Ganho de ~2,3 p.p. — 4,3% relativo — sem tocar em peso, dado ou arquitetura, a custo O(1).**

E o mecanismo é visível: as inserções despencam de 102 para 38 enquanto as deleções sobem de 116
para 173. O saldo é favorável até ~+1,6 e depois achata.

## O que torna isto interessante: o sinal inverte

`[MEDIDO]` E8b, no FLEURS (validação, n=200):

| viés | WER |
|---|---|
| **0,0** | **13,47%** ← ótimo |
| +0,5 | 13,58% |
| +1,0 | 13,97% |
| +2,0 | 15,08% |

**No áudio fácil, β=0 é o ótimo e viés positivo piora. No difícil, β≈+0,7 vale −2,3 p.p.**

A calibração de emissão do modelo **não é uma propriedade fixa** — depende da condição acústica.
Sob degradação, o modelo se torna *hesitante e ruidoso ao mesmo tempo*: erra por inventar tokens em
trechos que não sustentam fonema, e suprimir emissão remove mais lixo do que fala.

## Consequência prática

Um valor **global** de β seria errado nos dois sentidos: β=0 desperdiça 2,3 p.p. no domínio do
produto; β=+0,7 custaria ~0,2–0,5 p.p. no áudio limpo.

Para um produto de **call center** — onde *todo* o áudio é degradado e espontâneo — a troca é
claramente favorável, e β>0 deveria ser o default do caminho telefônico.

## Limitações

- **n=60, uma corrida, split de validação do NURC-SP.** Varrer aqui é legítimo (é validação), mas
  **o número precisa de confirmação num held-out** antes de virar default. O `nurc-sp-prosodic-segmentation`
  tem split de `test` com 789 utterances e licença MIT — é o candidato.
- **A curva é ACHATADA** entre +0,5 e +2,0 (51,59 a 51,95%). Escolher o argmin seria sobreajustar a
  ruído; qualquer ponto na região plana é defensável, e **+0,7** é escolhido por ficar no meio dela.
- **Não medido em conjunto com beam + LM.** As duas alavancas mexem na mesma decisão de emissão;
  a composição é `[DESCONHECIDO]` e não deve ser somada (regra do E6).
- **NURC-SP é degradação analógica dos anos 1970**, não codec telefônico. Que o ótimo de β seja o
  mesmo em 8 kHz G.711 é hipótese, não medição.
