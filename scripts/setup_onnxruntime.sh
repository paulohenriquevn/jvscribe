#!/usr/bin/env bash
# Baixa o ONNX Runtime 1.23 (build manylinux, compatível com glibc 2.17+).
# O binário que `ort` baixaria por padrão exige glibc >= 2.38 (usa
# __isoc23_strtoll); este runtime é carregado via load-dynamic (ORT_DYLIB_PATH
# em .cargo/config.toml). api-23 no Cargo.toml casa com esta versão.
set -euo pipefail
cd "$(dirname "$0")/.."
VER=1.23.0
[ -d "vendor/onnxruntime-linux-x64-$VER" ] && { echo "já presente"; exit 0; }
mkdir -p vendor
curl -sL "https://github.com/microsoft/onnxruntime/releases/download/v${VER}/onnxruntime-linux-x64-${VER}.tgz" -o /tmp/ort.tgz
tar xzf /tmp/ort.tgz -C vendor/ && rm -f /tmp/ort.tgz
echo "ONNX Runtime $VER em vendor/"
