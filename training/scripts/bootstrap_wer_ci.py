#!/usr/bin/env python3
"""IC bootstrap pareado da diferença de WER entre dois recogs do icefall.

Fecha a ablação de M4 fase 3 (§ 3 falácia #12: sem IC, um ponto de WER não sustenta
conclusão). Bootstrap por UTTERANCE (reamostra as utterances com reposição) sobre o
MESMO test set decodado por dois modelos — pareado, então o IC é da diferença real,
não da soma de duas incertezas independentes. Reusa o Levenshtein e o parser de
recogs já existentes (Regra 9). Determinístico: seed fixo (reprodutível).

Uso: python3 bootstrap_wer_ci.py <baseline_recogs> <candidato_recogs> [--boot 10000] [--seed 42]
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cer_from_recogs import parse_recogs  # noqa: E402
from wer_core import word_edit_distance  # noqa: E402


def per_utterance_errors(baseline_text: str, cand_text: str) -> list[tuple[int, int, int]]:
    """[(werr_base, werr_cand, n_ref_words)] por utterance, sobre o MESMO test set.

    Falha alto se os conjuntos de utterances divergirem (test sets diferentes → o
    pareamento seria inválido) ou se a referência de uma utterance diferir entre os
    dois arquivos (não é o mesmo alvo → comparação sem sentido).
    """
    base = parse_recogs(baseline_text)
    cand = parse_recogs(cand_text)
    if set(base) != set(cand):
        raise ValueError(f"conjuntos de utterances diferem ({len(set(base) ^ set(cand))} sem par)")
    rows = []
    for utt, (ref_b, hyp_b) in base.items():
        ref_c, hyp_c = cand[utt]
        if ref_b != ref_c:
            raise ValueError(f"referência difere na utterance {utt} — não é o mesmo test set")
        rows.append((word_edit_distance(ref_b, hyp_b), word_edit_distance(ref_c, hyp_c), len(ref_b)))
    return rows


def _wer_pair(rows: list[tuple[int, int, int]]) -> tuple[float, float]:
    eb = sum(r[0] for r in rows)
    ec = sum(r[1] for r in rows)
    w = sum(r[2] for r in rows) or 1
    return 100.0 * eb / w, 100.0 * ec / w


def paired_bootstrap(
    rows: list[tuple[int, int, int]], n_boot: int = 10000, seed: int = 42, dod_threshold: float = 3.0
) -> dict:
    """IC 95% (percentil) da diferença de WER e da melhora relativa, por reamostragem
    de utterances com reposição. `rows` = saída de per_utterance_errors. Emite também
    P(melhora>0) (significância) e P(melhora>=dod_threshold) (confiança de bater a DoD)
    da MESMA distribuição bootstrap — os números do artefato de decisão saem deste
    comando, não de um snippet à parte (proveniência fechada; review M4)."""
    if not rows:
        raise ValueError("nenhuma utterance pareada — recogs vazios ou test sets disjuntos?")
    wer_base, wer_cand = _wer_pair(rows)
    abs_diff = wer_base - wer_cand                      # p.p. que o candidato reduz
    rel_impr = 100.0 * abs_diff / wer_base if wer_base else 0.0
    rng = random.Random(seed)
    n = len(rows)
    diffs, rels = [], []
    n_gt0 = n_ge_thr = 0
    for _ in range(n_boot):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        wb, wc = _wer_pair(sample)
        diffs.append(wb - wc)
        rel = 100.0 * (wb - wc) / wb if wb else 0.0
        rels.append(rel)
        n_gt0 += rel > 0.0
        n_ge_thr += rel >= dod_threshold
    diffs.sort()
    rels.sort()
    lo, hi = int(0.025 * n_boot), int(0.975 * n_boot)
    return {
        "wer_base": wer_base, "wer_cand": wer_cand,
        "abs_diff_pp": abs_diff, "abs_ci95": (diffs[lo], diffs[hi]),
        "rel_impr_pct": rel_impr, "rel_ci95": (rels[lo], rels[hi]),
        "p_gt0_pct": 100.0 * n_gt0 / n_boot,
        "dod_threshold": dod_threshold, "p_ge_thr_pct": 100.0 * n_ge_thr / n_boot,
        "n_utt": n, "n_boot": n_boot, "seed": seed,
    }


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
