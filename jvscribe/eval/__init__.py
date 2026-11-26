"""Harness de medição de WER — o número, com a régua certa e o intervalo de confiança.

O que une: cada arquivo responde *"qual o WER neste recorte, e dá para concluir daí?"*. A
diferença entre eles é o **recorte**, nunca o método.

| recorte | arquivo |
|---|---|
| benchmark público (FLEURS, MINDS-14) | `baseline_fleurs_ptbr`, `baseline_minds14`, `run_baseline` |
| telefônico simulado (real-codec) | `measure_realcodec`, `make_telephone_test` |
| call center REAL 8 kHz | `measure_callcenter`, `make_callcenter_cuts` |
| comparação entre modelos | `compare_models`, `bootstrap_wer_ci`, `cer_from_recogs` |
| composição do erro | `analyze_error_composition`, `eval_runtime_wer` |

⚠️ Todos usam `common/text.normalize_for_wer_compare`. Três números deste projeto já foram
publicados com régua própria e ficaram incomparáveis com os demais — a régua não é escolha
de cada harness.
"""
