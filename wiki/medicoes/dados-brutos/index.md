---
type: Índice
title: Dados brutos das medições
description: A evidência que sustenta os números — soak por janela e dumps de eval por utterance.
tags: [medicao, dados-brutos, evidencia]
timestamp: 2026-07-31T00:00:00Z
---

# Dados brutos

Os números dos documentos de medição saem daqui. Ficam preservados porque **conclusão sem
evidência recomputável não é evidência** — e este projeto já regenerou um WER a partir dos
`recogs-*` antes de descartar os `errs-*` correspondentes.

## Soak que decidiu o tamanho do modelo

| arquivo | condição |
|---|---|
| `small-idle.json` · `medium-idle.json` | máquina ociosa |
| `small-load.json` · `medium-load.json` | **sob carga concorrente** — a condição-alvo |

É a evidência do [ADR 0003](../../decisoes/0003-finalista-medium.md): sob carga os dois
**empatam** em RTFx (mínimos 7,1× vs 7,6×, ambos ≥ 6×); isolado o small é só 1,15× mais
rápido, não 2× como uma medição anterior sugeria. Empatado o RTFx, o desempate migra para
acurácia — e o medium ganha.

Análise em [m4-soak-small-vs-medium.md](../m4-soak-small-vs-medium.md).

## Dumps de eval por utterance

`eval-cpu-medium-phoneme*.txt` — saída do **runtime Rust** (`macaw-cli transcribe`, removido em
2026-07-30) sobre FLEURS: 300 e 919 utterances, int8 e fp32.

Sustentam [runtime-rust-int8-vs-fp32.md](../runtime-rust-int8-vs-fp32.md), que mediu int8
contra fp32 e encontrou a diferença **dentro do ruído** — o que refutou investir em quantização
mista ou QAT: não havia acurácia a recuperar.

> O nome do binário (`macaw-cli`) é histórico: era o nome anterior do produto. Reescrevê-lo
> criaria citação para um comando que nunca existiu.
