# Code-Quality Audit — M0 Walking Skeleton

> 2026-07-24 · ciclo `cycle-code-quality` · linguagem: Rust
> `.claude/rules/code-quality-golden-rule.md`

## Verdict: **PASS**

Nenhum finding acima de INFO após remediação.

## Detectores

| Detector | Ferramenta | Resultado |
|---|---|---|
| **D1 — Dead code** | `clippy -D warnings` (lints `dead_code`, `unused_*`) | ✅ limpo em todo o workspace, `--all-targets` |
| **D2 — Fabricação de símbolo** | compilador Rust | ✅ garantido pelo sistema de tipos — API inexistente não compila. `cargo build --workspace` verde |
| **D3 — Exports órfãos** | verificação manual de `pub fn` sem uso externo + `cargo-machete` | ✅ 3 `pub fn` órfãos + o módulo `ring` inteiro (código morto, apontado no review H3) **removidos**; 0 dependências não usadas |

> **Nota de método (review H3):** a primeira passagem deste audit usou
> `clippy -D warnings` como proxy de D1, que **não** sinaliza itens `pub` sem
> consumidor no workspace (são superfície de API por definição). O review pré-merge
> pegou `ring::SampleRing` — módulo inteiro construído, testado isolado e nunca
> integrado ao pipeline. Removido. Lição: para Rust, a detecção de código morto
> `pub` precisa de verificação de caller explícita (feita agora manualmente), não
> só clippy.
| **D4 — Mutation testing** | — | N/A para Rust (golden rule § 5: Rust+Go deferidos; só Python/TS) |

## Findings remediados

Três `pub fn` sem nenhum uso externo (nem por teste, caller ou exemplo) foram
**removidos** por YAGNI (`parsimony-ladder` rung 1) — API especulativa que voltará
quando um caller precisar:

| Símbolo | Crate | Motivo |
|---|---|---|
| `AsrEngine::with_vocab` | macaw-asr | Vocab para decode — BLOQUEADO POR M2 |
| `AsrEngine::vocab_len` | macaw-asr | idem; o campo `vocab` foi removido junto |
| `DriftMeter::latest_drift_ms` | macaw-audio | redundante com `record()` + `history()` |

O tipo `Vocab` (com `load`/`len`/`decode`) foi **mantido** — é exercitado pelos
testes de `asr_test` e é primitiva natural de carregamento de artefato.

## Qualidade de teste (informativo)

- **34 testes**, cobrindo comportamento e não estrutura (`.claude/rules/testing.md`).
- **Casos negativos** presentes: source inexistente → erro tipado, janela de tamanho
  errado → erro tipado, modelo ausente → erro tipado (testa error-handling, não só
  happy path — `testing.md` § 4.1).
- **Testes de concorrência** reais: `loom`-style com `--test-threads=8` × 10, sob
  contador atômico e contenção.
- **Zero-alocação provada** por `stats_alloc`, não afirmada.
- **Determinismo**: fixture sintética versionada, sem dependência de rede no CI.

## Guarantia estrutural do Rust

O ponto mais forte: **D2 (fabricação de símbolo) é impossível por construção**.
Diferente de Python/TS, onde uma chamada a API inexistente passa despercebida até o
runtime, em Rust ela é erro de compilação. Todo o código que compõe o veredito PASS
compila, logo nenhum símbolo é fabricado.

## Handoff

`FAIL_HARD`/`INVALID` ausentes → libera `/review`.
