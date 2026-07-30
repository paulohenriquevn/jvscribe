#!/usr/bin/env bash
# Cadeia de augmentação telefônica 8 kHz (M1 — T2.1).
#
# Degrada um WAV para o canal de call center brasileiro (PRD.md § 4, § 7.1):
#   1. reamostra 16k→8k
#   2. filtro de banda telefônica 300-3400 Hz (onde vivem as fricativas some)
#   3. G.711 a-law round-trip (encode → decode) — a degradação do codec
#
# Tudo em `sox` (que faz a-law nativo) — nenhuma dependência torch/lhotse, que só
# cobriria o resample (blueprint Corner4/Q3, ADR do plano). Determinístico e
# reprodutível.
#
# Uso: ./scripts/telephone_augment.sh <input.wav> <output.wav>
#
# Fail-fast (error-handling.md § 2): input ausente ou sox ausente → exit não-zero
# com mensagem clara, nunca silêncio.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "uso: $0 <input.wav> <output.wav>" >&2
  exit 2
fi

INPUT="$1"
OUTPUT="$2"

if ! command -v sox >/dev/null; then
  echo "erro: sox não encontrado no PATH — a cadeia telefônica precisa de sox" >&2
  exit 3
fi

if [ ! -f "$INPUT" ]; then
  echo "erro: input '$INPUT' não existe" >&2
  exit 1
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

ALAW="$TMPDIR/alaw.wav"

# 1+2. reamostra p/ 8 kHz e aplica a banda telefônica 300-3400 Hz num passo.
#      `sinc 300-3400` é o passa-banda; `rate 8000` reamostra.
# 3.   codifica em G.711 a-law (8 kHz mono) — o formato do canal.
sox "$INPUT" -r 8000 -c 1 -e a-law "$ALAW" sinc 300-3400

# 3b. decodifica de volta para PCM 16-bit 8 kHz (round-trip do codec) — a saída
#     carrega a degradação do a-law, pronta para o ASR/medição.
sox "$ALAW" -e signed-integer -b 16 -r 8000 -c 1 "$OUTPUT"

echo "augmentação telefônica: $INPUT → $OUTPUT (8 kHz mono, banda 300-3400, a-law round-trip)"
