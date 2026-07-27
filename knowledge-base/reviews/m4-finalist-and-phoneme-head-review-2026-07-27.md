# Review: m4-finalist-and-phoneme-head

**Date:** 2026-07-27
**Mode:** fit-for-purpose (3 especialistas paralelos) — a skill `/review` plan-based não se
aplica (M4 é research, sem plan-slug / implementation.md / code-quality audit). Escopo: commits
`2d96c35` (finalista, ADR 0002) + `6c06c83` (cabeça de fonema) + remediação `535184b`.
**Reviewers (spawned agents):** 3 — evaluation-scientist (rigor estatístico), general-purpose
(código+testes), asr-chief-scientist (disciplina de evidência).
**Findings:** 15 total (BLOCKER: 0, HIGH: 2, MEDIUM: 7, LOW: 6) — **todos remediados em `535184b`**.
**Verdict:** READY_TO_MERGE

## Como o veredito foi alcançado

Nenhum reviewer achou BLOCKER: a decisão do finalista (Zipformer-CTC small) e a matemática do
bootstrap pareado estão **corretas, deterministas e testadas**; nenhuma falácia §3 #2/#6/#7/#12
sobrevive; nenhuma conclusão excede a evidência no corpo. Os 2 HIGH e 7 MEDIUM eram defeitos de
**disciplina/robustez/honestidade** (não de mérito), todos fix barato — corrigidos antes do merge.

## HIGH (2) — resolvidos

| # | Finding | Resolução (`535184b`) |
|---|---|---|
| H-A | "DoD VALIDADA" superestima evidência fronteiriça (IC inf. 2,63% < 3%, P=94,1%) | Headline → "atingida no ponto (IC fronteiriço)"; **critério de DoD declarado** (estimativa pontual; IC como qualificação obrigatória) no doc + CHANGELOG |
| H-B | Delta que decide o finalista (2,71pp Zipformer vs Conformer) sem IC + recogs não preservados (§3 #12 no número mais decisivo) | Re-decode limpo do Zipformer-medium (WER 28,86% confirmado); **bootstrap pareado → IC95% [2,11, 3,31], exclui 0, P(Conformer melhor)=0%**; recogs de ambos commitados; IC gravado no ADR + m4-decision |

## MEDIUM (7) — resolvidos

| Finding | Resolução |
|---|---|
| CER baseline errado (~11,0% a olho vs 11,42% medido), propagado ao CHANGELOG | 11,42% full-test em doc + CHANGELOG; queda real 0,57pp |
| P(>0)/P(≥3%) atribuídos ao script mas não emitidos por ele | `bootstrap_wer_ci.py` emite as duas probabilidades (proveniência fechada) |
| silent-zero em recogs vazio (`cer_from_recogs`) | `ValueError` em recogs vazio + teste |
| silent-zero em rows vazio (`bootstrap_wer_ci`) | `ValueError` + teste |
| deps de áudio arrastadas para tool de texto puro | `word_edit_distance` → `wer_core.py` dep-light |
| recogs stale telefônico (38,60%) com nome-default (footgun) | Renomeado `.STALE-...-DO-NOT-USE` + README |
| Conformer nunca medido no `small` (extrapolação não declarada) | Limite explícito no ADR ("O que NÃO decide") |
| RTFx/int8 medidos sem a cabeça; RTFx clip/sem-soak; "custo zero" sem rótulo | Caveats + rótulos `[ESTIMATIVA/FONTE-REPO]` nos limites do ADR |
| PRD §8.1 + CLAUDE.md staleness ("em curso") | "concluído — −4,63% rel, PASS com nota" |

## LOW (6) — resolvidos

encoding utf-8 no bootstrap; teste do branch `count>1` do patcher; `SyntaxError` capturado no
`cer` main; footnote de proveniência do CER small (runtime) no ADR; "int8 lossless" qualificado
(n=100 sem IC); "large avg=9 ≈ avg=10" rotulado `[ESTIMATIVA]`.

## Quality gates

- Testes puros: **36 passed** (era 12 antes da remediação; +casos negativos empty-input, count>1, probabilidades).
- `bootstrap_wer_ci.py` reproduz os números do artefato (Δ 1,39pp IC [0,77, 2,01]; rel 4,63% IC [2,63, 6,63]; P(>0)=100%; P(≥3%)=94,1%) — deterministas (seed=42).
- Modelo finalista exportado + verificado local (`models/m4-final-phoneme-small/`, smoke WER 27,74%, grafo ONNX sem nós de fonema, SHA íntegro).

## Handoff decision

**READY_TO_MERGE** — 0 BLOCKER, 2 HIGH resolvidos com evidência medida, 7 MEDIUM + 6 LOW
remediados em `535184b`. Segue para o release local `develop → main` + tag `v0.1.0`.
