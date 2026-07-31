---
type: Medição
title: E4 — o custo do beam não é o obstáculo que se supunha
description: Beam 8 custa 15 ms contra 134 ms de encoder. RTFx 45,8× no lote — mas o tempo real não foi medido, e é lá que o RNF-01 vive.
tags: [medicao, e4, beam, decoding, rnf, custo, protocolo]
timestamp: 2026-07-31T00:00:00Z
---

# E4 — o custo do beam `[MEDIDO]`

Data: 2026-07-31 · `git 38687d2` → E4 · FLEURS, 1 locução de 6,8 s · i7-1355U.
Fase E4 de [`portao-de-confianca-plan.md`](../../knowledge-base/plans/portao-de-confianca-plan.md).

## Hipótese

O beam search é a única alavanca que ataca `real_word_hyp` — **36,6% do erro**, o maior bloco, e
o único que nenhuma outra fase toca. A pergunta que vem primeiro **não** é quanto ele rende, e sim
se ele **cabe**: se estourar o RNF-07, o ganho é irrelevante.

**Critério de morte:** nenhum beam ≥ 2 mantém RTFx ≥ 6× → registrar o custo e parar.

## Evidência

Locução de 6,8 s · 169 frames · vocabulário 500 · encoder **134 ms**.

| decode | ms do decode | ms total | RTFx | cabe (≥6×)? |
|---|---|---|---|---|
| greedy | 0,05 | 134,3 | **50,95×** | ✅ |
| beam 2 | 4,29 | 138,5 | 49,39× | ✅ |
| beam 4 | 8,08 | 142,3 | 48,07× | ✅ |
| beam 8 | 15,23 | 149,4 | **45,77×** | ✅ |

**Nenhum critério de morte disparou.** Beam 8 custa **+11%** de tempo de parede sobre o greedy, e
o RTFx cai de 51× para 46× — a 7,6× do limiar.

### Por que o custo é tão pequeno

O **encoder domina**: 134 ms contra 0,05 ms de colapso greedy. É consistente com o profile já
publicado — `ctc_output` é **0,3%** do custo do modelo. Buscar sobre a saída de uma cabeça que
custa quase nada continua custando quase nada, mesmo multiplicando o trabalho por 8.

O beam usa poda de 12 candidatos por frame; sem ela o custo seria `T × largura × 500` e o que se
mediria seria o laço em Python, não o algoritmo.

## Conclusão — e apenas isto

**O argumento de custo contra o beam search está morto no caminho de lote.** Ele era a objeção
principal a explorar a alavanca dos 36,6%, e não se sustenta: 15 ms sobre 134 ms.

## O que esta medição NÃO diz — e o caveat é grande

⚠️ **Isto é benchmark de componente no caminho de LOTE. O RNF-01 vive no tempo real.**
`.claude/rules/asr-evidence-discipline.md` § 4: *benchmark de componente não transfere para o
sistema* — e este projeto já pagou por isso com a afinidade de CPU (25% melhor isolada, 46% pior
no pipeline).

No tempo real o desenho é outro: janela deslizante reprocessa 6 s a cada hop de 0,5 s, **121 ms
por hop** contra 11 ms de processar só o novo — 10,6× de retrabalho medido. Somar 15 ms de beam 8
a cada hop dá **+12%** ali também, mas a base é diferente: o RTFx ao vivo medido foi de **2,5× a
4,6×**, contra um RNF-01 de ≥ 3× para o pipeline de dois canais. **Doze por cento em cima de 3,0×
derruba abaixo do limiar.**

Então: **cabe no lote, `[DESCONHECIDO]` no tempo real.** Medir no tempo real exige
`bench/stress_test.py` com o beam ligado, numa máquina ociosa — e esta não fica ociosa.

- **Este beam não tem modelo de linguagem.** Em CTC puro, beam sem LM rende quase nada: a
  independência condicional entre frames faz a busca reencontrar o caminho greedy. O beam aqui
  existe para medir **custo**, que é o portão. O ganho depende do LM, e nenhum está instalado
  (`pyctcdecode`, `kenlm`, `torchaudio` — todos ausentes).
- Medir custo sem LM é teste **de um lado só**, e válido: o LM só encarece. Se o beam nu já não
  coubesse, com LM caberia menos.
- **Uma locução, três repetições, máquina com load average de 21 nos últimos 5 min.** O número do
  encoder (134 ms) reflete isso. As razões entre decodes são mais robustas que os absolutos.
- Sem varredura de poda: 12 candidatos por frame foi escolhido, não medido.

## Próximo passo, e ele tem pré-condição

O ganho de E4 exige um LM de PT-BR, que exige dependência nova — logo, `/deps-audit` próprio,
como o plano já previa. E exige **medir o custo no tempo real** antes, porque é lá que o
requisito morde.
