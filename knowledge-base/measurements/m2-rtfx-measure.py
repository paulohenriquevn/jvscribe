#!/usr/bin/env python3
"""Re-mede RTFx dos candidatos M2 capturando dispersão (média ± desvio, min/max).

Fecha o finding F1 do review de M2: o [MEDIDO] original reportou mediana; a regra
asr-evidence-discipline § 1 exige média ± desvio para o rótulo [MEDIDO].

Mesma metodologia da medição original (measurements/m2-rtfx-candidates.md):
- clip de 12s de FLEURS pt_br concatenado, 16 kHz
- Moonshine tiny/base (useful-moonshine-onnx), Zipformer 20M (sherpa-onnx)
- N execuções, warmup descartado, RTFx = dur_audio / wall_time
"""
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

SCRATCH = Path("/tmp/claude-1001/-home-paulo-Projetos-jvscribe/ebb088b0-ac5f-4e4f-8ca0-61bfdd41ad2b/scratchpad")
CLIP = SCRATCH / "fleurs_ptbr_12s.wav"
N_RUNS = 10
N_WARMUP = 3


def build_clip():
    if CLIP.exists():
        return
    print("[clip] construindo clip de 12s do FLEURS pt_br (parquet direto)...", flush=True)
    import io
    import glob
    import soundfile as sf
    import pyarrow.parquet as pq
    # Lê o parquet direto (evita o decoder de áudio do datasets que exige torchcodec).
    pattern = str(Path.home() / ".cache/huggingface/hub/datasets--google--fleurs/snapshots/*/pt_br/test/0000.parquet")
    pf = sorted(glob.glob(pattern))[0]
    tbl = pq.read_table(pf)
    col = tbl.column("audio").to_pylist()
    chunks, total = [], 0.0
    for a in col:
        b = a.get("bytes")
        if not b:
            continue
        arr, sr = sf.read(io.BytesIO(b), dtype="float32")
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        if sr != 16000:
            import librosa
            arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
        chunks.append(arr)
        total += len(arr) / 16000.0
        if total >= 12.0:
            break
    audio = np.concatenate(chunks)[: 16000 * 12]
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(CLIP), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    print(f"[clip] {CLIP} = {len(pcm)/16000:.2f}s", flush=True)


def load_pcm():
    with wave.open(str(CLIP), "rb") as w:
        n = w.getnframes()
        dur = n / w.getframerate()
        pcm = np.frombuffer(w.readframes(n), dtype=np.int16)
    return pcm, dur


def report(name, params, times, extra=""):
    dur_audio = times["dur_audio"]
    ts = times["wall"]  # medições (sem warmup)
    rtfx = [dur_audio / t for t in ts]
    mean = statistics.mean(rtfx)
    std = statistics.pstdev(rtfx)
    print(
        f"\n=== {name} ({params}) ===\n"
        f"  RTFx: média {mean:.2f} ± {std:.2f} · min {min(rtfx):.2f} · max {max(rtfx):.2f} "
        f"· mediana {statistics.median(rtfx):.2f} (n={len(rtfx)})\n"
        f"  wall(ms): média {1000*statistics.mean(ts):.0f} ± {1000*statistics.pstdev(ts):.0f} "
        f"· min {1000*min(ts):.0f} · max {1000*max(ts):.0f}\n"
        f"  {extra}",
        flush=True,
    )


def bench_moonshine(model_name, label, params):
    from moonshine_onnx import MoonshineOnnxModel, load_audio
    m = MoonshineOnnxModel(model_name=model_name)
    audio = load_audio(str(CLIP))
    _, dur = load_pcm()
    n_tokens = None
    walls = []
    for i in range(N_RUNS + N_WARMUP):
        t = time.perf_counter()
        toks = m.generate(audio)
        el = time.perf_counter() - t
        if i >= N_WARMUP:
            walls.append(el)
        n_tokens = len(toks[0]) if hasattr(toks[0], "__len__") else None
    report(label, params, {"dur_audio": dur, "wall": walls}, extra=f"tokens gerados: {n_tokens} (custo AED ∝ tokens)")


def bench_zipformer():
    import sherpa_onnx
    base = SCRATCH / "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17"
    if not base.exists():
        print("[zipformer] baixando modelo...", flush=True)
        url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17.tar.bz2"
        tar = SCRATCH / "zip.tar.bz2"
        subprocess.run(["curl", "-sL", "-o", str(tar), url], check=True)
        subprocess.run(["tar", "xjf", str(tar), "-C", str(SCRATCH)], check=True)
    rec = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(base / "tokens.txt"),
        encoder=str(base / "encoder-epoch-99-avg-1.onnx"),
        decoder=str(base / "decoder-epoch-99-avg-1.onnx"),
        joiner=str(base / "joiner-epoch-99-avg-1.onnx"),
        num_threads=2,
        provider="cpu",
    )
    pcm, dur = load_pcm()
    samples = pcm.astype(np.float32) / 32768.0
    walls = []
    for i in range(N_RUNS + N_WARMUP):
        t = time.perf_counter()
        s = rec.create_stream()
        s.accept_waveform(16000, samples)
        s.input_finished()
        while rec.is_ready(s):
            rec.decode_stream(s)
        el = time.perf_counter() - t
        if i >= N_WARMUP:
            walls.append(el)
    report("Zipformer transducer streaming", "~20M", {"dur_audio": dur, "wall": walls}, extra="custo fixo ∝ frames")


if __name__ == "__main__":
    import os
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    build_clip()
    _, dur = load_pcm()
    print(f"[audio] clip = {dur:.2f}s · OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')} · N={N_RUNS} (+{N_WARMUP} warmup)", flush=True)
    try:
        bench_moonshine("moonshine/tiny", "Moonshine tiny", "~27M")
    except Exception as e:
        print(f"[erro moonshine tiny] {e}", flush=True)
    try:
        bench_moonshine("moonshine/base", "Moonshine base", "~62M")
    except Exception as e:
        print(f"[erro moonshine base] {e}", flush=True)
    try:
        bench_zipformer()
    except Exception as e:
        print(f"[erro zipformer] {e}", flush=True)
    print("\n[done]", flush=True)
