---
type: Contrato
title: Resolução do artefato — o model card é a autoridade
description: Um resolvedor para todos os entrypoints. Escolher peso por nome de arquivo já entregou o modelo pior em silêncio.
resource: jvscribe/common/artifact.py
tags: [artefato, model-card, contrato, m9]
timestamp: 2026-07-31T00:00:00Z
---

# Resolução do artefato

```
MACAW_MODEL_DIR  >  models/current  >  diretório de trabalho
        ▼  em cada candidato, nesta ordem:
   model_card.json → campo "model_file"        ← AUTORIDADE
   senão, nomes conhecidos (model.int8.onnx, …)  ← degradação
```

## Por que existe

Dois pesos M5 coabitavam o diretório canônico, com WER **15,99%** e **17,32%**. A ordem
alfabética de nomes selecionava o segundo. Nada falhava — a transcrição só ficava
mensuravelmente pior.

Nome de arquivo não conhece WER.

## Um resolvedor, não um por script

`jvscribe/common/artifact.py` é o **único**; `batch_transcribe`, `mic_transcribe`,
`live_transcribe` e os testes o consomem. Defaults duplicados divergem: quando o artefato foi
renomeado, o lote continuou funcionando (lia o card) e o tempo real quebrou (tinha o nome fixo
no código). Um teste exige que todos os entrypoints resolvam o **mesmo** artefato.

## O card

```json
{
  "model_file": "model.int8.onnx",
  "model_sha256": "1ac8bc5d…",
  "tokens_file": "tokens.txt",
  "vocab_real_len": 500,
  "vocab_fingerprint": "9fcb45e4…",
  "wer_measured": 15.99,
  "wer_source": "FLEURS pt_br test[0:100], greedy CTC, load<2; IC95 do delta [-2.25,-0.43] pp"
}
```

O `wer_source` carrega a **condição** da medição. Número sem condição não é comparável com
nada — ver [../disciplina/index.md](../disciplina/index.md).
