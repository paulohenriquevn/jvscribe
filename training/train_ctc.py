"""Treino Zipformer-CTC PT-BR + cabeça de fonema auxiliar (M4 — piloto). Roda NA GPU.

Reuso máximo (Regra 9): importa Zipformer2 + Conv2dSubsampling + ScaledAdam + Eden +
ScheduledFloat do icefall (os módulos pesados, testados pelos autores do Zipformer).
O mínimo próprio (rung 6): as 2 cabeças CTC (subword BPE + fonema), o loop de treino e
a loss — porque a supervisão FONÉTICA não existe na recipe (Blueprint M4 Q2: a recipe
só tem CTC de subword). CTC via `torch.nn.functional.ctc_loss` (não precisa de k2).

Ablação (a decisão do dono — construir a cabeça de fonema): `--use-phoneme 1` liga a
2ª cabeça; comparar WER com/sem responde "a supervisão fonética ajuda ≥ 3%?".

Uso: python3 train_ctc.py --exp exp --epochs N [--use-phoneme 0|1]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import sentencepiece as spm
import torch
import torch.nn as nn
import torch.nn.functional as F
from lhotse import CutSet
from lhotse.dataset import DynamicBucketingSampler, K2SpeechRecognitionDataset
from lhotse.dataset.input_strategies import PrecomputedFeatures
from torch.utils.data import DataLoader

# módulos do icefall (copiados p/ o cwd na instância)
from zipformer import Zipformer2
from subsampling import Conv2dSubsampling
from scaling import ScheduledFloat
from optim import Eden, ScaledAdam


def _t(s):  # "a,b,c" -> (a,b,c)
    return tuple(int(x) for x in str(s).split(","))


# ---- Config pequena p/ smoke (~10-20M) — derivada por escala da recipe (Blueprint Q1) ----
CFG = dict(
    feature_dim=80,
    downsampling_factor="1,2,4,8,4,2",
    num_encoder_layers="1,1,1,1,1,1",   # smoke: 1 layer/stack (recipe usa 2..5)
    encoder_dim="128,128,192,256,192,128",
    encoder_unmasked_dim="128,128,128,128,128,128",
    query_head_dim="24,24,24,24,24,24",
    pos_head_dim="4,4,4,4,4,4",
    value_head_dim="12,12,12,12,12,12",
    num_heads="4,4,4,8,4,4",
    feedforward_dim="384,384,512,768,512,384",
    cnn_module_kernel="31,31,15,15,15,31",
    pos_dim=48, causal=False, chunk_size="-1", left_context_frames="-1",
)


class CtcModel(nn.Module):
    """Conv2dSubsampling → Zipformer2 → cabeça CTC subword (+ cabeça de fonema opcional)."""

    def __init__(self, vocab_size: int, num_phones: int = 0):
        super().__init__()
        edim = _t(CFG["encoder_dim"])
        self.embed = Conv2dSubsampling(
            in_channels=CFG["feature_dim"], out_channels=edim[0],
            dropout=ScheduledFloat((0.0, 0.3), (20000.0, 0.1)),
        )
        self.encoder = Zipformer2(
            output_downsampling_factor=2,
            downsampling_factor=_t(CFG["downsampling_factor"]),
            num_encoder_layers=_t(CFG["num_encoder_layers"]),
            encoder_dim=edim, encoder_unmasked_dim=_t(CFG["encoder_unmasked_dim"]),
            query_head_dim=_t(CFG["query_head_dim"]), pos_head_dim=_t(CFG["pos_head_dim"]),
            value_head_dim=_t(CFG["value_head_dim"]), pos_dim=CFG["pos_dim"],
            num_heads=_t(CFG["num_heads"]), feedforward_dim=_t(CFG["feedforward_dim"]),
            cnn_module_kernel=_t(CFG["cnn_module_kernel"]),
            dropout=ScheduledFloat((0.0, 0.3), (20000.0, 0.1)),
            warmup_batches=4000.0, causal=False,
            chunk_size=_t(CFG["chunk_size"]), left_context_frames=_t(CFG["left_context_frames"]),
        )
        out_dim = max(edim)
        self.ctc = nn.Sequential(nn.Dropout(0.1), nn.Linear(out_dim, vocab_size))
        self.phoneme = nn.Sequential(nn.Dropout(0.1), nn.Linear(out_dim, num_phones)) if num_phones else None

    def forward(self, feats, feat_lens):
        x, x_lens = self.embed(feats, feat_lens)
        x = x.permute(1, 0, 2)  # (T,N,C) p/ o encoder
        enc, enc_lens = self.encoder(x, x_lens)
        enc = enc.permute(1, 0, 2)  # (N,T,C)
        ctc_out = F.log_softmax(self.ctc(enc), dim=-1)
        ph_out = F.log_softmax(self.phoneme(enc), dim=-1) if self.phoneme is not None else None
        return ctc_out, ph_out, enc_lens


def collate(batch, sp, ph_map):
    """K2 dataset já devolve inputs (N,T,80) + supervisions. Monta alvos CTC."""
    feats = batch["inputs"]
    sup = batch["supervisions"]
    feat_lens = sup["num_frames"]
    texts = sup["text"]
    tok = [sp.encode(t, out_type=int) for t in texts]
    tgt = torch.tensor([x for s in tok for x in s], dtype=torch.long)
    tgt_lens = torch.tensor([len(s) for s in tok], dtype=torch.long)
    ph_tgt = ph_tgt_lens = None
    if ph_map is not None:
        phs = [ph_map.get(t, [1]) for t in texts]  # 1 = unk fonema
        ph_tgt = torch.tensor([x for s in phs for x in s], dtype=torch.long)
        ph_tgt_lens = torch.tensor([len(s) for s in phs], dtype=torch.long)
    return feats, feat_lens, tgt, tgt_lens, ph_tgt, ph_tgt_lens


def make_loader(cuts, sp, ph_map, max_dur=200):
    ds = K2SpeechRecognitionDataset(input_strategy=PrecomputedFeatures())
    sampler = DynamicBucketingSampler(cuts, max_duration=max_dur, shuffle=True, num_buckets=10)
    return DataLoader(ds, sampler=sampler, batch_size=None, num_workers=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--use-phoneme", type=int, default=0)
    ap.add_argument("--data", default="data")
    args = ap.parse_args()
    dev = torch.device("cuda")
    exp = Path(args.exp); exp.mkdir(exist_ok=True)

    sp = spm.SentencePieceProcessor(); sp.load(f"{args.data}/bpe_256.model")
    vocab = sp.get_piece_size()
    ph_map = num_phones = None
    if args.use_phoneme:
        pm = json.load(open(f"{args.data}/phoneme_targets.json"))
        ph_map = {k: v for k, v in pm["map"].items()}
        num_phones = pm["num_phones"]

    # cuts já vêm com supervisão clampada no prep; trim_to_supervisions garante o
    # alinhamento exato cut↔supervisão que o validate_for_asr do lhotse exige.
    cuts = CutSet.from_file(f"{args.data}/fleurs_cuts_validation.jsonl.gz")
    cuts = cuts.trim_to_supervisions(keep_overlapping=False).to_eager()
    loader = make_loader(cuts, sp, ph_map)
    model = CtcModel(vocab, num_phones or 0).to(dev)
    nparams = sum(p.numel() for p in model.parameters())
    print(f"[train] params={nparams/1e6:.1f}M vocab={vocab} phoneme={bool(args.use_phoneme)}", flush=True)

    opt = ScaledAdam(model.parameters(), lr=0.045, clipping_scale=2.0)
    sched = Eden(opt, lr_batches=7500, lr_epochs=3.5, warmup_start=0.1)
    step = 0
    for ep in range(args.epochs):
        model.train()
        tot = 0.0; nb = 0
        for batch in loader:
            feats, flens, tgt, tlens, ph_tgt, ph_tlens = collate(batch, sp, ph_map)
            feats, flens = feats.to(dev), flens.to(dev)
            ctc_out, ph_out, enc_lens = model(feats, flens)
            # CTC: (T,N,C)
            loss = F.ctc_loss(ctc_out.permute(1, 0, 2), tgt.to(dev), enc_lens.cpu(),
                              tlens, blank=0, zero_infinity=True)
            if ph_out is not None:
                lph = F.ctc_loss(ph_out.permute(1, 0, 2), ph_tgt.to(dev), enc_lens.cpu(),
                                 ph_tlens, blank=0, zero_infinity=True)
                loss = loss + 0.2 * lph
            opt.zero_grad(); loss.backward(); opt.step(); sched.step_batch(step)
            tot += loss.item(); nb += 1; step += 1
        sched.step_epoch(ep)
        print(f"[train] epoch {ep} loss {tot/max(nb,1):.3f}", flush=True)
    torch.save({"model": model.state_dict(), "vocab": vocab,
                "num_phones": num_phones or 0}, exp / "model.pt")
    print(f"[train] salvo em {exp}/model.pt", flush=True)


if __name__ == "__main__":
    main()
