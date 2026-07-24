#!/usr/bin/env bash
# Roda a suíte e reporta quantos testes EXECUTARAM de fato vs. fizeram SKIP por
# falta de ambiente (modelo/servidor de áudio ausente). Alguns testes de
# integração degradam graciosamente com `eprintln!("SKIP: ...")` + return quando
# o ambiente não tem o necessário — sem este relatório, eles contam como "ok"
# sem verificar nada (review M4). Um clone limpo sem scripts/setup_*.sh rodado
# verá vários SKIPs; este relatório os torna visíveis.
set -uo pipefail
cd "$(dirname "$0")/.."
out=$(cargo test --workspace -- --nocapture 2>&1)
passed=$(echo "$out" | grep -oE '[0-9]+ passed' | awk '{s+=$1} END {print s}')
skips=$(echo "$out" | grep -c 'SKIP:')
echo "-------- relatório de execução da suíte --------"
echo "testes 'ok'    : ${passed:-0}"
echo "SKIPs efetivos : ${skips:-0}"
if [ "${skips:-0}" -gt 0 ]; then
  echo "motivos de SKIP:"
  echo "$out" | grep 'SKIP:' | sed 's/^/  /' | sort -u
fi
echo "------------------------------------------------"
