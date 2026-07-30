#!/usr/bin/env bash
# Roda a suíte e reporta quantos testes EXECUTARAM de fato vs. fizeram SKIP por
# falta de ambiente (modelo/servidor de áudio ausente). Alguns testes de
# integração degradam graciosamente com `eprintln!("SKIP: ...")` + return quando
# o ambiente não tem o necessário — sem este relatório, eles contam como "ok"
# sem verificar nada (review M4). Um clone limpo sem scripts/setup_*.sh rodado
# verá vários SKIPs; este relatório os torna visíveis.
#
# M9/T2.3 — duas correções, motivadas por defeito observado em 2026-07-30:
#
#   1. FALHA DE BUILD ERA ENGOLIDA. Com o build quebrado (toolchain incompatível com `ort`),
#      este script imprimiu "testes 'ok': 0 / SKIPs: 0" e saiu 0 — um relatório tranquilizador
#      sobre uma suíte que nunca rodou. A ferramenta feita para impedir falso verde produzia
#      o falso verde mais puro possível. `set -uo pipefail` sem `-e` não captura o `$?` de uma
#      substituição de comando.
#   2. ZERO TESTES NUNCA É SUCESSO. Ou o build não produziu alvo, ou o filtro mudou. Nos dois
#      casos o relatório não pode sair verde.
set -uo pipefail
cd "$(dirname "$0")/.."

out=$(cargo test --workspace -- --nocapture 2>&1)
rc=$?

if [ "$rc" -ne 0 ]; then
  echo "-------- relatório de execução da suíte --------"
  echo "ERRO: a suíte não completou (cargo test saiu $rc)."
  echo "Este relatório NÃO é evidência de nada — o build ou os testes falharam."
  echo "Últimas 20 linhas da saída do cargo:"
  echo "$out" | tail -20 | sed 's/^/  /'
  echo "------------------------------------------------"
  exit "$rc"
fi

passed=$(echo "$out" | grep -oE '[0-9]+ passed' | awk '{s+=$1} END {print s+0}')
skips=$(echo "$out" | grep -c 'SKIP:')

echo "-------- relatório de execução da suíte --------"
echo "testes 'ok'    : ${passed:-0}"
echo "SKIPs efetivos : ${skips:-0}"
if [ "${skips:-0}" -gt 0 ]; then
  echo "motivos de SKIP:"
  echo "$out" | grep 'SKIP:' | sed 's/^/  /' | sort -u
fi
echo "------------------------------------------------"

# Zero testes executados nunca é um resultado verde.
if [ "${passed:-0}" -eq 0 ]; then
  echo "ERRO: nenhum teste executou. Zero testes nunca é sucesso." >&2
  exit 1
fi
