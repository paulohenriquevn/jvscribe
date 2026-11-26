---
type: Pipeline
title: Lote — uma pasta de áudios
description: ffmpeg, VAD de energia, batch por comprimento similar, CTC greedy. Sem GPU.
resource: jvscribe/batch/batch_transcribe.py
tags: [lote, batch, vad, ffmpeg]
timestamp: 2026-07-31T00:00:00Z
---

# Pipeline de lote

```
pasta de áudios
   ▼  ffmpeg (mp3/m4a/aac/flac/ogg/opus/mp4/webm → f32le 16 kHz mono)
segmentação por VAD de energia
   │  RMS por janela de 30 ms; corta em silêncios ≥ 350 ms
   │  teto de 28 s: fala contínua é cortada no frame de menor energia
   ▼
fbank por segmento (paralelo — a etapa é I/O-bound)
   ▼  ordenação por COMPRIMENTO → batches de duração similar
ONNX Runtime em batch → CTC greedy → remonta na ordem original
   ▼
.txt por arquivo + transcripts.json (com RTFx agregado)
```

## Por que ordenar por comprimento

Agrupar segmentos de duração parecida evita preencher a matriz de padding majoritariamente com
zeros. É o que torna o batch barato.

```bash
python3 jvscribe/batch/batch_transcribe.py --input-dir ./audios --out-dir ./saida
```

O modelo e o vocabulário são resolvidos pelo
[resolucao-de-artefato.md](resolucao-de-artefato.md) — não passe caminho à mão sem motivo.
