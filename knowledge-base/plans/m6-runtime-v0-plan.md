---
slug: m6-runtime-v0
milestone_id: M6
created_at: 2026-07-26
goal: Implementar o decoder CTC greedy em Rust que transcreve um wav em texto pelo modelo int8, com teste fixture verde.
---

# Plano: Runtime v0 de M6 — decoder CTC greedy em Rust

## Goal

Fazer o `macaw-cli` transcrever um wav em texto usando o `model.int8.onnx` via um decoder CTC
greedy em Rust — **métrica: `cargo test -p macaw-asr` verde com um teste fixture que decoda um
`log_probs` conhecido para a sequência de tokens esperada (colapso blank+repetição).**

## Context

Do blueprint `knowledge-base/discoveries/blueprints/m6-runtime-blueprint.md` (SHIPPABLE): o de-risk
de velocidade já foi medido (`training/results/m6-realtime-current-model.md`: RTFx 41-90×). Falta a
implementação do decode. O algoritmo vem de `sherpa-onnx/.../offline-ctc-greedy-search-decoder.cc:42`
(argmax + skip blank + dedup); a estrutura ort já é a do `AsrEngine`. **Achado do deep-review:** o
`encode()` atual (`crates/macaw-asr/src/lib.rs:205`) é placeholder de M0 — usa input names
`audio_signal/length/outputs` (estilo NeMo) e retorna o SHAPE, não os logits (`:234` descarta os
dados com `_`). O nosso ONNX icefall usa `x`(1,T,80)/`x_lens`→`log_probs`(1,T,500) — então o v0
adapta a inferência ao contrato real.

## Baseline Context

### Files that will be touched

| Arquivo | LoC | último commit | papel |
|---|---|---|---|
| `crates/macaw-asr/src/lib.rs` | 242 | `001f562` (M0) | `AsrEngine` (encode placeholder), `Vocab` |
| `crates/macaw-asr/src/decode.rs` | 0 (NEW) | — | decode CTC greedy + detokenização BPE (domínio puro) |
| `crates/macaw-asr/tests/ctc_decode_test.rs` | 0 (NEW) | — | fixture RED do decode |
| `crates/macaw-cli/src/app.rs` | ~450 | — | wiring wav→texto (demo) |

### Current callers / dependents

- `AsrEngine::encode` → chamado em `crates/macaw-asr/tests/forward_pass_test.rs` e `crates/macaw-cli/src/app.rs:447` (via `AsrEngine::load`). Mudar a assinatura de `encode` quebraria esses — por isso o v0 **adiciona** `ctc_logits()` + `transcribe()` em vez de mudar `encode()` (preserva o M0-proof).
- `Vocab::decode(id)` → novo consumidor: a detokenização.

### Architecture boundaries affected

- **Domínio puro:** o decode CTC + detokenização (funções sobre `&[f32]`/`&[usize]`, sem I/O) → `decode.rs`, unit-testável sem ONNX.
- **Infra:** a inferência ONNX (`ort::Session.run`) fica no `AsrEngine` (adapter). DIP: o domínio não importa `ort`.

### Domain glossary

- **CTC greedy collapse:** por frame, pega o argmax; emite o token só se ≠ blank E ≠ token anterior.
- **blank:** id 0 (icefall `blank_id: 0`, confirmado no config de treino).
- **BPE detok:** pieces sentencepiece com `▁` = fronteira de palavra → juntar e trocar `▁` por espaço.

## Prior Art & Related Work

- Blueprint `m6-runtime-blueprint.md` (SHIPPABLE) — algoritmo + estrutura + achado de hotwords/streaming.
- `knowledge-base/references/sherpa-onnx/.../offline-ctc-greedy-search-decoder.cc` — o algoritmo canônico.
- `knowledge-base/references/parakeet-rs/src/model.rs:47,54` — o padrão `session.run(inputs!)`+`try_extract_tensor`.

## ADRs

### ADR-1 — adicionar `ctc_logits()`+`transcribe()`, NÃO mudar `encode()`
**Decisão:** novos métodos para o I/O do nosso modelo; `encode()` (M0-proof) permanece.
**Rationale:** `encode()` tem callers (Baseline § callers); mudá-lo quebra o M0-proof e viola OCP
(`rules/architecture.md`). Adicionar é extensão, não cirurgia. **Alternativa rejeitada:** reescrever
`encode()` — quebra callers + perde a prova de M0.
**Consequência:** um método novo que casa `x`/`x_lens`→`log_probs` (dados reais, não shape).

