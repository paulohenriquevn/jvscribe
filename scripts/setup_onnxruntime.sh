#!/usr/bin/env bash
# Baixa o ONNX Runtime 1.23 (build manylinux, compatível com glibc 2.17+).
# O binário que `ort` baixaria por padrão exige glibc >= 2.38 (usa
# __isoc23_strtoll); este runtime é carregado via load-dynamic (ORT_DYLIB_PATH
# em .cargo/config.toml). api-23 no Cargo.toml casa com esta versão.
#
# INTEGRIDADE (M9/T2.2): o tarball é verificado por SHA-256 ANTES de ser extraído.
# `[MEDIDO]` em M6: uma libonnxruntime errada deixou a inferência até 40× mais lenta e
# custou uma investigação inteira — um tarball corrompido, truncado ou substituído passaria
# silenciosamente sem esta checagem. O peer sherpa-onnx usa `URL_HASH` obrigatório mesmo com
# URL de tag imutável (`cmake/googletest.cmake:37`).
#
# O hash em scripts/onnxruntime-1.23.0.sha256 foi medido em 2026-07-30 e validado por
# equivalência: o libonnxruntime.so extraído dele é byte-idêntico ao que já estava em uso
# (sha256 98b0253652d36c706cd9b873f3e8dc74e107c26cf9694672fb4d88da1c00f250).
set -euo pipefail
cd "$(dirname "$0")/.."
VER=1.23.0
TARBALL="onnxruntime-linux-x64-${VER}.tgz"
SUMFILE="scripts/onnxruntime-${VER}.sha256"

[ -d "vendor/onnxruntime-linux-x64-$VER" ] && { echo "já presente"; exit 0; }

[ -f "$SUMFILE" ] || { echo "erro: checksum de referência ausente ($SUMFILE)" >&2; exit 1; }

mkdir -p vendor
TMPDIR_ORT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ORT"' EXIT

echo "baixando ONNX Runtime $VER…"
curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${VER}/${TARBALL}" \
  -o "$TMPDIR_ORT/$TARBALL"

echo "verificando integridade…"
if ! (cd "$TMPDIR_ORT" && sha256sum -c "$OLDPWD/$SUMFILE" --quiet); then
  echo "ERRO: checksum do $TARBALL não confere." >&2
  echo "  esperado: $(cut -d' ' -f1 "$SUMFILE")" >&2
  echo "  obtido  : $(sha256sum "$TMPDIR_ORT/$TARBALL" | cut -d' ' -f1)" >&2
  echo "Abortado ANTES de extrair — uma lib adulterada degrada a inferência em até 40×." >&2
  exit 1
fi

tar xzf "$TMPDIR_ORT/$TARBALL" -C vendor/
echo "ONNX Runtime $VER em vendor/ (checksum verificado)"
