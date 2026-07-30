#!/usr/bin/env python3
"""Phase 2: WER de um checkpoint no CORAA mono-falante degradado por CODEC REALISTA
(métrica âncora D1). Aplica band+codec-pool on-the-fly ao áudio, fbank@16k, greedy CTC.
Roda na CPU (CUDA_VISIBLE_DEVICES="") para não tocar a GPU."""
import argparse, sys
sys.path.insert(0, "/workspace/icefall/egs/commonvoice/ASR/zipformer")
sys.path.insert(0, "/workspace")           # codec_pool + telephone_channel
import numpy as np, torch, sentencepiece as spm
from lhotse import load_manifest_lazy, Fbank, FbankConfig
from scipy.signal import resample_poly
from math import gcd
from train import get_parser as train_parser, get_params, get_model
from icefall.utils import write_error_stats
import codec_pool
from telephone_channel import apply_band

SR = 16000


def build_model(ckpt, bpe, phon):
    p = train_parser()
    a = p.parse_args(["--use-ctc", "1", "--use-transducer", "0", "--use-phoneme-ctc", "1",
        "--phoneme-targets-json", phon, "--num-encoder-layers", "2,2,3,4,3,2",
        "--feedforward-dim", "512,768,1024,1536,1024,768", "--encoder-dim", "192,256,384,512,384,256",
        "--encoder-unmasked-dim", "192,192,256,256,256,192", "--bpe-model", bpe])
    params = get_params(); params.update(vars(a))
    sp = spm.SentencePieceProcessor(); sp.load(bpe)
    params.blank_id = sp.piece_to_id("<blk>"); params.vocab_size = sp.get_piece_size()
    m = get_model(params)
    ck = torch.load(ckpt, map_location="cpu", weights_only=False)
    m.load_state_dict(ck["model"], strict=False); m.eval()
    return m, sp


def _rs(x, a, b):
    if a == b: return x
    g = gcd(int(a), int(b)); return resample_poly(x, b // g, a // g).astype(np.float32)


def greedy(logp, lens, sp):
    ids = logp.argmax(-1)
    outs = []
    for i in range(ids.size(0)):
        seq = ids[i, :lens[i]].tolist(); toks, prev = [], -1
        for t in seq:
            if t != prev and t != 0: toks.append(t)
            prev = t
        outs.append(sp.decode(toks))
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--test", default="data/coraa/cv-pt_cuts_test.jsonl.gz")
    ap.add_argument("--bpe", default="data/lang_bpe_500/bpe.model")
    ap.add_argument("--phon", default="/workspace/phoneme_targets_m5.json")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--out", default="/workspace/wer_realcodec.txt")
    ap.add_argument("--codec", default="pool", help="'pool' sorteia; ou nome fixo (gsm/g711a/...)")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    m, sp = build_model(a.checkpoint, a.bpe, a.phon)
    fb = Fbank(FbankConfig(num_mel_bins=80))
    rng = np.random.default_rng(a.seed)
    cuts = list(load_manifest_lazy(a.test))[: a.n]
    results = []
    with torch.no_grad():
        for c in cuts:
            au = c.load_audio()[0].astype(np.float32)
            band, sr8 = apply_band(au, SR)
            codec = codec_pool.sample_codec(rng) if a.codec == "pool" else a.codec
            coded = codec_pool.apply_codec(band, sr8, codec)
            wav = _rs(coded, sr8, SR)
            feats = torch.from_numpy(np.asarray(fb.extract(wav, SR)))[None]
            lens = torch.tensor([feats.shape[1]])
            enc, el = m.forward_encoder(feats, lens)
            logp = m.ctc_output(enc)
            hyp = greedy(logp, el.tolist(), sp)[0]
            results.append((c.id, c.supervisions[0].text.split(), hyp.split()))
    with open(a.out, "w") as f:
        wer = write_error_stats(f, "coraa-realcodec", results)
    print(f"[realcodec] {len(results)} utts | codec={a.codec} | WER = {wer:.2f}% | -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
