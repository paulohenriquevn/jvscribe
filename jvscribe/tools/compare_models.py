#!/usr/bin/env python3
"""Compara dois modelos no MESMO conjunto, com a MESMA régua de normalização.

Existe porque "qual modelo é melhor" foi decidido por nome mais de uma vez neste projeto —
"final", "leve", "SOTA" — e nome não é evidência. A saída traz WER, CER e o intervalo de
confiança por bootstrap, para que a comparação diga se a diferença é real ou ruído.

Uso:
    python3 jvscribe/tools/compare_models.py \\
        --refs refs.tsv --hyps-a dirA --hyps-b dirB --label-a "small 27MB" --label-b "medium 68MB"

Formato de `refs.tsv`: `<id>\\t<transcrição de referência>` por linha, onde `<id>` casa com o
nome do `.txt` produzido em cada diretório de hipótese.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_normalize_ptbr import normalize_for_wer_compare  # noqa: E402
from wer_core import word_edit_distance  # noqa: E402


def _carregar(refs_path: Path, hyps_dir: Path) -> list[tuple[str, str]]:
    """Devolve `[(ref, hyp)]` só dos ids presentes nos DOIS lados."""
    pares = []
    for linha in refs_path.read_text(encoding="utf-8").splitlines():
        if "\t" not in linha:
            continue
        uid, ref = linha.split("\t", 1)
        hyp_file = hyps_dir / f"{uid}.txt"
        if hyp_file.exists():
            pares.append((ref, hyp_file.read_text(encoding="utf-8").strip()))
    return pares


def _wer_cer(pares: list[tuple[str, str]]) -> tuple[float, float, int, int]:
    """WER e CER agregados, usando a régua de COMPARAÇÃO (remove acento)."""
    err_w = tot_w = err_c = tot_c = 0
    for ref, hyp in pares:
        r = normalize_for_wer_compare(ref).split()
        h = normalize_for_wer_compare(hyp).split()
        err_w += word_edit_distance(r, h)
        tot_w += len(r)
        rc, hc = list("".join(r)), list("".join(h))
        err_c += word_edit_distance(rc, hc)
        tot_c += len(rc)
    return (
        100.0 * err_w / max(tot_w, 1),
        100.0 * err_c / max(tot_c, 1),
        tot_w,
        len(pares),
    )


def _bootstrap_ic(pares: list[tuple[str, str]], n: int = 1000, seed: int = 42) -> tuple[float, float]:
    """IC95% do WER por bootstrap sobre as utterances.

    Sem intervalo, uma diferença de 1 pp entre modelos pode ser ruído amostral — e o projeto
    já registrou essa lição (`ROADMAP.md` M1, risco 1: 20 min de áudio têm IC largo).
    """
    rng = random.Random(seed)
    amostras = []
    for _ in range(n):
        sub = [pares[rng.randrange(len(pares))] for _ in range(len(pares))]
        amostras.append(_wer_cer(sub)[0])
    amostras.sort()
    return amostras[int(0.025 * n)], amostras[int(0.975 * n)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refs", type=Path, required=True)
    ap.add_argument("--hyps-a", type=Path, required=True)
    ap.add_argument("--hyps-b", type=Path, required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--bootstrap", type=int, default=1000)
    a = ap.parse_args()

    resultados = []
    for label, d in ((a.label_a, a.hyps_a), (a.label_b, a.hyps_b)):
        pares = _carregar(a.refs, d)
        if not pares:
            print(f"  {label}: nenhuma hipótese pareada em {d}", file=sys.stderr)
            return 1
        wer, cer, palavras, n = _wer_cer(pares)
        lo, hi = _bootstrap_ic(pares, a.bootstrap)
        resultados.append((label, wer, cer, n, palavras, lo, hi))
        print(
            f"  {label:<22} WER {wer:5.2f}%  [IC95 {lo:5.2f}–{hi:5.2f}]  "
            f"CER {cer:5.2f}%  ({n} utts, {palavras} palavras)"
        )

    (la, wa, _, _, _, loa, hia), (lb, wb, _, _, _, lob, hib) = resultados
    delta = wb - wa
    sobrepoe = not (hia < lob or hib < loa)
    print()
    print(f"  delta (B − A): {delta:+.2f} pp de WER")
    if sobrepoe:
        print("  ⚠ Os intervalos de confiança SE SOBREPÕEM — a diferença não é conclusiva")
        print("    neste tamanho de amostra. Escolher pelo WER aqui seria escolher por ruído.")
    else:
        melhor = la if wa < wb else lb
        print(f"  ✓ Separação estatística limpa — {melhor} é melhor neste conjunto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
