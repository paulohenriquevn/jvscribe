#!/usr/bin/env python3
"""CER e WER a partir de um `recogs-*.txt` do icefall.

O WER pune deslize de 1-2 chars como palavra inteira errada; o CER mede a distância
real de caractere. Uso: python3 jvscribe/eval/cer_from_recogs.py <recogs.txt>

CLI fino: a lógica vive em `common/metrics.py` — este arquivo só faz argumento e
impressão. A separação existe porque a métrica tem 7 consumidores e o CLI, nenhum.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
from metrics import score_recogs  # noqa: E402

from pathlib import Path  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("recogs", type=Path, help="arquivo recogs-*.txt produzido pelo icefall")
    path = ap.parse_args().recogs
    if not path.exists():
        raise SystemExit(f"recogs ausente: {path}")
    try:
        r = score_recogs(path.read_text(encoding="utf-8"))
    except (ValueError, SyntaxError) as e:
        raise SystemExit(str(e)) from e
    print(f"[MEDIDO] {path.name}")
    print(f"  utterances={r['utterances']}  palavras={r['words']}  caracteres={r['chars']}")
    print(f"  WER = {r['wer']:.2f}%  ({r['werr']}/{r['words']})")
    print(f"  CER = {r['cer']:.2f}%  ({r['cerr']}/{r['chars']})")


if __name__ == "__main__":
    main()
