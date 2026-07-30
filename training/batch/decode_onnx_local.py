"""Teste final do M5 no notebook (CPU) — decode ONNX int8 do modelo, medindo WER e RTFx.
Reusa onnxruntime + lhotse (features lilcom) + jiwer (WER). Greedy CTC.
Este é o ambiente-alvo do produto (CPU do atendente), não a GPU de treino.

Uso:
    python3 decode_onnx_local.py --model model.int8.onnx --test testdata/coraa/cv-pt_cuts_test.jsonl.gz
"""
from __future__ import annotations
import argparse, time
import numpy as np
import onnxruntime as ort
from lhotse import CutSet
import jiwer


def load_tokens(path):
    id2tok = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                id2tok[int(parts[1])] = parts[0]
    return id2tok


def ids_to_text(ids, id2tok):
    pieces = [id2tok.get(i, "") for i in ids]
    return "".join(pieces).replace("▁", " ").strip()


def greedy_ctc(log_probs, lens):
    # log_probs: (N,T,V); lens: (N,) frames válidos
    ids = log_probs.argmax(-1)  # (N,T)
    outs = []
    for i in range(ids.shape[0]):
        seq = ids[i, : lens[i]]
        toks, prev = [], -1
        for t in seq:
            if t != prev and t != 0:  # colapsa repetição + remove blank(0)
                toks.append(int(t))
            prev = t
        outs.append(toks)
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="model.int8.onnx")
    ap.add_argument("--tokens", default="tokens.txt")
    ap.add_argument("--test", required=True)
    ap.add_argument("--limit", type=int, default=0)  # 0 = todos
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()

    import gc
    so = ort.SessionOptions()
    so.intra_op_num_threads = a.threads
    so.inter_op_num_threads = 1
    so.enable_cpu_mem_arena = False   # evita o arena que cresce sem devolver (causa do OOM)
    so.enable_mem_pattern = False
    sess = ort.InferenceSession(a.model, so, providers=["CPUExecutionProvider"])
    id2tok = load_tokens(a.tokens)

    cuts = CutSet.from_file(a.test)
    all_cuts = list(cuts)
    if a.limit:
        all_cuts = all_cuts[: a.limit]
    # ordena por duração → batches uniformes (menos padding, menos pico de memória)
    all_cuts.sort(key=lambda c: c.duration)
    print(f"[onnx] {len(all_cuts)} utts | model={a.model} | threads={a.threads} | arena=off", flush=True)

    refs, hyps = [], []
    total_audio_s = 0.0
    t0 = time.perf_counter()
    n = 0
    for i in range(0, len(all_cuts), a.batch):
        batch = all_cuts[i : i + a.batch]
        feats = [c.load_features() for c in batch]  # cada (T,80)
        lens = np.array([f.shape[0] for f in feats], dtype=np.int64)
        T = int(lens.max())
        x = np.zeros((len(feats), T, 80), dtype=np.float32)
        for j, f in enumerate(feats):
            x[j, : f.shape[0]] = f
        log_probs, lp_len = sess.run(["log_probs", "log_probs_len"],
                                     {"x": x, "x_lens": lens})
        hyp_ids = greedy_ctc(log_probs, lp_len.astype(int))
        for c, ids in zip(batch, hyp_ids):
            refs.append(c.supervisions[0].text)
            hyps.append(ids_to_text(ids, id2tok))
            total_audio_s += c.duration
        n += len(batch)
        del feats, x, log_probs, lp_len, hyp_ids
        if n % 512 < a.batch:
            gc.collect()
            print(f"[onnx] {n}/{len(all_cuts)}", flush=True)
    elapsed = time.perf_counter() - t0

    rtfx = total_audio_s / elapsed
    has_refs = any(r.strip() for r in refs)
    print("=" * 50)
    print(f"[RESULT] utts={len(refs)}")
    if has_refs:
        wer = jiwer.wer(refs, hyps) * 100
        cer = jiwer.cer(refs, hyps) * 100
        print(f"[RESULT] WER = {wer:.2f}%")
        print(f"[RESULT] CER = {cer:.2f}%")
    else:
        print("[RESULT] modo QUALITATIVO (sem ground-truth) — hipóteses abaixo")
    print(f"[RESULT] audio={total_audio_s/3600:.2f}h  wall={elapsed:.1f}s  RTFx = {rtfx:.2f}x")
    print("=" * 50)
    if has_refs:
        for r, h in list(zip(refs, hyps))[:3]:
            print(f"REF: {r[:90]}")
            print(f"HYP: {h[:90]}")
            print()
    else:
        for h in hyps:
            if h.strip():
                print(f"HYP: {h}")


if __name__ == "__main__":
    main()
