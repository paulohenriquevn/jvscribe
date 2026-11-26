---
type: Contrato de artefato
title: Vocabulário — 500 tokens BPE, e por que a contagem não identifica
description: Dois artefatos com 500 tokens cada têm 492 ids divergentes. Validar por fingerprint, nunca por cardinalidade.
tags: [vocabulario, bpe, tokens, m9, contrato]
timestamp: 2026-07-31T00:00:00Z
---

# Vocabulário

| | |
|---|---|
| linhas em `tokens.txt` | 503 |
| dimensão de saída do modelo | **500** |
| diferença | `#0`, `#1`, `#2` — símbolos de desambiguação do lexicon FST, **não emitíveis** |
| id 0 | `<blk>` — o blank do CTC |
| ids 1, 2 | `<sos/eos>`, `<unk>` |
| demais | peças BPE (SentencePiece), com `▁` marcando início de palavra |

## O par (modelo, vocabulário) não é intercambiável

Dois artefatos deste projeto têm **500 tokens emitíveis cada** e **492 dos 500 ids mapeiam para
tokens diferentes** — o id 4 é `▁a` num e `r` no outro.

Trocar o `tokens.txt` produz texto **plausível e errado**, sem erro nenhum: nada falha, a
transcrição só fica incorreta.

## Como validar corretamente

Pelo `vocab_fingerprint` do `model_card.json` — SHA-256 sobre os pares `(id, token)` ordenados
dos tokens emitíveis. **Nunca** pela contagem: cardinalidade não distingue os dois artefatos.

```
vocab_real_len   : 500
vocab_fingerprint: 9fcb45e4e5174aa73983215a30701a6c3bf13b2380065a803593cd00e5112e92
```

Este é o achado que motivou o milestone M9 — ver [../decisoes/index.md](../decisoes/index.md).
