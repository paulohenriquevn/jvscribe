"""Prova (parcial) de ausência de vazamento de locutor entre os splits do CORAA-v1.1.

Invariante do projeto / falácia §3 #10: vazamento de locutor entre train e test invalida
todo resultado a jusante. Esta é a PROVA POR SCRIPT exigida — não a afirmação do paper.

O metadado do CORAA NÃO traz coluna speaker_id. Mas o `file_path` de cada segmento
codifica uma chave de locutor/gravação em 3 dos 5 subcorpora:

  - C-ORAL-BRASIL I : `.../CORAL/{idx}_CO_{spk}.wav`            → locutor {spk}
  - NURC-Recife     : `.../NURC_RE_{T}/NURC_RE_{T}_{N}/…_.wav` → entrevista NURC_RE_{T}_{N}
                                                                 (1 informante por sessão)
  - TEDx Talks      : `.../{videoID}-{seg}.wav`                → palestra {videoID}
                                                                 (1 palestrante por talk)
  - ALIP / SP2010   : `.../{idx}_alip_.wav`, `{idx}_sp_.wav`   → SEM chave → NÃO-VERIFICÁVEL

Cobertura da prova (horas de train, paper Tab.4 [LITERATURA]):
  verificável = CORAL 6,54 + NURC 137,08 + TEDx 68,67 = 212,3h de 273,5h (≈78%).
  não-verificável = ALIP 33,4 + SP2010 27,83 = 61,2h (≈22%).

Saída: exit 0 se NENHUM overlap nas chaves verificáveis; exit 1 se qualquer chave
aparece em mais de um split (vazamento). Segmentos sem chave são contados e reportados
como não-verificáveis — o script NUNCA afirma disjunção sobre ALIP/SP2010.

Uso:
  python3 coraa_speaker_overlap.py --meta-dir /workspace/coraa_work
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

VERIFIABLE = ("CORAL", "NURC", "TEDx")


def speaker_key(dataset: str, file_path: str):
    """Retorna (corpus, chave) ou None quando o path não codifica locutor."""
    parts = file_path.split("/")
    name = os.path.splitext(parts[-1])[0]
    if dataset == "C-ORAL-BRASIL I":
        toks = name.split("_")
        return ("CORAL", toks[-1]) if len(toks) >= 3 and toks[-1] else None
    if dataset == "NURC-Recife":
        return ("NURC", parts[-2]) if len(parts) >= 2 else None
    if dataset == "TEDx Talks":
        return ("TEDx", re.sub(r"-\d+$", "", name))
    return None  # ALIP, SP2010 — sem chave de locutor no path


def load_keys(meta_dir: str, split: str):
    keys = defaultdict(set)
    unverifiable = defaultdict(int)
    path = os.path.join(meta_dir, f"metadata_{split}_final.csv")
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            k = speaker_key(row["dataset"], row["file_path"])
            if k is None:
                unverifiable[row["dataset"]] += 1
            else:
                keys[k[0]].add(k[1])
    return keys, dict(unverifiable)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta-dir", required=True,
                    help="dir com metadata_{train,dev,test}_final.csv")
    ap.add_argument("--splits", nargs="+", default=["train", "dev", "test"])
    args = ap.parse_args()

    # Fail-fast COM instrução na fronteira: sem isto o script morre no traceback cru da lib
    # (`FileNotFoundError`/`LibsndfileError`), que não diz ao operador o que buscar.
    # `error-handling.md` § 2: valide na entrada, falhe claro. Achado no live test 2026-07-31.
    import pathlib as _p
    if not _p.Path(args.meta_dir).exists():
        raise SystemExit(
            f"diretório de metadados do CORAA não encontrado: {args.meta_dir}\n"
            "Baixe o CORAA-v1.1 e aponte --meta-dir para a pasta com os metadata_*.csv."
        )

    per_split = {}
    for split in args.splits:
        keys, unverif = load_keys(args.meta_dir, split)
        per_split[split] = keys
        summary = ", ".join(f"{c}={len(keys.get(c, set()))}" for c in VERIFIABLE)
        print(f"[{split}] chaves verificáveis: {summary}")
        print(f"         não-verificável (sem chave no path): {unverif}")

    leaks = 0
    print("\n=== overlap de locutor/gravação entre splits (chaves verificáveis) ===")
    pairs = [(a, b) for i, a in enumerate(args.splits) for b in args.splits[i + 1:]]
    for a, b in pairs:
        for corpus in VERIFIABLE:
            A = per_split[a].get(corpus, set())
            B = per_split[b].get(corpus, set())
            inter = A & B
            if inter:
                leaks += 1
                print(f"  {corpus:6s} {a} ∩ {b}: {len(inter)} em comum "
                      f"← VAZAMENTO {sorted(inter)[:5]}")
            else:
                print(f"  {corpus:6s} {a} ∩ {b}: 0  ✓ disjunto "
                      f"(|{a}|={len(A)}, |{b}|={len(B)})")

    print()
    if leaks:
        print(f"FALHA: {leaks} par(es) subcorpus×split com vazamento de locutor.")
        sys.exit(1)
    print("OK: nenhuma chave de locutor/gravação compartilhada nas 3 fontes verificáveis "
          "(CORAL, NURC, TEDx ≈78% das horas de train). ALIP+SP2010 (≈22%) permanecem "
          "NÃO-VERIFICÁVEIS pelo metadado — reportar como caveat, não como disjunção provada.")
    sys.exit(0)


if __name__ == "__main__":
    main()
