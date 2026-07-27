# Blueprint: Runtime CTC em Rust para M6 (como implementar o decoder)

> Deriva de `knowledge-base/discoveries/plans/m6-runtime-plan.md` (SHIPPABLE). Fecha o "como"
> antes de escrever o decoder CTC em Rust no `macaw-asr`, portando padrões testados de
> **sherpa-onnx** (C++, CTC greedy + hotwords) e **parakeet-rs** (Rust, estrutura ort). Todo
> achado com citação `arquivo:linha` que exibe o fato (`asr-evidence-discipline`).

## Executive summary

O runtime v0 de M6 é **pequeno e desbloqueado**: o `macaw-asr` já carrega o ONNX e faz `encode()`
(`crates/macaw-asr/src/lib.rs:205`); falta o **CTC greedy decode** (adiado esperando M2, agora CTC).
O algoritmo é ~15 linhas (sherpa), a estrutura Rust já é a do nosso `AsrEngine` (bate com parakeet-rs),
as deps já existem (`ort`), e o teste é fixture-based. **Achado honesto:** hotwords via ContextGraph
**não funcionam em greedy** (precisam de beam/lattice com scores) — v0 é greedy sem hotwords; hotwords
são um incremento posterior (CTC beam search). Streaming fica para modelo causal (D3).

## Context

M6 (ROADMAP § M6) exige o runtime otimizado; o de-risk de velocidade já foi medido
(`training/results/m6-realtime-current-model.md`: RTFx 41-90×). O que falta é a implementação do
decode: `macaw-asr/src/lib.rs:197` registra que o `encoder→texto` ficou adiado esperando M2 — que
saiu CTC (ADR `knowledge-base/adrs/0001-m2-architecture-finalists.md`). Este blueprint fecha o "como".

## Objective

Decidir como implementar o decoder CTC greedy em Rust no `macaw-asr` portando padrões testados dos
peers (sherpa-onnx C++, parakeet-rs Rust), sem inventar — habilitando o `/to-plan` do runtime v0.

## Coverage Corner 1 — Integration Tests

**Q6 — como sherpa testa o decode/context-graph** `[FONTE-REPO]`:
`sherpa-onnx/.../context-graph-test.cc:20-42` usa `TestHelper(queries, score, ...)`: monta o grafo,
consulta, e `EXPECT_EQ` no score/token esperado. Padrão = **input conhecido → saída esperada**.

**Recomendação p/ o nosso decoder:** teste de regressão fixture-based — um `log_probs` fixo (ex.:
um tensor pequeno com argmax conhecido por frame, incluindo blanks e repetições) → sequência de
tokens esperada. Cobre os edge-cases do colapso (blank no início/fim, repetição, frame único).
Alinha com `rules/testing.md` (o teste vem de um peer, não inventado). É o RED do TDD do decoder.

## Coverage Corner 2 — Dependencies

**Q4 — ONNX runtime + int8 no parakeet-rs** `[FONTE-REPO]`:
`parakeet-rs/Cargo.toml:46` → `ort = "2.0.0-rc.12"` (default-features=false, features `std,ndarray,api-24`),
`ndarray = "0.17"` (:49), `realfft = "3"` (:53). Features: `cpu`, `cuda`, `coreml` (:60-63).
`src/model.rs:5` `use ort::session::Session`.

**Recomendação:** **nenhuma dep nova** para o v0. O `macaw-asr` já usa `ort` (mesmo crate). O int8
**não** é uma dep — o modelo já sai quantizado do export (`model.int8.onnx`, 27MB) e o `ort`
CPUExecutionProvider roda int8 usando **AVX-VNNI automaticamente** na i7-1355U. Threads via
`SessionBuilder::with_intra_threads` (já validado no `training/bench_rtfx.py:session_options`).
`ndarray` pode entrar se precisarmos manipular o tensor de saída fora do `ort` — avaliar (KISS: o
`try_extract_tensor` já dá um slice, talvez baste).

## Coverage Corner 3 — Tools

**Q5 — build/test/exemplo do parakeet-rs** `[FONTE-REPO]`:
`parakeet-rs/Cargo.toml:58-63` define features (`default = ["cpu","ort-defaults"]`); `examples/streaming.rs`
é o runner de exemplo. Build = `cargo build --features cpu`; exemplo = `cargo run --example streaming`.

**Recomendação:** o `macaw-cli` já é o nosso runner (`crates/macaw-cli/src/app.rs` carrega o `AsrEngine`).
O v0 = adicionar o decode ao `AsrEngine` + um subcomando/fixture no `macaw-cli` que transcreve um wav
→ texto (a "demo ao vivo"). Test = `cargo test -p macaw-asr` (o fixture do Corner 1). Sem tooling novo.

## Coverage Corner 4 — Techniques

**Q1 — CTC greedy decode (o algoritmo a portar)** `[FONTE-REPO]`:
`sherpa-onnx/.../offline-ctc-greedy-search-decoder.cc:34-46` — por frame `t` até `log_probs_length[b]`:
`y = argmax_v log_probs[t]` (`std::max_element`, :37); **`if (y != blank_id_ && y != prev_id)`**
push token (:42) — colapsa blank **e** repetidos; `prev_id = y` (:46). Entrada (B,T,V)+lengths (:17-22).

