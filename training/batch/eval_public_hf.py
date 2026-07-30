#!/usr/bin/env python3
"""Mede WER do batch_transcribe num dataset PÚBLICO do HF (FLEURS pt_br) — fala lida
banda-larga (perfil ~128 kbps). Pega bytes crus (decode=False, sem torchcodec), grava
como arquivos, roda batch_transcribe, compara com a referência humana via jiwer."""
import os, re, sys, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # batch/ — co-locado com batch_transcribe
from datasets import load_dataset, Audio
import jiwer
from batch_transcribe import transcribe_folder

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
import tempfile; SC = tempfile.mkdtemp(prefix="fleurs_eval_")
AUD = Path(f"{SC}/fleurs_aud"); OUT = Path(f"{SC}/fleurs_out")
M = "/home/paulo/Projetos/jvscribe/models/m5-final-medium-phoneme"

def norm(t):
    t = t.lower()
    t = re.sub(r"[^0-9a-zàáâãéêíóôõúüç ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

AUD.mkdir(parents=True, exist_ok=True)
ds = load_dataset("google/fleurs", "pt_br", split="test", streaming=True)
ds = ds.cast_column("audio", Audio(decode=False))
refs = {}
for i, ex in enumerate(ds):
    if i >= N: break
    b = ex["audio"]["bytes"]
    if b is None:  # às vezes vem como path
        b = Path(ex["audio"]["path"]).read_bytes()
    fid = f"utt{i:04d}"
    (AUD / f"{fid}.wav").write_bytes(b)
    refs[fid] = ex["transcription"]
print(f"[fleurs] {len(refs)} amostras gravadas")

s = transcribe_folder(str(AUD), str(OUT), f"{M}/m5_avg.int8.onnx", f"{M}/tokens.txt",
                      batch=8, workers=4, threads=6)

R, H = [], []
for fid, ref in refs.items():
    hyp = (OUT / f"{fid}.txt").read_text(encoding="utf-8").strip()
    rn, hn = norm(ref), norm(hyp)
    if rn:
        R.append(rn); H.append(hn)
o = jiwer.process_words(R, H)
nwords = o.hits + o.substitutions + o.deletions
print(json.dumps({
    "dataset": "google/fleurs pt_br test",
    "n": len(R), "ref_words": nwords,
    "WER_pct": round(o.wer * 100, 2),
    "hits_pct": round(o.hits / nwords * 100, 1),
    "sub_pct": round(o.substitutions / nwords * 100, 1),
    "del_pct": round(o.deletions / nwords * 100, 1),
    "ins_pct": round(o.insertions / nwords * 100, 1),
    "audio_sec": s["audio_sec"], "wall_sec": s["wall_sec"], "rtfx": s["rtfx_agregado"],
}, ensure_ascii=False, indent=2))
