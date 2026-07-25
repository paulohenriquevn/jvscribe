# Code-Quality Audit — M3

**Data:** 2026-07-25 · **Modo:** standalone (Python) · **Slug:** m3-corpus
**Verdict:** **PASS_WITH_CAVEATS** (cap 89)

## Escopo

M3 adiciona código Python em `scripts/corpus/` (5 módulos) + 3 arquivos de teste. Não toca Rust (workspace intacto: 23 suites verdes, 0 FAILED).

## Detectores

| Detector | Resultado |
|---|---|
| D1 — dead code (vulture, min-confidence 80) | **Limpo** após fix — o único achado era `**kw` não-usado em 2 mocks de teste (assinatura precisa aceitar kwargs); renomeado para `**_kw`. Zero dead code em produção. |
| D2 — fabricação de símbolo | **Zero** — os 7 símbolos públicos (`apply_telephone_channel`, `pairwise_cer`, `agree`, `calibrate_tau`, `transcribe_pair`, `build_cutset`, `load_telephone_audio`) têm 3 callers cada (definição + teste + `run_pipeline`). Imports resolvem (torch/lhotse/scipy/audioop/jiwer verificados no ambiente). |
| D3 — wiring | Cada módulo tem caller de produção (`run_pipeline.py`) + teste + métrica (o pipeline grava `m3-cer-distribution.md`). |

## Caveats (documentados)

1. **Python é `DEFER`** em `code-quality-languages.txt` (scripts cobertos por pytest, sem manifesto). O gate hard de code-quality é o Rust (ENABLED) — intacto. A cobertura de M3 vem dos 17 testes pytest + a Integration real.
2. **`audioop` deprecado** (PEP 594) — import guardado com fail-fast + fallback `audioop-lts` documentado (`telephone_channel.py`).

## Findings reais

Nenhum. Zero dead code (vulture limpo), zero fabricação (callers + imports verificados), error-handling explícito (ValueError tipado em cada fronteira: array vazio, distribuição vazia, keep_fraction inválido, label ausente).

## Verdict

**PASS_WITH_CAVEATS** — libera `/review`. Nenhum `FAIL_HARD`/`INVALID`.