**Recomendação (o decoder Rust):**
```rust
// macaw-asr: decode(log_probs: &[f32], t_len: usize, vocab: usize, blank: usize=0) -> Vec<usize>
let mut prev = usize::MAX; let mut out = vec![];
for t in 0..t_len {
    let frame = &log_probs[t*vocab..(t+1)*vocab];
    let y = argmax(frame);                 // max_element
    if y != blank && y != prev { out.push(y); }
    prev = y;
}
```
Depois `out.iter().map(|id| vocab.decode(id))` → texto (o `Vocab` já existe em `macaw-asr/lib.rs:58`).
**EC-2 checkpoint:** blank=0 (icefall `blank_id: 0`) — casa com o export.

**Q2 — estrutura Rust (ort session → texto)** `[FONTE-REPO]`:
`parakeet-rs/src/model.rs:47` `self.session.run(ort::inputs!(...))` → `:54` `.try_extract_tensor::<f32>()`.
Fluxo: `audio → feat (realfft mel, audio.rs:13-21) → session.run → extract_tensor → decode`. É **a mesma
API ort 2.x** que o nosso `AsrEngine.encode` já usa — o decode só consome a saída do `encode()`.
**EC-1 respeitado:** o `decoder_tdt.rs` do parakeet é **transducer** — NÃO portamos ele; só a estrutura
`run→extract`. O algoritmo CTC vem de Q1.

**Q3 — hotwords (ContextGraph) — ACHADO HONESTO** `[FONTE-REPO]`:
`sherpa-onnx/.../context-graph.cc:34-37` aplica `context_score_` (boost) por token com `ac_threshold_`
(poda) — é um **trie scored (Aho-Corasick)** que soma boost ao **score do caminho** durante a busca.
**Isso exige um decode com scores por caminho (beam/lattice)** — o greedy (argmax, sem score de caminho)
**não tem onde aplicar o boost**. Confirma o caveat do `_catalog.md` ("hotwords só com transducer/beam").
**Conclusão:** hotwords **NÃO entram no v0 greedy**; exigem CTC **beam search** (incremento posterior)
ou rescoring. Não é blocker do runtime v0 offline — é um item explícito de M6 que fica para depois do beam.

## Cross-cutting Comparison

| Aspecto | sherpa-onnx (C++) | parakeet-rs (Rust) | Nosso plano (macaw-asr) |
|---|---|---|---|
| Decode | CTC greedy (`:42`) | TDT/transducer (EC-1) | **portar o CTC greedy do sherpa** |
| ort API | Ort::Value | `session.run(inputs!)`+`try_extract_tensor` (`model.rs:47,54`) | já usamos ort 2.x no `AsrEngine` |
| Features | kaldi-native-fbank | realfft mel (`audio.rs`) | já temos `macaw-audio/features.rs` |
| Hotwords | ContextGraph (beam) | — | **fora do v0** (precisa beam) |
| Teste | fixture EXPECT_EQ | — | fixture RED (Corner 1) |

## Recommendations

1. **CTC greedy decode** (Corner 4/Q1): portar o loop do sherpa (`offline-ctc-greedy-search-decoder.cc:42`) — argmax por frame + `if y != blank(0) && y != prev` push. ~15 linhas de Rust puro sobre `&[f32]`, no `macaw-asr`.
2. **Estrutura ort** (Corner 4/Q2): consumir a saída do `AsrEngine.encode()` já existente (ort 2.x, mesma API do parakeet-rs `model.rs:47,54`); NÃO portar o `decoder_tdt` (é transducer — EC-1).
3. **Zero dep nova** (Corner 2/Q4): reusar `ort` + `Vocab`; int8 já vem do export, AVX-VNNI automático no `ort` CPU.
4. **Teste fixture RED** (Corner 1/Q6): `log_probs` conhecido → tokens esperados, cobrindo blank/repetição.
5. **Hotwords fora do v0** (Corner 4/Q3): greedy não tem score de caminho para boost — hotwords exigem CTC beam search (incremento posterior), não bloqueiam o v0.

## ADRs

### D1 — v0 = CTC greedy, sem hotwords, sem streaming
**Decisão:** o runtime v0 implementa só o CTC greedy decode offline (encode→texto), com teste fixture.
**Rationale:** greedy é o mínimo que fecha o pipeline end-to-end (KISS); hotwords precisam de beam
(Q3), streaming precisa de modelo causal (D3) — ambos são incrementos, não pré-requisitos do v0.
**Alternativa rejeitada:** implementar beam+hotwords já — YAGNI (não temos ainda os requisitos de
biasing definidos, e o greedy já dá a demo ao vivo + valida o pipeline).
**Consequência:** o v0 NÃO fecha os DoDs de M6 "hotwords" nem "RNF-02 streaming" — isso é explícito e
honesto; M6 completo depende do beam + causal + M5.

### D2 — reusar `ort` + `Vocab`, zero dep nova
**Decisão:** o decode consome a saída do `AsrEngine.encode()` (ort já presente) e usa o `Vocab`
existente (`lib.rs:58`); nenhuma dep nova.
**Rationale:** Regra 9 + KISS — o algoritmo é ~15 linhas de Rust puro sobre um slice `&[f32]`.
**Consequência:** decoder é domínio puro (testável sem I/O), respeitando `rules/architecture.md` (DIP:
o `ort`/ONNX é infra no `encode`; o decode é domínio).

## Blocked questions (if any)
Nenhuma — as 6 questões foram respondidas com citação `[FONTE-REPO]`.

## O que o blueprint NÃO decide
- O algoritmo de **beam search + hotwords** (fica para o discovery `m6-beam-hotwords`).
- O **streaming cache-aware** (D3, precisa de modelo causal).
- A medição **int8 vs fp32 WER** (item de M6, mede-se na implementação).
