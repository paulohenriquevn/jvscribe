# Review: m1-measurement-harness

**Date:** 2026-07-24
**Reviewers (spawned agents):** 5 — architecture (`rust-runtime-engineer`), tests, wiring, cross-validation, evidence-discipline (`evaluation-scientist`)
**Findings:** 27 total (BLOCKER: 0, HIGH: 1, MEDIUM: 12, LOW: 11, INFO: 3)
**Verdict:** **READY_TO_MERGE**

Todos os 5 agentes concordaram: **zero BLOCKER, zero fabricação de evidência**. O único HIGH e os MEDIUM de defeito foram **corrigidos** nesta iteração; os MEDIUM de escopo são divergências honestas mapeadas a riscos pré-aceitos (R1/R4/R5).

## HIGH — corrigido

### W1: `SampleCounter` era export público sem caller de produção (dead export)
- **Found by:** wiring · **File:** `crates/macaw-audio/src/harness.rs`
- **Resolução:** REMOVIDO (YAGNI). O harness de M1 é usado single-threaded (bench sequencial); a coleta concorrente de amostras das threads de captura é trabalho futuro (soak ao vivo). Teste de concorrência removido; nota explicativa no lugar. Pilar (a) do triad agora íntegro para todos os símbolos públicos.

## MEDIUM — defeitos corrigidos

| # | Achado | Agente | Resolução |
|---|---|---|---|
| F3 | `extract_fixture_features` doc afirmava compartilhamento inexistente + reordenação duplicada | architecture | Extraído helper `mel_features_from_samples` — reordenação em um só lugar; `run_fixture` e `extract_fixture_features` reusam (DRY) |
| TEST-M1-01 | Teste de banda dava falso-verde por `unwrap_or(0.0)` | tests | `rms()` retorna `Option`; teste assere ambos RMS > 0 antes de comparar |
| TEST-M1-02 | Branch "0 após transcrição" inalcançável em `run_baseline.py` | tests | Branch morto removido; EC-5 = manifesto vazio (testado com `match=`) |
| EVID-01 | Report do baseline sem bloco de proveniência que `[MEDIDO]` exige | evidence | `render_report` ganhou `provenance=` (comando/hardware/seed/n_boot); report regenerado |
| EVID-02 | Soak ≥ 10 min (RNF-04) não rodado, mas "17,81× sustentado" exibido como métrica | evidence | Relabel: "janela curta (proxy)"; RNF-04 e RNF-05 marcados `[DESCONHECIDO — não executado]` |
| EVID-03 | 17,81× medido sem carga concorrente (RNF-05) sem caveat inline | evidence | Caveat "sem carga concorrente" inline na tabela de medição |

## MEDIUM — divergências de escopo aceitas (documentadas, mapeadas a riscos)

| # | Achado | Risco pré-aceito | Por que aceito |
|---|---|---|---|
| CV-1 | Baseline: 1 modelo (whisper-base), não 3 (TAGARELA+Moonshine+large-v3) | R1 (Alta) | Compute do ambiente; número real e rotulado entregue; TAGARELA (2,3 GB) já cacheado → follow-up de M1 |
| CV-2 | Augmentação não aplicada ao baseline (minds14 é 8 kHz nativo) | — | Tecnicamente mais forte (canal real > proxy sintético); a-law validado à parte por T2.1 |
| CV-3 | Test set pt-PT, não pt-BR "recorte regional" | R4 (domain gap) | pt-BR definitivo depende de corpus consentido (LGPD, fora de escopo); caveat explícito, sem pseudo-label |

## LOW — corrigidos ou aceitos

- TEST-M1-04 (IC mais largo p/ N pequeno não asserido) → **corrigido** (`test_bootstrap_ci_wider_for_smaller_n`).
- TEST-M1-05 (negative Python tests sem `match=`) → **corrigido** (3 testes com `match=`).
- TEST-M1-06 (temp filenames fixos) → **corrigido** (`tmp_unique` com `process::id()`).
- CV-4 / normalizador: "numerais por extenso" no docstring sem implementação → **corrigido** (docstring alinhado; numeral deferido por YAGNI).
- EVID-04 ("domínio exato" exagera) → **corrigido** (wording "domínio próximo, com gaps explícitos").
- EVID-05 (IC largo sem framing de risco 1) → **corrigido** (bloco de framing no report).
- F5 (ThermalRatio unit struct — nit), CV-5 (guard defensivo), TEST-M1-03 (resolvido por W1), EVID-06 (baseline nativo — traceabilidade) → aceitos/resolvidos.

## Cross-validation summary

- **tasks: 6** · full: 5 (T1.1, T1.2, T1.3, T2.1, T3.1) · partial: 1 (T4.1 — baseline scope) · missing: 0 · diverged: 1 (T4.1)
- **Goal metric ACHIEVED:** `cargo test --workspace` verde (43 testes) + `knowledge-base/measurements/m1-baseline-report.md` com WER real `73,0% [IC95: 49,8%–104,6%]` + proveniência.

## Quality gates summary

- cargo test --workspace: PASS (43 testes) · cargo clippy --all-targets -D warnings: PASS (0 warnings)
- pytest scripts/tests/: PASS (15 testes)
- code-quality: PASS_WITH_CAVEATS (D2-Rust N/A por compilador; cargo-udeps allowlisted, mitigado por clippy+machete)
- Wiring triad: 3 medidores (RtfxMeter/LatencyHistogram/ThermalRatio) + HarnessError com triad completo, comprovado por execução real; SampleCounter removido

## Spawned agents (audit trail)

- `agents/review-m1-measurement-harness-2026-07-24/findings/{architecture,tests,wiring,evaluation}.md`

## Handoff decision

**READY_TO_MERGE** — zero BLOCKER; o HIGH e os MEDIUM de defeito corrigidos; divergências de escopo documentadas e mapeadas a R1/R4/R5. Segue para `/release`.

Follow-ups de M1 (rastreados, não bloqueantes): baseline dos 3 modelos (TAGARELA cacheado), soak real de ≥ 10 min sob carga (RNF-04/05), test set pt-BR consentido, numeral-por-extenso no normalizador.
