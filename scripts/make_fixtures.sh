#!/usr/bin/env bash
# Gera as fixtures de áudio determinísticas usadas pelos testes.
# Determinístico por construção: sox sintetiza a partir de parâmetros, sem RNG.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p tests/fixtures
sox -n -r 16000 -c 1 -b 16 tests/fixtures/tone_440hz_16k.wav synth 3 sine 440 vol 0.5
echo "gerado: tests/fixtures/tone_440hz_16k.wav ($(soxi -s tests/fixtures/tone_440hz_16k.wav) amostras)"
