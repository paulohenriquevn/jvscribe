#!/usr/bin/env python3
"""Phase 2: WER de um checkpoint no CORAA mono-falante degradado por CODEC REALISTA
(métrica âncora D1). Aplica band+codec-pool on-the-fly ao áudio, fbank@16k, greedy CTC.
Roda na CPU (CUDA_VISIBLE_DEVICES="") para não tocar a GPU."""
import argparse, os, pathlib, sys
import numpy as np, torch, sentencepiece as spm
from lhotse import load_manifest_lazy, Fbank, FbankConfig
from scipy.signal import resample_poly
from math import gcd

# O canal telefônico virou `common/audio/` (é sinal, não corpus) e o `ctc` é o shared
# kernel. Antes isto apontava para `/workspace`, que só existe na máquina de treino.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
import ctc  # noqa: E402  — shared kernel
from audio import codecs as codec_pool  # noqa: E402
from audio.channel import apply_band  # noqa: E402

SR = 16000
# Único caminho genuinamente externo: a recipe zipformer do icefall (não é do repositório).
# Era hardcoded em `/workspace/icefall/...`; agora falha alto e claro quando não resolve, em
# vez de morrer num ImportError que não diz o que configurar.
ICEFALL_ROOT_PADRAO = "/workspace/icefall"


def _importar_do_icefall(raiz: str):
    """Importa a recipe do icefall — fail-fast com instrução, não ImportError cru."""
    recipe = pathlib.Path(raiz) / "egs/commonvoice/ASR/zipformer"
    if not recipe.is_dir():
        raise FileNotFoundError(
            f"recipe do icefall não encontrada em {recipe}. Passe --icefall-root <caminho> "
            f"ou exporte ICEFALL_ROOT. Este script só roda onde o icefall está clonado."
        )
    sys.path.insert(0, str(recipe))
    sys.path.insert(0, str(pathlib.Path(raiz).parent))
    from train import get_parser, get_params, get_model  # noqa: E402
    from icefall.utils import write_error_stats  # noqa: E402
    return get_parser, get_params, get_model, write_error_stats


def build_model(ckpt, bpe, phon, train_parser, get_params, get_model):
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
    """Colapso CTC greedy por linha, detokenizando com o SentencePiece.

    O **colapso** é delegado ao shared kernel (`common/ctc.py`) — era reimplementado aqui. A
    **detokenização** continua sendo `sp.decode()`: o kernel usa a convenção
    `join + replace ▁`, e o SentencePiece resolve pieces que essa convenção não cobre. As duas
    são legítimas; o que não podia era duplicar o colapso.
    """
    return [sp.decode(ctc.greedy_ids(logp[i], int(lens[i]))) for i in range(logp.shape[0])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--test", default="data/coraa/cv-pt_cuts_test.jsonl.gz")
    ap.add_argument("--bpe", default="data/lang_bpe_500/bpe.model")
    ap.add_argument("--phon", default="phoneme_targets_m5.json")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--out", default="wer_realcodec.txt")
    ap.add_argument("--codec", default="pool", help="'pool' sorteia; ou nome fixo (gsm/g711a/...)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--icefall-root", default=os.environ.get("ICEFALL_ROOT", ICEFALL_ROOT_PADRAO),
                    help="raiz do clone do icefall (env ICEFALL_ROOT)")
    a = ap.parse_args()

    train_parser, get_params, get_model, write_error_stats = _importar_do_icefall(a.icefall_root)
    m, sp = build_model(a.checkpoint, a.bpe, a.phon, train_parser, get_params, get_model)
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
