"""Decodifica um checkpoint Zipformer-CTC e mede WER (M4 — piloto). Roda NA GPU.

CTC greedy search (auto-suficiente — só modelo + BPE, sem LM/léxico; Blueprint Q8).
WER word-level via jiwer. O WER é sobre FLEURS pt_br (banda larga) — NÃO o test set
8 kHz de call center do produto (§ 3 #6): prova que o pipeline treina e produz WER,
não o WER-alvo. Reusa o CtcModel de train_ctc.

Uso: python3 decode_ctc.py --exp exp --split validation
"""

from __future__ import annotations

import argparse

import jiwer
import sentencepiece as spm
import torch
from lhotse import CutSet

from train_ctc import CtcModel, make_loader


def ctc_greedy(log_probs, lens, sp):
    """(N,T,V) log-probs → texto (colapsa repetições + remove blank=0)."""
    ids = log_probs.argmax(-1)  # (N,T)
    out = []
    for i in range(ids.size(0)):
        seq = ids[i, : lens[i]].tolist()
        toks, prev = [], -1
        for t in seq:
            if t != prev and t != 0:
                toks.append(t)
            prev = t
        out.append(sp.decode(toks))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp")
    ap.add_argument("--split", default="validation")
    ap.add_argument("--data", default="data")
    args = ap.parse_args()
    dev = torch.device("cuda")

    sp = spm.SentencePieceProcessor(); sp.load(f"{args.data}/bpe_256.model")
    ckpt = torch.load(f"{args.exp}/model.pt", map_location=dev)
    model = CtcModel(ckpt["vocab"], ckpt["num_phones"]).to(dev).eval()
    model.load_state_dict(ckpt["model"])

    cuts = CutSet.from_file(f"{args.data}/fleurs_cuts_{args.split}.jsonl.gz")
    cuts = cuts.trim_to_supervisions(keep_overlapping=False).to_eager()
    loader = make_loader(cuts, sp, None, max_dur=200)

    refs, hyps = [], []
    with torch.no_grad():
        for batch in loader:
            feats = batch["inputs"].to(dev)
            flens = batch["supervisions"]["num_frames"].to(dev)
            texts = batch["supervisions"]["text"]
            ctc_out, _, enc_lens = model(feats, flens)
            hyps += ctc_greedy(ctc_out, enc_lens.cpu(), sp)
            refs += list(texts)
    wer = jiwer.wer(refs, hyps)
    print(f"[decode] {args.exp} split={args.split} n={len(refs)} WER={wer*100:.2f}%")
    print(f"[decode] ex ref: {refs[0][:60]!r}")
    print(f"[decode] ex hyp: {hyps[0][:60]!r}")


if __name__ == "__main__":
    main()
