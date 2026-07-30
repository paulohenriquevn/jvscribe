"""Gera alvos fonéticos para a cabeça auxiliar do Zipformer-CTC (M4 fase 3 — task #20).

A supervisão fonética que o PRD §8.1 exige ("camada intermediária do encoder,
agnóstica ao decoder") NÃO existe pronta na recipe do icefall — este script constrói
os alvos: G2P PT-BR (phonemizer+espeak-ng, [FONTE-REPO] cobertura/determinismo
medidos em Q-08 do blueprint m4-pilot) → sequência de fonemas por utterance →
vocabulário de fonemas. G2P é usado APENAS offline no treino (phonemizer é GPLv3 —
nunca entra no runtime de produção, per m4-pilot-blueprint.md).

Difere do smoke `training/smoke/gen_phonemes.py` (que só cobria
fleurs_cuts_validation.jsonl.gz) em cobrir os textos REAIS usados no treino real:
train (MLS-PT, cv-pt_cuts_train.jsonl.gz) + dev (cv-pt_cuts_dev.jsonl.gz, usado pelo
compute_validation_loss do icefall a cada valid_interval). Sem isso, textos de treino
cairiam no fallback <unk> e a cabeça auxiliar aprenderia ruído.

Roda NA INSTÂNCIA, em egs/commonvoice/ASR (onde data/pt/*.jsonl.gz existem).

Uso: python3 gen_phonemes.py --data data/pt --splits train,dev
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_targets(texts_list: list[str], phon: list[str]) -> dict:
    """Constrói vocab de fonemas + mapa texto→ids a partir das saídas do G2P.

    Lógica pura (sem I/O nem phonemizer) — o núcleo testável. Convenção CTC do
    icefall: 0=<blk>, 1=<unk>; símbolos ganham id na ordem de aparição. Falha alto
    (`ValueError`) se G2P e textos ficarem desemparelhados (não vira alvo silencioso).
    """
    if len(phon) != len(texts_list):
        raise ValueError(f"G2P devolveu {len(phon)} saídas para {len(texts_list)} entradas")
    vocab = {"<blk>": 0, "<unk>": 1}
    tgt_map: dict[str, list[int]] = {}
    empty_count = 0
    for text, ph in zip(texts_list, phon):
        syms = ph.replace("|", " ").split()
        if not syms:
            empty_count += 1
            continue
        ids = []
        for sym in syms:
            if sym not in vocab:
                vocab[sym] = len(vocab)
            ids.append(vocab[sym])
        tgt_map[text] = ids
    return {"map": tgt_map, "num_phones": len(vocab), "vocab": vocab, "n_empty_g2p": empty_count}


def main():
    # Imports pesados (GPLv3, só treino offline) locais ao main → build_targets testável sem eles.
    from lhotse import CutSet
    from phonemizer import phonemize
    from phonemizer.separator import Separator

    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/pt", help="dir com cv-pt_cuts_{split}.jsonl.gz")
    ap.add_argument("--splits", default="train,dev", help="splits a cobrir, vírgula-separado")
    ap.add_argument("--out", default=None, help="default: {data}/phoneme_targets.json")
    args = ap.parse_args()
    data = Path(args.data)
    out_path = Path(args.out) if args.out else data / "phoneme_targets.json"

    texts: set[str] = set()
    for split in args.splits.split(","):
        cuts_path = data / f"cv-pt_cuts_{split}.jsonl.gz"
        if not cuts_path.exists():
            sys.exit(f"FALHA: {cuts_path} não existe — split errado ou data-dir errado?")
        cuts = CutSet.from_file(str(cuts_path))
        n_before = len(texts)
        for c in cuts:
            for s in c.supervisions:
                if s.text:
                    texts.add(s.text)
        print(f"[phonemes] {split}: +{len(texts) - n_before} textos únicos "
              f"(total acumulado {len(texts)})", flush=True)

    texts_list = sorted(texts)
    if not texts_list:
        sys.exit("FALHA: nenhum texto coletado — cuts vazios?")

    # G2P em lote (phonemizer, backend espeak-ng, pt-br) — determinístico (Q-08)
    phon = phonemize(
        texts_list, language="pt-br", backend="espeak",
        separator=Separator(phone=" ", word="|"), strip=True, njobs=4,
    )
    try:
        out = build_targets(texts_list, phon)
    except ValueError as e:
        sys.exit(f"FALHA: {e}")

    out.update({"splits_covered": args.splits, "n_texts": len(texts_list)})
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"[phonemes] {len(out['map'])}/{len(texts_list)} textos mapeados, "
          f"{out['num_phones']} fonemas distintos, {out['n_empty_g2p']} G2P vazios → {out_path}",
          flush=True)


if __name__ == "__main__":
    main()
