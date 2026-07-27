# Review: m6-runtime-v0

**Data:** 2026-07-26 · **Cycle:** REVIEW (gate pré-merge) · **Escopo:** runtime v0 do M6 (decoder CTC em Rust), commits `32946fc~1..de1f3da`
**Revisores (agentes paralelos):** 4 — architecture, tests, wiring, cross-validation
**Achados:** 17 (BLOCKER: 0, HIGH: 4, MEDIUM: 6, LOW/INFO: 7)
**Verdict:** **NEEDS_FIXES**

## Contexto

Gate pós code-quality (PASS 100). Os 4 agentes convergiram: o **núcleo do decode (Fases 1+2) é sólido** — domínio puro, DIP correto, Regra 9 verificável linha-a-linha, zero `unwrap()` de produção, prova de fala real reproduzível (86% word-overlap). Os achados HIGH/MEDIUM são de **cobertura de teste** e **completude de wiring**, não de correção do algoritmo.

## BLOCKER
Nenhum.

## HIGH (corrigir antes do merge)

### F1 — T-01: falta teste da semântica central do CTC
- **Found by:** tests · **File:** `crates/macaw-asr/tests/ctc_decode_test.rs`
- Repetição do mesmo token **separada por blank** não deve colapsar (`[1,0,1]→[1,1]`). É a propriedade que define o CTC. Nenhum teste a cobre; um refactor que quebre `decode.rs:41` (atualizar `prev=blank` no frame de blank) passaria verde.
- **Ação:** adicionar `ctc_greedy_preserva_repeticao_separada_por_blank`.

### F2 — T-02: testes de integração reportam verde em skip
- **Found by:** tests, cross-validation · **File:** `tests/{transcribe_smoke,real_speech}_test.rs`
- `if !model.exists() { return; }` conta como PASSED no cargo (não IGNORED). No CI (sem fixture) a camada de integração é **verde-fictícia** (Regra 3, testing.md §6).
- **Ação:** `#[ignore = "requer fixture"]` em vez de early-return silencioso.

### F3 — CV-03/WIRING-01/02: Fase 3 (wiring wav→texto) MISSING
- **Found by:** wiring, cross-validation, architecture · **File:** `crates/macaw-cli/`
- O subcomando `transcribe <wav>` + caller de produção (pilar a) + métrica (pilar c) **não foram entregues**. `grep transcribe crates/macaw-cli/` → 0. Bloqueado pela **task #25** (fbank 128-bin macaw-audio vs 80-bin icefall). **Mérito:** bloqueio transparente, sem caller falso (o `real_speech_test` prova o decode com features 80-bin corretas do lhotse).
- **Ação:** resolver task #25 (fbank 80-bin kaldi no macaw-audio) → então wiring do CLI + métrica fecham os pilares (a)+(c). M6 não fecha como "wiring completo" até lá.

### F4 — ARCH-01: `AsrEngine` sem trait de backend
- **Found by:** architecture · **File:** `crates/macaw-asr/src/lib.rs:124-305`
- Dois caminhos de inferência concretos (`encode()` NeMo-M0 + `ctc_logits()` icefall) coexistem sem trait. O mandato DIP + o limiar YAGNI (2 casos concretos) sugerem extrair `trait CtcBackend` antes da Fase 3.
- **Ação (a decidir):** ou extrair o trait, ou — mais parcimonioso — quando o CLI passar a usar `transcribe()`, o `encode()` placeholder M0 vira morto e é **removido**, deixando 1 caminho (sem trait, YAGNI). Decisão registrada no fix loop.

## MEDIUM
- **ARCH-02**: blank id `0` mágico em `transcribe()` → `const ICEFALL_BLANK_ID`.
- **ERR-01**: truncamento de entrada curta em `ctc_greedy` é silencioso; comentário atribui mal `error-handling.md`. Emitir sinal observável (contador) + corrigir comentário.
- **T-03**: `Vocab::load` sem testes dos erros tipados `VocabNotFound`/`InvalidVocab`.
- **T-04**: `detok` sem caso negativo de id fora do range (perda silenciosa quando `tokens.txt` diverge do vocab do modelo).
- **T-05/T-06**: `argmax` e `detok` testam 2 comportamentos por teste; `detok` usa fixture temp mutável de nome fixo (colisão sob paralelismo).

## LOW/INFO
T-07 (NaN/empate em argmax), T-08 (ramos `vocab==0`/`t_len==0`/`blank!=0`), T-09 (`AsrEngine::load` ModelNotFound sem teste), T-10 (`word_overlap` é recall, não WER — comentário conflaciona), CV-07 (clippy/test workspace não re-rodados pelos agentes), PROC-01 (decoder icefall antes de M4 — decisão do dono documentada), OK-01..04 (domínio puro, SRP, Regra 9, sem unwrap de produção). Nota RF-06: a porta do sherpa omite timestamps (escopo futuro explícito).

## Cross-validation summary
- Plan tasks: 3 · fully: 2 (Fase 1, 2) · partial: 0 · missing: 1 (Fase 3) · diverged: 1 (fbank 128 vs 80)

## Quality gates
- `cargo test -p macaw-asr`: PASS (12/12) · code-quality: PASS 100 · CHANGELOG [Unreleased]: atualizado (Regra 6 ✔)
- clippy/test do **workspace inteiro**: a re-rodar no fix loop (CV-07).

## Handoff decision

**NEEDS_FIXES** → loop back to fix (cycle-review § Verdicts). Ordem do fix loop:
1. Fixes de teste F1/F2 + T-03/04/05/06/09 (Rust puro, imediato) — fecham 2 HIGH + casos negativos.
2. ERR-01 + ARCH-02 (observabilidade + const) junto do wiring.
3. **Task #25 — fbank 80-bin kaldi no macaw-audio** (keystone): destrava a Fase 3, fecha pilares (a)+(c), entrega o demo wav→texto. Decide ARCH-01 (trait vs remover encode() morto).
4. `cargo clippy --workspace -D warnings` + `cargo test --workspace` (CV-07).

Runtime v0 **não fecha como IMPLEMENTATION_COMPLETE** até a tríade de wiring completar (task #25). O incremento de decode em si é sólido e provado.
