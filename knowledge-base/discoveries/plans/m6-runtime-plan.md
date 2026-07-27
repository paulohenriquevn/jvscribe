# Discovery Plan: Runtime CTC em Rust para M6 (decoder + hotwords + int8 + streaming)

> **Version 1.1** (EC-1/EC-2 absorvidos do edge-case review) — Investiga COMO implementar o runtime otimizado de M6 (o decoder CTC em
> Rust que o `macaw-asr` deixou explicitamente adiado esperando M2, agora desbloqueado —
> `macaw-asr/src/lib.rs:197`), estudando os peers de runtime CPU já clonados: **sherpa-onnx**
> (C++, referência de CTC greedy + hotwords ContextGraph), **parakeet-rs** (Rust, runtime ASR
> CPU — o mais próximo do nosso), com **tract**/**icefall** como apoio. Output: blueprint com
> os algoritmos, deps, tooling e padrão de teste a portar para o `macaw-asr`/`macaw-cli`.

**Slug:** `m6-runtime`
**Owner:** Paulo (via CYCLE autônomo)
**Created:** 2026-07-26
**Time budget:** 6h (sherpa-onnx 3h, parakeet-rs 3h — breakdown em D1)

## Context

M6 (ROADMAP § M6) exige o runtime otimizado: decoder Rust conforme a arquitetura de M2
(FLToP + blank-skipping se CTC), int8 AVX-VNNI medido, os 5 critérios RNF-01..05 no i7-1355U,
hotwords (boost→poda). O de-risk de real-time já foi medido `[MEDIDO]` (`training/results/m6-realtime-current-model.md`:
RTFx 41-90×, soak sem throttle, carga 25-44×) — a **velocidade** está encaminhada. Falta a
**implementação**: o `macaw-asr` carrega o ONNX e faz `encode()` (`crates/macaw-asr/src/lib.rs:205`)
mas o comentário `lib.rs:197` diz que o decode encoder→texto ficou adiado esperando a decisão de
arquitetura de M2 — que **já saiu: CTC** (ADR `knowledge-base/adrs/0001-m2-architecture-finalists.md`).
Este discovery fecha o "como" antes de escrever o decoder, respeitando `rules/architecture.md`
(o decoder é domínio; o adapter ONNX é infra — DIP), `rules/asr-evidence-discipline.md` (todo
número rotulado) e `rules/testing.md` (o padrão de teste do decoder vem de um peer, não inventado).

## Objective

Decidir COMO implementar o decoder CTC em Rust (+ hotwords + config int8 + gancho de streaming)
no `macaw-asr`, portando padrões testados dos peers em vez de inventar. Sucesso do blueprint:

- [ ] Todas as questões respondidas com citação a `knowledge-base/references/`
- [ ] Tabela comparativa cross-cutting populada (sherpa-onnx C++ vs parakeet-rs Rust)
- [ ] ≥ 1 proposta de decisão concreta por questão (ex.: "portar o loop de X, adaptar Y")
- [ ] `/discover-confidence` ≥ SHIPPABLE_WITH_CAVEATS

## In-Scope / Out-of-Scope

### In-Scope (per reference project)

| Project | In-scope subdirectories | Reason |
|---|---|---|
| `knowledge-base/references/sherpa-onnx/` | `sherpa-onnx/csrc/offline-ctc-greedy-search-decoder.{cc,h}`, `sherpa-onnx/csrc/context-graph.{cc,h}`, `sherpa-onnx/csrc/context-graph-test.cc` | Referência C++ de CTC greedy + hotwords + teste |
| `knowledge-base/references/parakeet-rs/` | `src/decoder.rs`, `src/model.rs`, `src/audio.rs`, `Cargo.toml`, `examples/streaming.rs` | Runtime ASR em **Rust** — o padrão que o `macaw-asr` vai espelhar |
| `knowledge-base/references/icefall/` | `egs/librispeech/ASR/zipformer/export-onnx-ctc.py` (já usado) | Confirmar o contrato de I/O do ONNX CTC (x, x_lens → log_probs) |

### Out-of-Scope (explicit)

| Project / Subdir | Why excluded |
|---|---|
| `sherpa-onnx/` decoders transducer/whisper/paraformer | Nosso modelo é CTC — só o CTC greedy + context-graph importam |
| `tract/` | ONNX engine alternativo; já usamos `ort` no `macaw-asr` — reavaliar só se `ort` falhar (D3) |
| `moonshine/`, `funasr/`, `vibeasr-cpp/` | Cache de estado (moonshine) e outros são de M7/streaming avançado — fora do runtime v0 |
| `**/build/`, `**/dist/`, `**/*.onnx` | Artefatos |
| Streaming cache-aware deep-dive | Adiado (D3): precisa de modelo causal, que ainda não existe |

## ADRs

### D1 — Time budget + stop conditions

**Decision:** sherpa-onnx 3h (CTC greedy + context-graph + teste), parakeet-rs 3h (o padrão Rust).

**Rationale:** sherpa-onnx é a referência canônica de CTC/hotwords em CPU (catálogo `_catalog.md`
tagueia M6); parakeet-rs é o único runtime ASR em Rust da lista → o mais transferível ao `macaw-asr`.
icefall entra só para confirmar o contrato de I/O do ONNX (custo baixo, já conhecido).

**Alternatives considered:** split igual (rejeitado — icefall é confirmação rápida), só sherpa-onnx
(rejeitado — perde o padrão Rust idiomático do parakeet-rs).

**Stop condition — per question:** se Fase A retorna vazio após 3 variações de query, marca BLOCKED
com razão e segue. **Per project:** budget esgotado → questões restantes BLOCKED; se todas as
restantes estão `done`/`blocked`, emite `<promise>BLUEPRINT_BLOCKED</promise>` honesto.

**Anti-pattern:** NUNCA fabricar resposta de Fase B para fechar questão com Fase A esgotada (Regra 3).

**Consequences:** o halt-loop para por projeto no fim do budget; questões bloqueadas viram semente do próximo discovery.

### D2 — Investigation depth

**Decision:** ler end-to-end os arquivos de decode/context-graph (são pequenos e densos); grep+read
pontual no parakeet-rs (seguir o fluxo `model.rs → decoder.rs`).

**Rationale:** o decode CTC e o ContextGraph são algoritmos que serão portados linha-a-linha —
exigem leitura completa; o padrão Rust é estrutural (seguir o fluxo, não decorar cada linha).

**Consequences:** cobertura profunda no que vira código nosso; estrutural no que vira convenção.

### D3 — Streaming adiado para follow-up

**Decision:** o streaming cache-aware (RNF-02) é investigado só o suficiente para mapear o GANCHO
(onde o estado entraria), não em profundidade — deep-dive fica para um discovery `m6-streaming`
posterior.

**Rationale:** o modelo atual é non-causal; medir/implementar streaming honesto exige um modelo
causal (`train --causal 1`) que ainda não existe. Investigar cache em profundidade agora seria
premature (YAGNI) — mas o runtime v0 deve deixar o gancho.

**Consequences:** runtime v0 = offline (CTC greedy) end-to-end; streaming é extensão posterior.

## Research Questions

| # | Question | Corner | Reference project(s) | Fase A (broad — grep/ast map) | Fase B (deep — Read) | Expected answer shape |
|---|---|---|---|---|---|---|
| Q1 | Como o sherpa-onnx implementa o CTC greedy decode (argmax por frame → colapso de repetidos → remove blank)? Qual o id do blank e a ordem exata das operações? | techniques | sherpa-onnx | grep `Decode\|blank\|argmax` em `csrc/offline-ctc-greedy-search-decoder.cc` | Ler `offline-ctc-greedy-search-decoder.{cc,h}` end-to-end | Pseudocódigo do loop + id do blank + edge-cases (frame vazio) → portável p/ Rust |
| Q2 | Qual a **estrutura Rust** do parakeet-rs (setup do `ort::Session`, `audio→feat→session`, `Vocab`, gestão de tensores) — o esqueleto que o `macaw-asr` vai espelhar? **ATENÇÃO (EC-1):** parakeet-rs é FastConformer-**TDT** (transducer, `src/lib.rs`) — extrair só a ESTRUTURA/idioma Rust, NÃO o algoritmo de decode (que é TDT); o CTC greedy vem de Q1/sherpa-onnx. | techniques | parakeet-rs | grep `Session\|run(\|Vocab\|Tensor\|feat` em `src/model.rs`, `src/audio.rs` | Ler `src/model.rs` + `src/audio.rs` (o fluxo estrutural, não o `decoder_tdt`); seguir `examples/streaming.rs` só p/ o gancho de estado (D3) | Diagrama do fluxo Rust (audio→feat→session→texto) + config do `ort::Session` + onde o estado entraria — SEM o algoritmo TDT |
| Q3 | Como o sherpa-onnx faz hotwords/contextual biasing (ContextGraph/Aho-Corasick) e respeita a ordem boost→poda? | techniques | sherpa-onnx | grep `boost\|score\|Aho\|fail\|Prune` em `csrc/context-graph.cc` | Ler `context-graph.{cc,h}` end-to-end | Estrutura do trie + como boost é aplicado antes da poda → viabilidade p/ CTC (o caveat do `_catalog`) |
| Q4 | Que ONNX runtime + config de int8/threads o parakeet-rs usa? Bate com o `ort` que o `macaw-asr` já usa? Como configura intra-op threads / quantização? | deps | parakeet-rs | grep `ort\|onnxruntime\|intra\|thread\|int8\|quant` em `Cargo.toml`, `src/model.rs` | Ler `Cargo.toml` (versões) + o setup de sessão em `src/model.rs` | Tabela dep+versão + config de sessão → confirma/ajusta o `macaw-asr` |
| Q5 | Como o parakeet-rs é buildado/testado (o dev/test story de um runtime ASR Rust)? Como um exemplo streaming roda? | tools | parakeet-rs | grep `[[example]]\|dev-dependencies\|test` em `Cargo.toml`; `ls examples/` | Ler `Cargo.toml` + `examples/streaming.rs` | Comandos de build/test/exemplo → o que replicar no `macaw-cli` |
| Q6 | Como o sherpa-onnx testa o decoder CTC / o ContextGraph contra saída de referência (o teste que o nosso decoder Rust vai espelhar)? | tests | sherpa-onnx | grep `TEST\|EXPECT\|assert` em `csrc/context-graph-test.cc` | Ler `context-graph-test.cc` end-to-end | Forma do teste (input→expected) → o teste de regressão do nosso decoder |

## Coverage Matrix

| Corner | Questões | Coberto? |
|---|---|---|
| Techniques | Q1, Q2, Q3 | ✅ (3, no teto) |
| Dependencies | Q4 | ✅ |
| Tools | Q5 | ✅ |
| Integration tests | Q6 | ✅ |

Total: 6 questões (dentro de 5-10), 4 corners cobertas, máx 3/corner respeitado. Nenhum corner deferido.

## Halt-loop checkpoints (para /discover-execute)

- **(EC-2)** Antes de marcar Q1 DONE: confirmar que o `blank_id_` do sherpa (`offline-ctc-greedy-search-decoder.cc:42`) casa com o **blank=0** do nosso ONNX (icefall `blank_id: 0`) — senão o colapso remove o token errado.
- Antes de marcar Q1/Q3/Q6 DONE: a citação `arquivo:linha` tem de **exibir** o algoritmo/teste (não vizinhança).
- Antes de marcar Q2/Q4/Q5 DONE: o fluxo/dep citado tem de resolver a um símbolo real no `parakeet-rs`.
- Streaming (D3): só mapear o gancho; não abrir cache-deep — se o loop começar a investigar cache em profundidade, PARAR (fora de escopo).

## Acceptance Criteria

- [ ] Cada questão respondida com citação `knowledge-base/references/...:linha` que exibe o fato.
- [ ] Tabela comparativa sherpa-onnx (C++) × parakeet-rs (Rust) para CTC decode.
- [ ] ≥ 1 proposta concreta por questão (o que portar e como adaptar ao `macaw-asr`).
- [ ] Seção de blocked questions honesta (se houver).

## Global Definition of Done

- `/discover-confidence` ≥ SHIPPABLE_WITH_CAVEATS (`rules/discover-blueprint-golden-rule.md`).
- Sem citação fabricada (hard cap). 4 coverage corners populados (hard cap).
- Blueprint em `knowledge-base/discoveries/blueprints/m6-runtime-blueprint.md`.
