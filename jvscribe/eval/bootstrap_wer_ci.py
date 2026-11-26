#!/usr/bin/env python3
"""IC bootstrap PAREADO da diferença de WER entre dois recogs do icefall.

Sem IC, um ponto de WER não sustenta conclusão (asr-evidence-discipline § 3 #12).
Uso: python3 jvscribe/eval/bootstrap_wer_ci.py <base> <cand> [--boot N] [--seed N]

CLI fino: a lógica vive em `common/metrics.py` — este arquivo só faz argumento e
impressão. A separação existe porque a métrica tem 7 consumidores e o CLI, nenhum.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
import argparse  # noqa: E402
from pathlib import Path  # noqa: E402

from metrics import paired_bootstrap, per_utterance_errors  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    for p in (args.baseline, args.candidate):
        if not Path(p).exists():
            raise SystemExit(f"recogs ausente: {p}")
    rows = per_utterance_errors(
        Path(args.baseline).read_text(encoding="utf-8"), Path(args.candidate).read_text(encoding="utf-8")
    )
    r = paired_bootstrap(rows, n_boot=args.boot, seed=args.seed)
    print(f"[MEDIDO] bootstrap pareado (n={r['n_utt']} utt, B={r['n_boot']}, seed={r['seed']})")
    print(f"  WER baseline={r['wer_base']:.2f}%  candidato={r['wer_cand']:.2f}%")
    print(f"  Δ absoluto = {r['abs_diff_pp']:.2f} p.p.  IC95% [{r['abs_ci95'][0]:.2f}, {r['abs_ci95'][1]:.2f}]")
    print(f"  Melhora relativa = {r['rel_impr_pct']:.2f}%  IC95% [{r['rel_ci95'][0]:.2f}, {r['rel_ci95'][1]:.2f}]")
    print(f"  P(melhora>0) = {r['p_gt0_pct']:.1f}%   P(melhora>={r['dod_threshold']:.0f}%) = {r['p_ge_thr_pct']:.1f}%")


if __name__ == "__main__":
    main()
