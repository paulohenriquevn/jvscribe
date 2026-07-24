#!/usr/bin/env bash
# Baixa o modelo emprestado de M0 (alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx).
# O modelo é grande (encoder 40MB de grafo + 2.3GB de pesos externos) e NÃO é
# versionado — é artefato de terceiro, apenas encanamento (ADR D4 do blueprint).
set -euo pipefail
cd "$(dirname "$0")/.."
DIR=models/m0-borrowed
REPO=alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx
mkdir -p "$DIR"
for f in config.json vocab.txt nemo128.onnx encoder-model.onnx decoder_joint-model.onnx; do
  [ -f "$DIR/$f" ] || curl -sL -o "$DIR/$f" "https://huggingface.co/$REPO/resolve/main/$f"
done
# pesos externos do encoder (2.3GB) — hf CLI faz resume robusto de LFS
if [ ! -f "$DIR/encoder-model.onnx.data" ]; then
  hf download "$REPO" encoder-model.onnx.data --local-dir "$DIR"
fi
echo "modelo emprestado pronto em $DIR"
