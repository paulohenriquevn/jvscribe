---
type: Medição
title: E0 — o instrumento de confiança, e o desenho que a execução refutou
description: A margem por palavra custa +0,31% do decode. E o plano previa um invólucro que teria mudado todo WER publicado.
tags: [medicao, e0, confianca, ctc, kernel, protocolo]
timestamp: 2026-07-31T00:00:00Z
---

# E0 — o instrumento de confiança `[MEDIDO]`

Data: 2026-07-31 · `git 50fd6a9` → E0 · modelo `models/current/model.int8.onnx` · i7-1355U.
Fase E0 de [`portao-de-confianca-plan.md`](../../knowledge-base/plans/portao-de-confianca-plan.md).

## Hipótese

A margem entre o primeiro e o segundo colocado é extraível por palavra **sem custo relevante**,
porque o `argmax` já percorre o eixo do vocabulário — o segundo colocado sai da mesma passagem.

**Predição pré-registrada:** custo adicional < **2%** do tempo de decode.
**Critério de morte:** RTFx cai fora do IC95% do valor anterior.

## Evidência

### O desenho do plano foi refutado antes da primeira linha de código

O plano previa `greedy_text` virar **invólucro** de `greedy_palavras`. Uma verificação no
`tokens.txt` do artefato canônico matou o desenho:

```
token exatamente '▁' : [(7, '▁')]
```

O vocabulário tem uma peça que é **só** o marcador de início de palavra. Emitida, ela vira um
espaço solto: `detok_pieces` produz `"a  b"` (dois espaços) enquanto uma junção por palavras
produziria `"a b"`. Como invólucro, `greedy_text` mudaria de saída nesse caso — e ela tem **seis
chamadores de produção**, então a mudança alteraria todo WER publicado. É exatamente o risco R4.

**Contrato adotado no lugar, e ele é mais forte porque é verificável:**

```python
[p.texto for p in greedy_palavras(x)] == greedy_text(x).split()
```

`greedy_text` **não foi tocada**. A comparação por `.split()` é exata mesmo com espaço duplo.

### R4 fechado contra dado real, não contra fixture

| verificação | resultado |
|---|---|
| invariante sobre **300 utterances reais** de FLEURS | **0 divergências** |
| saída de `batch_transcribe` (md5) | `5329b677…` **antes e depois — idêntica** |
| suíte | **514** testes verdes (+13) |
| `ruff F,E9,B` | limpo |

### O custo

Colapso medido **isolado** da sessão ONNX — a sessão tem variância de 2× nesta máquina
(88,6 a 177,7 ms em 7 corridas) e mascararia um efeito de 0,3%. Nove blocos de 200 repetições:

| função | mediana |
|---|---|
| `greedy_text` | 0,032 ms |
| `greedy_palavras` | 0,400 ms |
| **Δ** | **+0,368 ms** |

Contra o decode completo de ~119 ms: **+0,31%**.

## Conclusão

**Predição confirmada** (+0,31% < 2%). O instrumento existe, é gratuito na prática e não alterou
uma vírgula do que o sistema transcreve. E0 passa; E1 está liberada.

## O que esta medição NÃO diz

- **A função em si é 12,5× mais cara** que `greedy_text` (0,400 contra 0,032 ms). Isso é
  irrelevante aqui porque o colapso é 0,03% do pipeline — mas deixa de ser se alguém a mover
  para um laço quente com entradas pequenas. O número que vale é o **absoluto** (+0,37 ms), não
  a razão.
- O custo foi medido sobre **uma** locução de 6,8 s. Locuções longas têm `T` maior e o
  `np.partition` escala com `T×V`; a fração deve permanecer, mas não foi medida em varredura.
- A regra de redução escolhida — margem do **primeiro** frame de uma emissão repetida — é a que
  produziu os números do protocolo. **Não foi comparada** contra "máximo sobre o span" nem contra
  a posterior da trajetória colapsada. É trabalho de E1 (Unresolved Question 1).

## Aprendizado para o loop

> **Verificar o vocabulário antes de escrever a função custou dois minutos e evitou reescrever
> todo WER publicado.**

O plano estava errado num detalhe que só o artefato conhecia. O passo 5 do loop — *revisar o
plano com o número que causou a mudança* — foi exercido na primeira fase, o que é um bom sinal
sobre o protocolo e um mau sinal sobre planejar sem olhar o dado.
