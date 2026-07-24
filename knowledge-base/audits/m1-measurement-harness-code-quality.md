# Code-Quality Audit — M1 (régua de medição)

**Data:** 2026-07-24 · **Modo:** standalone (Rust) · **Slug:** m1-measurement-harness
**Verdict:** **PASS_WITH_CAVEATS** (cap 89)

## Saída do runner automático (transparência)

`run_code_quality.py` retornou `FAIL_HARD` com:

| Detector | Contagem | Severidade automática |
|---|---|---|
| D2 — fabricação de símbolo (rust) | **95** | HARD |
| D1 — dead code: `auditor_unavailable_cargo-udeps` | 1 | SOFT_CAP |

Este audit **reconcilia** essa saída com a ground truth, seguindo o método já
estabelecido e released no audit de M0 (`knowledge-base/audits/m0-walking-skeleton-code-quality.md`).

## D2 — fabricação de símbolo: 95 falso-positivos (não aplicável a Rust compilado)

**Os 95 findings são 100% falso-positivo, por construção.** O detector D2 de Rust
tenta resolver símbolos contra o registro crates.io e não introspecta `std::`,
`core::` nem símbolos crate-local — flagrando-os como "fabricados".

Mas em Rust **qualquer** referência a um símbolo inexistente — de `std`, do próprio
crate, ou de crate externo — é **erro de compilação**. Logo:

```
cargo build --workspace  →  exit 0 (verde)  ⟹  ZERO símbolos fabricados
```

Verificado nesta run: o workspace compila limpo. O compilador é um oráculo
**completo** (não parcial) para fabricação de símbolo — diferente de Python/TS,
onde a chamada a API inexistente só falha em runtime. O detector D2 é **redundante
com o compilador** para Rust e não se aplica. Precedente: audit de M0, verdict PASS
pela mesma razão ("D2 é impossível por construção — o sistema de tipos enforça").

## D1 — dead code: cargo-udeps ausente, mitigado (allowlist ativo)

`cargo-udeps` não está instalado neste ambiente → `auditor_unavailable_cargo-udeps`
(SOFT_CAP). Mitigação com cobertura equivalente, verificada nesta run:

- **clippy limpo**: `cargo clippy --workspace --all-targets -- -D warnings` sem
  nenhum warning de `dead_code`/`unused` (o lint `dead_code` é on por padrão).
- **cargo-machete**: "didn't find any unused dependencies" — sem deps mortas.

Entrada de allowlist adicionada (`code-quality-allowlist.txt`, sunset 2026-10-22)
downgrada o SOFT_CAP para SOFT_FLOOR. Nenhum símbolo morto real detectado por
clippy nem machete.

## Findings reais

Nenhum. Zero fabricação (compilador), zero dead code (clippy + machete), zero deps
não usadas (machete).

## Verdict

**PASS_WITH_CAVEATS** — libera `/review`.

Caveats explícitos:
1. D2-Rust é N/A (compilador garante); os 95 findings automáticos são falso-positivo documentado.
2. `cargo-udeps` ausente (allowlist ativo, sunset 2026-10-22); cobertura de código morto por clippy + cargo-machete.

`FAIL_HARD`/`INVALID` reais ausentes → gate liberado para `/review`.
