# Edge Case Review — m1-measurement-harness (plan)

Date: 2026-07-24
Tasks analyzed: 6 (T1.1, T1.2, T1.3, T2.1, T3.1, T4.1)
Cases found: 7 (EDGE: 4, NEGATIVE: 3 | MUST FIX: 0, SHOULD TEST: 5, DOCUMENT: 2)

O plano já traz edge + negative por task no TDD. Nenhum MUST FIX: o risco de crash mais provável (percentil de histograma vazio, T1.2) **não existe** porque `nearest_rank_percentile` (`crates/macaw-audio/src/metrics.rs:37-44`, que o `LatencyHistogram` reusa por DRY) já protege o slice vazio retornando 0. Os achados abaixo endurecem os boundaries.

## MUST FIX

Nenhum.

## SHOULD TEST

### EC-1: `warmup_iters >= total_iters` deixa a medição sem nenhuma iteração
- **Affected task:** T1.1
- **Kind:** NEGATIVE (config inválida)
- **Suggested test:** `test_rtfx_warmup_ge_total_is_typed_error` — configurar `warmup_iters = total_iters` e asserir `HarnessError` tipado (não RTFx de amostra vazia / NaN). O plano já declara o invariante "warmup_iters < total_iters" mas sem teste que o prove.

### EC-2: percentil de histograma vazio retorna 0 ms — lê-se como "instantâneo", não "sem dados"
- **Affected task:** T1.2
- **Kind:** EDGE (extremo válido — nenhuma amostra ainda)
- **Suggested test:** `test_latency_percentiles_empty_is_unambiguous` — sem amostras, asserir que a API sinaliza "sem dados" (retornar `Option::None` OU um relatório que marca `n=0`), não `(0,0,0)` que um leitor confunde com latência zero. Correção ≤ 1 linha: `if self.is_empty() { return None }` no `percentiles()`.

### EC-3: `ThermalRatio` com RTFx(min1) = 0 → divisão por zero
- **Affected task:** T1.3
- **Kind:** NEGATIVE (janela degenerada)
- **Suggested test:** `test_thermal_ratio_zero_baseline_is_typed_error` — janela min1 com RTFx 0 → `HarnessError` (não `inf`/`NaN`). Guard: `if min1 == 0.0 { return Err(...) }`.

### EC-4: bootstrap com N=1 utterance → IC degenerado (low = high = WER)
- **Affected task:** T3.1
- **Kind:** EDGE (menor test set válido)
- **Suggested test:** `test_bootstrap_ci_single_utterance` — com 1 utterance e seed fixa, asserir que o IC é degenerado (`IC_low == IC_high == WER`) e **não** crasha; o relatório deve deixar claro que N=1 dá IC sem informação (o ponto do risco 1 em extremo).

### EC-5: test set vazio (todas as utterances falharam na augmentação) → relatório sobre zero resultados
- **Affected task:** T4.1
- **Kind:** NEGATIVE (resultado vazio)
- **Suggested test:** `test_baseline_empty_testset_is_error` — 0 utterances válidas → `run_baseline.py` falha fast com mensagem clara ("0 utterances mensuráveis"), não gera relatório com divisão por zero nem WER falso.

## DOCUMENT

### EC-6: WAV vazio/silêncio no round-trip a-law
- **Affected task:** T2.1
- **Kind:** EDGE (extremo válido degenerado)
- **Accepted risk:** `sox` processa silêncio/entrada de duração mínima sem erro; a cadeia é robusta a isso. Não vale um teste dedicado — o `test_augment_output_is_8khz_mono` já cobre a propriedade estrutural, e silêncio é um caso degenerado sem valor de negócio distinto.

### EC-7: soak insuficiente (< 30 min) num ambiente que não sustenta
- **Affected task:** T1.3
- **Kind:** NEGATIVE (recurso insuficiente)
- **Accepted risk:** Já coberto pelo R5 do plano — se o ambiente não sustentar 10-30 min, a razão térmica é reportada como `[DESCONHECIDO]` honesto, nunca um número frágil. O `[DESCONHECIDO]` é o comportamento correto (`asr-evidence-discipline.md` § 1), não um bug a corrigir.

## Summary

| Task | EDGE | NEGATIVE | MUST FIX | SHOULD TEST | DOCUMENT |
|------|------|----------|----------|-------------|----------|
| T1.1 | 0 | 1 | 0 | 1 | 0 |
| T1.2 | 1 | 0 | 0 | 1 | 0 |
| T1.3 | 0 | 1 | 0 | 1 | 1 |
| T2.1 | 1 | 0 | 0 | 0 | 1 |
| T3.1 | 1 | 0 | 0 | 1 | 0 |
| T4.1 | 0 | 1 | 0 | 1 | 0 |

**Coverage check:** cada task com boundary de input tem edge + negative considerados. Os 5 SHOULD TEST são endurecimentos cheap (1 teste cada, ≤ 1 linha de guard).

**Verdict:** PLAN OK (nenhum MUST FIX; 5 SHOULD TEST recomendados para absorção no TDD das tasks)
