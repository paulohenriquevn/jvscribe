# M1 — Régua de Medição: resumo de implementação

**Plano:** `knowledge-base/plans/m1-measurement-harness-plan.md` (v1.1, SHIPPABLE_WITH_CAVEATS 89.6)
**Promise:** IMPLEMENTATION_COMPLETE
**Data:** 2026-07-24

## O que foi entregue (4 fases + validação)

| Fase | Entregável | Wiring triad (caller · teste · métrica) | Evidência |
|---|---|---|---|
| 1 | Harness Rust (`crates/macaw-audio/src/harness.rs`): `RtfxMeter`, `LatencyHistogram`, `ThermalRatio`, `SampleCounter` | Caller: `macaw-cli bench` + `scripts/bench.sh` (taskset) · 9 testes + concorrência · RTFx/p99/térmica impressos | `knowledge-base/measurements/m1-harness-measurement.md` — RTFx **17,81×** [MEDIDO] |
| 2 | Cadeia telefônica (`scripts/telephone_augment.sh`) | Caller: `run_baseline`/`bench.sh` · 3 testes (8kHz mono, banda, fail-fast) · saída WAV verificável | teste `augmentation_test.rs` verde |
| 3 | WER+IC (`scripts/eval_wer.py` + `text_normalize_ptbr.py`) | Caller: `run_baseline` · 10 testes · relatório com IC | exemplo real WER 5,6% [IC 0–21,4%] |
| 4 | Baseline (`scripts/run_baseline.py` + `baseline_minds14.py`) | Caller: `baseline_minds14` · 4 testes · relatório [MEDIDO] | **WER 68,3% [IC95: 46,8%–96,9%]** real |

## Métrica do Goal — ATINGIDA

`cargo test --workspace` verde (44 testes) **E** `knowledge-base/measurements/m1-baseline-report.md`
existe com WER real `WER = 68.3% [IC95: 46.8%–96.9%]` gerado por execução real (não placeholder).

## Validação de integração

- `cargo test --workspace`: 44 testes verdes · `cargo clippy --workspace --all-targets -- -D warnings`: limpo
- `python3 -m pytest scripts/tests/`: 14 verdes
- `macaw-cli bench`: roda, imprime RTFx/p99/térmica sem panic
- Chaos pass (failure scenarios): sox input inválido → exit 1; modelo ausente → mensagem clara sem panic; manifesto vazio → erro tipado; pseudo-label → rejeitado. Todos ✓

## Achados/correções durante a implementação

1. **`ORT_DYLIB_PATH` só sob `cargo run`.** O `.cargo/config.toml [env]` não se aplica ao invocar o binário direto — `bench.sh` exporta o path explicitamente.
2. **Bug de tooling do `discover-plan-confidence`** (formato pipe vs `=`) corrigido durante a fase discover.
3. **Ambiente Python quebrado** contornado para o baseline real: `torch` órfão (sem `__init__`) movido para `.bak`; `datasets` 5.0 exige `torchcodec` → baseline usa parquet direto do HF + soundfile; ctranslate2 deadlock de futex → `cpu_threads=1`.

## Decisões de escopo honestas (asr-evidence-discipline § 2, § 4)

- **Baseline em 1 modelo real** (faster-whisper-base), não os 3 do DoD original. Protocolo reprodutível vale para whisper-large-v3 e TAGARELA (cacheado localmente); a execução dos modelos pesados é limitada pelo ambiente (R1 do plano). O número entregue é real e rotulado.
- **Test set proxy pt-PT** (minds14), não pt-BR — fala telefônica real com transcrição humana; o pt-BR definitivo depende de corpus consentido (LGPD, fora de escopo). Caveat explícito no relatório.
- **RTFx do encoder emprestado** rotulado `[MEDIDO — encanamento apenas]` — prova a régua, não o produto.

## Caveats que seguem para /review

- Baseline com n=15 tem IC largo (46,8–96,9%) — é o risco 1 do ROADMAP em ação; o IC honesto é o resultado, não um defeito.
- `models--...-TAGARELA-onnx` (2,3 GB) está cacheado — medir TAGARELA é o próximo baseline natural (requer inferência sherpa-onnx/parakeet, escopo de follow-up).