### ADR-2 — decode como domínio puro em `decode.rs`
**Decisão:** CTC greedy + detok são funções puras sobre slices, sem `ort`.
**Rationale:** DIP + testabilidade (`rules/architecture.md`, `rules/testing.md`) — o decode é a lógica
de negócio, testável com fixture sem carregar ONNX. **Alternativa rejeitada:** inline no `encode` —
acopla domínio a infra, intestável sem modelo.
**Consequência:** `cargo test` roda o decode sem GPU/ONNX (fixture).

## Dependency Graph

- Fase 1 (decode.rs puro + fixture) — independente, não precisa de ONNX. **Começa aqui.**
- Fase 2 (ctc_logits/transcribe no AsrEngine) — depende de nada de código, mas o teste de integração usa o `model.int8.onnx`.
- Fase 3 (wiring macaw-cli + integração) — depende de 1 e 2.

## Phases

### Fase 1 — decode CTC greedy + detok (domínio puro)

#### Task 1.1 — CTC greedy collapse + BPE detok

**Why this step:** portar o algoritmo do sherpa (`offline-ctc-greedy-search-decoder.cc:42`) para Rust
puro é o núcleo do runtime; sem ele não há texto. Raciocínio: é domínio testável (ADR-2), então
começa pelo teste fixture (RED) que fixa o comportamento de colapso antes do código.

**Files to edit:** `crates/macaw-asr/src/decode.rs` (NEW), `crates/macaw-asr/tests/ctc_decode_test.rs` (NEW), `crates/macaw-asr/src/lib.rs` (`mod decode;` + re-export).

**Deep file dependency analysis:** `decode.rs` não depende de `ort` (domínio). Usa `Vocab` (`lib.rs:58`) para mapear id→piece.

#### TDD
- **RED:** `ctc_decode_test.rs` — `log_probs` fixo 4 frames × vocab 5 (argmax conhecido: `[▁a, ▁a, blank, ▁b]`) → esperar tokens `[id(▁a), id(▁b)]` (colapsa o repetido e o blank). E um caso só-blank → `[]`. E a detok `["▁ola","▁mundo"]` → `"ola mundo"`.
- **GREEN:** `ctc_greedy(log_probs, t_len, vocab, blank)->Vec<usize>` (argmax+skip blank+dedup) e `detok(ids, &Vocab)->String` (join pieces, `▁`→espaço, trim).
- **REFACTOR:** extrair `argmax(&[f32])->usize`.

#### Concurrency tests
(none — single-threaded; decode é função pura sobre slice)

#### Acceptance criteria
- `cargo test -p macaw-asr ctc_decode` verde. `clippy` limpo. `decode.rs` < 120 LoC.

#### DoD
- `cargo test -p macaw-asr` verde; `cargo clippy -p macaw-asr -- -D warnings` limpo.

### Fase 2 — inferência do modelo real (x/x_lens → log_probs)

#### Task 2.1 — `AsrEngine::ctc_logits()` + `transcribe()`

**Why this step:** o `encode()` atual não serve ao nosso ONNX (input names errados + retorna shape).
Preciso de um método que rode `x`(1,T,80)/`x_lens`→`log_probs`(dados) e um `transcribe()` que
encadeia logits→`ctc_greedy`→`detok`. Raciocínio: ADR-1 (adicionar, não mudar); é a fronteira infra.

**Files to edit:** `crates/macaw-asr/src/lib.rs` (novos métodos), `crates/macaw-asr/tests/asr_test.rs` (teste de integração se `model.int8.onnx` presente).

**Deep file dependency analysis:** usa `ort::Session.run` (padrão parakeet `model.rs:47`); consome `decode.rs` da Fase 1. Não quebra `encode()` (ADR-1).

#### TDD
- **RED:** teste de integração — se `training/results/onnx/model.int8.onnx` existe, `transcribe(mel,80,T)` retorna String não-vazia sobre um fixture de features conhecido; senão `#[ignore]` com razão.
- **GREEN:** `ctc_logits()` roda a sessão com input names `x`/`x_lens`, `try_extract_tensor` retornando os **dados** (não shape); `transcribe()` = logits→greedy→detok.
- **REFACTOR:** compartilhar a construção de tensores com `encode()` se limpo.

