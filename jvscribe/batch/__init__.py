"""Transcrição offline — uma pasta de áudio entra, texto e WER saem.

O que une: todos processam um **conjunto fechado** de áudio, sem restrição de latência. Podem
ordenar por comprimento, agrupar em batch e usar toda a CPU — o oposto do `realtime/`, que
paga latência para responder no ritmo da fala.

| arquivo | uso |
|---|---|
| `batch_transcribe` | transcreve uma pasta (o caminho de produção offline) |
| `decode_onnx_local` | decode sobre um manifest lhotse, medindo WER/CER |
| `eval_public_hf` | WER num dataset público do HuggingFace |
"""
