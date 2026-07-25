"""Gera alvos fonéticos para a cabeça auxiliar (M4 — piloto). Roda NA INSTÂNCIA.

A supervisão fonética que o DoD de M4 pede NÃO existe na recipe (Blueprint Q2). Aqui
construímos os alvos: G2P PT-BR (phonemizer+espeak-ng, medido em Q-08) → sequência de
fonemas por utterance → ids num vocabulário de fonemas. Reprodutível, versionado.

Uso: python3 gen_phonemes.py --data data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lhotse import CutSet
from phonemizer import phonemize
from phonemizer.separator import Separator


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--split", default="validation")
    args = ap.parse_args()
    data = Path(args.data)

    cuts = CutSet.from_file(str(data / f"fleurs_cuts_{args.split}.jsonl.gz"))
    texts = list({s.text for c in cuts for s in c.supervisions})

    # G2P em lote (phonemizer, backend espeak, pt-br) — determinístico (Q-08)
    phon = phonemize(texts, language="pt-br", backend="espeak",
                     separator=Separator(phone=" ", word="|"), strip=True, njobs=1)

    # vocabulário de fonemas: 0=blank, 1=unk, depois os símbolos observados
    vocab = {"<blk>": 0, "<unk>": 1}
    tgt_map = {}
    for text, ph in zip(texts, phon):
        ids = []
        for sym in ph.replace("|", " ").split():
            if sym not in vocab:
                vocab[sym] = len(vocab)
            ids.append(vocab[sym])
        tgt_map[text] = ids

    out = {"map": tgt_map, "num_phones": len(vocab), "vocab": vocab}
    (data / "phoneme_targets.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"[phonemes] {len(texts)} textos, {len(vocab)} fonemas distintos → phoneme_targets.json")


if __name__ == "__main__":
    main()
