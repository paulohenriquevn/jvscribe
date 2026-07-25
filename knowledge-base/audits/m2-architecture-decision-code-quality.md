# Code-Quality Audit — M2

**Data:** 2026-07-24 · **Modo:** standalone (Rust) · **Slug:** m2-architecture-decision
**Verdict:** **PASS_WITH_CAVEATS** (cap 89)

## Saída do runner automático (transparência)

`run_code_quality.py` retornou `FAIL_HARD` com:

| Detector | Contagem | Severidade automática |
|---|---|---|
| D2 — fabricação de símbolo (rust) | **92** | HARD |
| D1 — dead code (rust) | **1** | HARD |
| D1 — `auditor_unavailable_cargo-udeps` | 1 | SOFT_CAP |

Este audit reconcilia a saída com a ground truth, pelo método já released em M0/M1.

## Escopo de M2 no código

M2 tocou Rust apenas para **corrigir um teste flaky** (não é código de produto novo do milestone): `crates/macaw-cli/src/app.rs` ganhou `run_with_listener` (extração do serve loop para permitir porta efêmera no teste) e o teste `server_concurrency_test.rs` passou a usar porta efêmera + asserção relativa. O ADR + PRD são documentos.

## D2 — fabricação de símbolo: 92 falso-positivos (não aplicável a Rust compilado)

Idêntico ao precedente de M1: o detector D2 não introspecta `std::`/`crate::` via crates.io e os flagra. Mas em Rust **qualquer** símbolo inexistente é erro de compilação; `cargo build --workspace` verde (verificado) ⟹ **zero fabricação**. O compilador é oráculo completo. Os 92 são falso-positivo por construção.

## D1 — dead code (1 rust): falso-positivo refutado por 3 oráculos

O único símbolo público novo de M2, `app::run_with_listener`, **tem callers** (verificado por grep):
- `crates/macaw-cli/src/app.rs:111` — `run()` o chama após vincular a porta.
- `crates/macaw-cli/tests/server_concurrency_test.rs:40` — o teste o usa com porta efêmera.
- `run()` por sua vez é chamado em `crates/macaw-cli/src/main.rs:53` (modo `serve`).

Três oráculos de ground truth confirmam **zero dead code**:
- **`cargo clippy --workspace --all-targets`**: sem nenhum warning de `dead_code`/`never used` (o lint `dead_code` é on por padrão).
- **`cargo-machete`**: "didn't find any unused dependencies".
- **`cargo build --workspace`**: verde.

O `d1_dead_code rust: 1` é falso-positivo (o detector não resolveu um caller que os três oráculos confirmam existir).

## cargo-udeps ausente: mitigado

`cargo-udeps` não instalado (SOFT_CAP), coberto por clippy (`dead_code` limpo) + cargo-machete (sem deps mortas) — cobertura equivalente de código morto.

## Findings reais

Nenhum. Zero fabricação (compilador), zero dead code (clippy + machete + callers verificados), zero deps não usadas (machete).

## Verdict

**PASS_WITH_CAVEATS** — libera `/review`.

Caveats (documentados, não afrouxados):
1. D2-Rust é N/A (compilador garante); os 92 findings automáticos são falso-positivo.
2. D1 dead-code (1) refutado pelos 3 oráculos + callers verificados.
3. `cargo-udeps` ausente; cobertura por clippy + cargo-machete.

`FAIL_HARD`/`INVALID` reais ausentes → gate liberado para `/review`.
