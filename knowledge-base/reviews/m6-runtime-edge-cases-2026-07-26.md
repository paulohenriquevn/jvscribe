# Discover Edge Case Review — m6-runtime

Date: 2026-07-26
Discovery plan analyzed: knowledge-base/discoveries/plans/m6-runtime-plan.md
Research questions analyzed: 6
Edge cases found: 3 (MUST FIX: 1, SHOULD TEST: 1, DOCUMENT: 1)

## MUST FIX

### EC-1: parakeet-rs é FastConformer-**TDT** (transducer 600M), não CTC
- **Affected question:** Q2
- **Family:** Interpretation
- **Scenario:** Q2 pede "espelhar o fluxo ONNX→decode do parakeet-rs". Mas `parakeet-rs/src/lib.rs`
  declara `//! based on the FastConformer-TDT architecture` + `mod decoder_tdt`. O algoritmo de
  decode dele é **transducer (TDT)**, não CTC greedy.
- **Impact:** `/discover-execute` poderia portar o loop de decode TDT (com joiner/blank-por-token)
  como se fosse o nosso CTC — errado. Nosso decode é CTC greedy (argmax por frame + colapso), que
  vem de Q1 (sherpa-onnx `offline-ctc-greedy-search-decoder.cc:42`).
- **Suggested fix:** reescrever Q2 para "extrair a **estrutura Rust** (setup do `ort::Session`,
  `audio→feat→session`, `Vocab`, gestão de tensores) — NÃO o algoritmo de decode (que é TDT no
  parakeet-rs); o algoritmo CTC vem de Q1/sherpa-onnx."

## SHOULD TEST

### EC-2: blank_id do sherpa é configurável (`blank_id_`) — precisa casar com o nosso export (blank=0)
- **Affected question:** Q1
- **Suggested halt-loop checkpoint:** antes de marcar Q1 DONE, confirmar que o `blank_id_` usado no
  `offline-ctc-greedy-search-decoder.cc:42` corresponde ao **blank=0** do nosso ONNX (icefall
  `blank_id: 0` no config de treino) — senão o decode colapsa o token errado.

## DOCUMENT

### EC-3: hotwords ContextGraph "só funcionam com transducer" (restrição conhecida) vs nosso CTC
- **Affected question:** Q3
- **Accepted risk:** o `_catalog.md` e o próprio sherpa documentam que hotwords via ContextGraph
  foram desenhadas para transducer. Q3 EXISTE justamente para avaliar a viabilidade em CTC — não é
  defeito do plano, é o propósito da questão. Se Q3 concluir "inviável em CTC greedy puro", isso é
  um resultado válido do blueprint (e vira decisão de arquitetura de decode em M6/M7, não um blocker
  do runtime v0 offline). Já sinalizado na coluna "Expected answer shape" de Q3.

## Summary

| Question | Edges found | MUST FIX | SHOULD TEST | DOCUMENT |
|----------|-------------|----------|-------------|----------|
| Q1 | 1 | 0 | 1 | 0 |
| Q2 | 1 | 1 | 0 | 0 |
| Q3 | 1 | 0 | 0 | 1 |
| Q4-Q6 | 0 | 0 | 0 | 0 |

**Verdict:** DISCOVERY PLAN NEEDS ADJUSTMENT (1 MUST FIX — absorver EC-1 em Q2; EC-2 vira checkpoint).
