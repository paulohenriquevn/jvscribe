---
type: Índice
title: Decisões de arquitetura
description: ADRs — o que foi travado, com racional e alternativas descartadas.
tags: [adr, decisoes, arquitetura]
timestamp: 2026-07-31T00:00:00Z
---

# Decisões de arquitetura

A arquitetura deste projeto é **output de ciclo medido**, não de documento. Cada ADR registra o
que foi travado, a evidência que o sustentou e o que ficou a-medir.

| ADR | decisão | estado |
|---|---|---|
| [0001](0001-finalistas-de-arquitetura.md) | Finalistas que sobreviveram aos 8 critérios (M2) | aceito |
| [0002](0002-zipformer-ctc-small.md) | Zipformer-CTC `small` como finalista (M4) | **superseded** no eixo tamanho pelo 0003 |
| [0003](0003-finalista-medium.md) | O finalista é o `medium` (64M) | aceito — é o modelo em produção |
| [0004](0004-remocao-do-runtime-rust.md) | Remoção do runtime Rust | aceito |

## O que o 0003 decidiu, e como

Head-to-head com parâmetros equivalentes, mesmo corpus e mesmo test set: **Zipformer domina
Conformer nos dois eixos de acurácia** (WER 28,86% vs 31,57%, IC95% do delta excluindo zero).

O **tamanho** foi decidido por soak e carga: sob carga concorrente, `small` e `medium` **empatam**
em RTFx (mínimos 7,1× vs 7,6×, ambos ≥ 6×). Isolado, o `small` é só 1,15× mais rápido — não 2×,
como uma medição anterior sugeria.

Empatado o RTFx, o desempate migra para acurácia → **o `medium` ganha**.

## Um ADR que vale reler antes de reabrir a questão

O **0004** registra que a remoção do Rust **não foi por performance**: a comparação justa
mostrou Python 6,7× e Rust 6,9× — indistinguíveis. A decisão foi por foco de time. Se alguém no
futuro reabrir achando que o Rust era lento, o dado diz o contrário.
