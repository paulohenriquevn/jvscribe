# Baseline Zipformer-CTC small (SEM cabeça de fonema) — recogs

- **`recogs-clean-avg10.txt`** — o baseline REAL: FLEURS test wideband limpo,
  `ctc-greedy-search` avg=10 → **WER 29,97%**. É este o baseline da ablação de fonema
  (`training/results/m4-phoneme-ablation-results.md`) e do bootstrap pareado.
  Re-decodado em 2026-07-27 porque os recogs originais do small foram sobrescritos.

- **`*.STALE-telephone-38pct-DO-NOT-USE`** — recogs do experimento TELEFÔNICO (8 kHz,
  banda 300-3400 + G.711), **WER 38,60%**, segmentação diferente (chaves `...-0-0`).
  NÃO usar como baseline: infla o delta da ablação (~10pp). Mantidos só como registro
  do experimento telefônico; renomeados para eliminar o footgun de nome-default.
