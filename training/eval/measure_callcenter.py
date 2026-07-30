#!/usr/bin/env python3
"""Mede WER do modelo M5 (ONNX) em áudio real de call center 8 kHz — DoD#3 REAL.

Genérico (áudio + transcrição por argumento) para ser versionável; o DADO (call
center) fica LOCAL por LGPD. Segmenta pela transcrição humana timestampada (blocos
de ~30s), normaliza ref/hyp, computa WER agregado via jiwer. Caveats honestos: 9 min
→ IC largo; 2 interlocutores no mesmo mono; granularidade de 30s; PII mascarada conta
como erro. Direciona, não conclui (asr-evidence-discipline § 3 #12).
"""
import argparse, re
import numpy as np
import onnxruntime as ort
import soundfile as sf
from lhotse import Fbank, FbankConfig
import jiwer

SR = 16000
TS_RE = re.compile(r'^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$')


def parse_transcript(path):
    blocks, cur_ts, cur = [], None, []
    def flush():
        if cur_ts is not None:
            blocks.append((cur_ts, " ".join(cur).strip()))
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if not s or s == "⚠️":
            continue
        m = TS_RE.match(s)
        if m:
            flush()
            a, b, c = m.groups()
            cur_ts = (int(a) * 60 + int(b)) if c is None else (int(a) * 3600 + int(b) * 60 + int(c))
            cur = []
        else:
            cur.append(s)
    flush()
    return blocks


def normalize(t):
    t = t.lower().replace("⚠️", " ")
    t = re.sub(r"_+", " ", t)                          # máscaras de PII
    t = re.sub(r"[^0-9a-zàáâãéêíóôõúüç ]", " ", t)      # tira pontuação, mantém acento
    return re.sub(r"\s+", " ", t).strip()


def load_tokens(path):
    d = {}
    for line in open(path):
        p = line.split()
        if len(p) == 2:
            d[int(p[1])] = p[0]
    return d


def greedy(lp, id2tok):
    """Delega ao shared kernel (M9/T3.1) — equivalência medida antes da migração."""
    import pathlib
    import sys

    # Mesmo motivo do insert em batch_transcribe: este script tem de rodar standalone, e o
    # `conftest.py` só expõe `common/` para os testes.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
    import ctc

    return ctc.greedy_text(lp[0], id2tok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokens", required=True)
    a = ap.parse_args()

    so = ort.SessionOptions(); so.enable_cpu_mem_arena = False
    sess = ort.InferenceSession(a.model, so, providers=["CPUExecutionProvider"])
    id2tok = load_tokens(a.tokens)
    fb = Fbank(FbankConfig(num_mel_bins=80))
    audio, sr = sf.read(a.wav)
    assert sr == SR, sr
    if audio.ndim > 1:
        audio = audio[:, 0]

    blocks = parse_transcript(a.transcript)
    refs, hyps = [], []
    for i, (start, ref) in enumerate(blocks):
        end = blocks[i + 1][0] if i + 1 < len(blocks) else len(audio) / SR
        seg = audio[int(start * SR):int(end * SR)].astype(np.float32)
        if len(seg) < SR // 2:
            continue
        feats = fb.extract(seg, SR)
        x = feats[None].astype(np.float32)
        xl = np.array([feats.shape[0]], dtype=np.int64)
        lp, _ = sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
        rn, hn = normalize(ref), normalize(greedy(lp, id2tok))
        if not rn:
            continue
        refs.append(rn); hyps.append(hn)
        print(f"[{i:02d}] {start:>4}s ref={rn[:75]!r}")
        print(f"          hyp={hn[:75]!r}")

    wer = jiwer.wer(refs, hyps)
    nwords = len(" ".join(refs).split())
    print(f"\n=== WER real call center 8 kHz = {wer*100:.2f}%  "
          f"({len(refs)} segmentos, {nwords} palavras de referência) ===")
    print("CAVEAT: 9 min → IC largo; 2 interlocutores no mono; granularidade 30s. Direciona, não conclui.")


if __name__ == "__main__":
    main()
