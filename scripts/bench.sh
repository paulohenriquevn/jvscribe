#!/usr/bin/env bash
# Harness de medição de M1 sob os RNFs completos (PRD.md § 6).
#
# Prende o ASR aos P-cores com `taskset` (RNF-06 ≤ 2 P-cores) e, opcionalmente,
# gera carga concorrente nos E-cores (RNF-05) — já que `stress-ng` não está no
# ambiente, a carga são processos `openssl speed` presos aos demais cores
# (ADR D4 do plano m1-measurement-harness).
#
# Uso:
#   ./scripts/bench.sh [iterações] [--load]
#     iterações : nº de forward passes (default 30)
#     --load    : liga o gerador de carga concorrente nos E-cores
#
# Descoberta de P-cores: nos i7 híbridos (12ª+ gen) os P-cores são os primeiros
# lógicos. Sem introspecção confiável no sandbox, usamos os cores 0-1 como P-core
# proxy; ajuste PCORES no seu hardware real (Q-01 — piso da frota é DESCONHECIDO).
set -euo pipefail
cd "$(dirname "$0")/.."

ITERS="${1:-30}"
LOAD=0
[ "${2:-}" = "--load" ] && LOAD=1

PCORES="${PCORES:-0-1}"      # P-cores para o ASR (RNF-06 ≤ 2)
NCPU="$(nproc)"

echo "bench.sh — P-cores=$PCORES, iterações=$ITERS, carga concorrente=$LOAD"

if ! command -v taskset >/dev/null; then
  echo "AVISO: taskset ausente — rodando sem fixação de core (RNF-06 não isolado)"
  TASKSET=(env)
else
  TASKSET=(taskset -c "$PCORES")
fi

LOAD_PIDS=()
cleanup() {
  for pid in "${LOAD_PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

if [ "$LOAD" = "1" ]; then
  if command -v openssl >/dev/null && [ "$NCPU" -gt 2 ]; then
    echo "gerando carga concorrente nos E-cores (2..$((NCPU-1)))…"
    for core in $(seq 2 $((NCPU-1))); do
      taskset -c "$core" bash -c 'while true; do openssl speed -seconds 1 sha256 >/dev/null 2>&1; done' &
      LOAD_PIDS+=($!)
    done
  else
    echo "AVISO: openssl ausente ou poucos cores — sem carga concorrente (RNF-05 não exercido)"
  fi
fi

echo "compilando (release para medição realista)…"
cargo build -q --release -p macaw-cli

# O `.cargo/config.toml [env]` só se aplica sob `cargo run`; ao invocar o binário
# direto (via taskset) precisamos exportar o ORT_DYLIB_PATH nós mesmos, senão o
# `ort` não acha a lib e trava no load. Caminho a partir da raiz do repo.
export ORT_DYLIB_PATH="$(pwd)/vendor/onnxruntime-linux-x64-1.23.0/lib/libonnxruntime.so"

echo "rodando o harness preso aos P-cores…"
"${TASKSET[@]}" ./target/release/macaw-cli bench "$ITERS"
