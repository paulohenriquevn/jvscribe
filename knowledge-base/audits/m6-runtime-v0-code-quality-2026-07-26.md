# Code-Quality Audit — m6-runtime-v0

**Data:** 2026-07-26 · **Cycle:** CODE-QUALITY (entre `/implement` e `/review`) · **Escopo:** runtime v0 do M6 (decoder CTC em Rust) + workspace `crates/`

## Veredito

| Campo | Valor |
|---|---|
| **verdict** | **PASS** |
| score_cap | 100 |
| hard_caps_triggered | `[]` |
| soft_caps_triggered | `[]` |
| findings_by_detector | `{}` (zero achados) |
| languages_audited | rust |

Evidência-máquina: `run_code_quality.py --json-out -` → `{"verdict":"PASS","score_cap":100,...}` (reprodutível na i7-1355U com `cargo-udeps v0.1.61` + `tree-sitter` instalados).

## Detectores (todos limpos)

| Detector | Resultado | Ferramenta |
|---|---|---|
| D1 — Dead code | **0** símbolos mortos | `cargo +nightly udeps` (real, instalado nesta sessão) |
| D2 — Symbol fabrication | **0** crates fabricados | tree-sitter + crates.io |
| D3 — Cross-package wiring | **0** orphan exports | ast-grep |
| Cross-check independente | **0** deps não usadas ("Good job!") | `cargo machete` |

## Achado do próprio gate (corrigido nesta sessão)

O detector Rust D2 emitia **98 falso-positivos** de "symbol fabrication" (verdict FAIL_HARD)
antes deste run: marcava como crate fabricado todo `use` de stdlib (`std`/`core`/`alloc`, 57×),
crates internos do workspace Cargo (`macaw_*`, 40×) e imports com alias `use x as y` (1×) —
nenhum é fabricação. Corrigido com TDD em `.claude/skills/code-quality/scripts/detectors/rust.py`
(commit `93bd547`, 3 testes de regressão, 105/105 do skill verdes). Sem o fix, o gate seria
inutilizável para qualquer código Rust do projeto. **Consertar o linter, não suprimir** (Regra 9 +
honestidade). Detalhe no CHANGELOG `[Unreleased] § Fixed`.

## Handoff

Verdict `PASS` ∈ {PASS, PASS_WITH_CAVEATS} → **libera `/review`** (pré-condição de `cycle-review.md`).
Base de testes do incremento: 12/12 do `macaw-asr` verdes, incluindo a prova em fala real
(`real_speech_test.rs`, 86% word-overlap `[MEDIDO]`).
