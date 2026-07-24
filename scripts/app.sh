#!/usr/bin/env bash
# App de teste do Macaw Voice — sobe o servidor e abre o navegador.
# Uso: ./scripts/app.sh [porta]
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-7070}"

echo "Compilando… (primeira vez pode demorar)"
cargo build -q -p macaw-cli

URL="http://127.0.0.1:$PORT"
# Abre o navegador ~2s depois de subir o servidor.
( sleep 2
  if command -v xdg-open >/dev/null; then xdg-open "$URL"
  elif command -v open   >/dev/null; then open "$URL"
  else echo "Abra manualmente: $URL"; fi
) &

exec cargo run -q -p macaw-cli -- serve "$PORT"