#### Failure scenarios
- Modelo ausente → `AsrError::VocabNotFound`/`NoSession` tipado (não panic). Input shape inválido → `InferenceFailed` com contexto (`rules/error-handling.md`).

#### Acceptance criteria
- `transcribe()` retorna texto; erro tipado se modelo/entrada inválidos. `clippy` limpo.

#### DoD
- `cargo test -p macaw-asr` verde (integração `#[ignore]` se sem modelo).

### Fase 3 — wiring: macaw-cli transcreve um wav (demo)

#### Task 3.1 — subcomando `transcribe <wav>` no macaw-cli

**Why this step:** o wiring triad — o caller de produção que exercita o decode end-to-end (wav →
features `macaw-audio` → `transcribe` → texto). Sem isso o decode é código sem caller. Raciocínio:
`cycle-implement` exige caller + teste de integração + métrica observável.

**Files to edit:** `crates/macaw-cli/src/app.rs` (subcomando), `crates/macaw-cli/tests/` (integração com um wav fixture, `#[ignore]` se sem modelo).

#### TDD
- **RED:** teste que roda `transcribe` sobre um wav fixture curto → String não-vazia (`#[ignore]` se sem `model.int8.onnx`).
- **GREEN:** o subcomando lê wav → `macaw_audio` log-mel → `AsrEngine::transcribe` → imprime texto + um log de métrica (nº de tokens / duração — observabilidade do wiring triad).
- **REFACTOR:** reusar o carregamento do engine já em `app.rs:447`.

#### Acceptance criteria
- `cargo run -p macaw-cli -- transcribe <wav>` imprime texto + métrica.

#### DoD
- `cargo build` + `cargo test` do workspace verdes.

## Coverage Matrix

| Requisito (blueprint) | Task |
|---|---|
| CTC greedy decode (Q1) | 1.1 |
| detokenização BPE (Vocab) | 1.1 |
| estrutura ort / inferência do modelo real (Q2, achado do deep-review) | 2.1 |
| teste fixture RED (Q6) | 1.1 |
| wiring wav→texto (demo, Corner 3) | 3.1 |
| zero dep nova (Q4) | todas (ort/ndarray já são workspace deps) |
| hotwords/streaming FORA do v0 | (explicitamente adiado no blueprint m6-runtime (streaming/hotwords fora do v0)) |

## Global DoD

- `cargo test` do workspace verde; `cargo clippy --workspace -- -D warnings` limpo.
- `decode.rs` < 120 LoC; nenhum arquivo > 500 LoC (`rules/architecture.md`).
- CHANGELOG `[Unreleased]` atualizado (Regra 6).
- Wiring triad completo na Fase 3 (caller + integração + métrica).

## Drawbacks & Risks

| Risco | Sev | Mitigação | Owner |
|---|---|---|---|
| Input names/layout do nosso ONNX diferirem do assumido (`x`/`x_lens`, (1,T,80)) | Médio | Task 2.1 confirma via `session.inputs()` antes; o export já foi inspecionado (bench_rtfx viu `x`,`x_lens`) | impl |
| Detok BPE incorreta (▁, casos de borda) | Médio | fixture cobre ▁ no início/meio; comparar com `sp.decode` do icefall num caso | impl |
| Modelo int8 ausente no CI → testes de integração skipados mascaram bug | Baixo | `#[ignore]` com razão explícita + a Fase 1 (pura) sempre roda | impl |

## Unresolved Questions

- None — o v0 é bem definido e todas as decisões estão resolvidas no plano; hotwords e streaming são explicitamente fora de escopo (não são questões abertas).

## Failure scenarios

- **ONNX ausente/corrompido:** `AsrError::SessionFailed` tipado (já existe em `lib.rs`), sem panic.
- **wav ilegível:** erro tipado no macaw-cli, mensagem clara (`rules/error-handling.md`).
- (Sem I/O de rede/DB — só filesystem local.)

## Final Phase: Integration Validation

- `cargo test --workspace` verde (unit + integração).
- `cargo clippy --workspace -- -D warnings` limpo.
- `cargo run -p macaw-cli -- transcribe <wav-fixture>` imprime texto real do `model.int8.onnx`.
- Se o texto sair vazio/lixo com modelo presente → a fase falhou (eat-your-own-cooking).
