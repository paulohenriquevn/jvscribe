---
type: Índice
title: O modelo
description: Zipformer-CTC de 64M parâmetros, int8, PT-BR. Arquitetura, vocabulário e os limites conhecidos.
tags: [modelo, zipformer, ctc, int8]
timestamp: 2026-07-31T00:00:00Z
---

# O modelo

**`jvscribe-ptbr-zipformer-ctc-64m`** — Zipformer-CTC, 64,29M parâmetros, quantizado int8,
com cabeça de fonema auxiliar que sai do grafo de inferência.

| conceito | o que responde |
|---|---|
| [entregavel.md](entregavel.md) | O que está publicado, com que números e sob que condição |
| [arquitetura.md](arquitetura.md) | Grafo, stacks, subamostragem, onde o custo mora |
| [vocabulario.md](vocabulario.md) | 500 tokens BPE — e por que a contagem não identifica o vocabulário |
| [nao-e-streaming.md](nao-e-streaming.md) | O fato que mais restringe o produto hoje |
| [cabeca-de-fonema.md](cabeca-de-fonema.md) | A supervisão auxiliar que só existe no treino |
