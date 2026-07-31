---
type: Artefato de modelo
title: jvscribe-ptbr-zipformer-ctc-64m
description: O modelo publicado — WER 15,99% em FLEURS pt_br, RTFx 40×, int8 em CPU.
resource: https://huggingface.co/paulohenriquevn/jvscribe
tags: [modelo, entregavel, huggingface, wer]
timestamp: 2026-07-31T00:00:00Z
---

# jvscribe-ptbr-zipformer-ctc-64m

Publicado em `paulohenriquevn/jvscribe` (HuggingFace, **privado**), 17 arquivos, 3,13 GB —
inferência, alternativos e tudo para retomar o treino.

## Números

`[MEDIDO]` 2026-07-31 — FLEURS pt_br `test[0:100]`, 2.552 palavras, greedy CTC, ONNX int8,
máquina com load average < 1.

| | valor |
|---|---|
| WER | **15,99%** |
| CER | **7,30%** |
| RTFx | **40,0×** |

RTFx é a razão entre duração do áudio e tempo de processamento. O requisito do produto é ≥ 6×
para o ASR isolado — ver [../medicoes/index.md](../medicoes/index.md).

## Como este peso foi escolhido

Dois candidatos coabitavam o artefato. Medidos no mesmo conjunto, com a mesma régua:

| peso | WER | CER |
|---|---|---|
| `model.int8.onnx` (média de 112k+124k) | **15,99%** | 7,30% |
| `alternates/ckpt124k.int8.onnx` (checkpoint único) | 17,32% | 7,39% |

Bootstrap **pareado** de 5.000 reamostragens: IC95% do delta em **[−2,25; −0,43] pp** — não
cruza zero. A vantagem do checkpoint averaging é real, não ruído.

> O `model_card.json` é a **autoridade** sobre qual arquivo é o canônico. Nome de arquivo não
> conhece WER — foi assim que o pior dos dois ficou canônico por engano. Ver
> [../motor/resolucao-de-artefato.md](../motor/resolucao-de-artefato.md).

## Reprodutibilidade

Verificado **a partir do download do HuggingFace**, não dos arquivos locais: `sha256` e
`vocab_fingerprint` conferem com o model card, a inferência entrega os mesmos 15,99% / 7,30%, e
o checkpoint publicado carrega, codifica PT-BR e aceita treino.

Ver [../medicoes/reprodutibilidade.md](../medicoes/reprodutibilidade.md).

## Limites conhecidos

- **WER em telefonia 8 kHz**: `[DESCONHECIDO]`. A literatura indica penalidade de 2–3×.
- **Fala espontânea de call center**: `[DESCONHECIDO]`. FLEURS é leitura de notícias.
- **Não é streaming**: ver [nao-e-streaming.md](nao-e-streaming.md).
- **Licença**: `other` — os termos são herdados dos corpora de treino e não foram apurados.
  Por isso o repositório é privado.
