#!/usr/bin/env python3
"""Transcrição em LOTE de uma pasta de áudios com o modelo M5 (ONNX int8, CPU).

Lê qualquer formato (mp3/m4a/aac/wav/flac/ogg/opus/mp4/webm) via ffmpeg → resample 16 kHz mono
→ segmenta por silêncio (VAD de energia, com teto de duração) → inferência ONNX **em batch**
(eficiente) → texto por arquivo. Decode dos arquivos em paralelo (I/O), inferência batchada
(matmuls agrupados + threads do ONNX). Sem GPU.

Uso:  python3 batch_transcribe.py --input-dir ./audios --out-dir ./transcricoes
      python3 batch_transcribe.py --input-dir ./audios --batch 8 --workers 4 --threads 6
Saída: um .txt por áudio em --out-dir + um resumo transcripts.json (com RTFx agregado).
"""
from __future__ import annotations
import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import onnxruntime as ort

import ctc  # shared kernel (training/common)
from lhotse import Fbank, FbankConfig

SR = 16000
BLANK = 0
WORD_START = "▁"
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".mp4", ".webm"}


def load_tokens(path: str) -> dict[int, str]:
    d = {}
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) == 2:
                d[int(p[1])] = p[0]
    return d


def greedy(log_probs_row: np.ndarray, valid_len: int, id2tok: dict[int, str]) -> str:
    """Colapso CTC greedy de UMA linha (T,V), usando só os `valid_len` frames válidos.

    Delega ao shared kernel (M9/T3.1). A equivalência com a implementação anterior foi
    medida antes da migração — ver `training/tests/test_ctc_equivalence.py`.
    """
    return ctc.greedy_text(log_probs_row, id2tok, valid_len)


def decode_audio(path: str, sr: int = SR) -> np.ndarray:
    """Decodifica qualquer formato para float32 mono @ sr via ffmpeg (fail-fast tipado)."""
    try:
        raw = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-ar", str(sr), "-ac", "1", "-f", "f32le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:  # error-handling.md: erro tipado + contexto
        raise RuntimeError(f"ffmpeg falhou em {path}: {exc.stderr.decode('utf-8', 'ignore')[:200]}") from exc
    return np.frombuffer(raw, dtype=np.float32).copy()


def segment(samples: np.ndarray, sr: int = SR, max_sec: float = 28.0,
            min_sil_sec: float = 0.35, win_sec: float = 0.03) -> list[tuple[int, int]]:
    """Segmenta em trechos curtos cortando em silêncios (VAD de energia), com teto `max_sec`.

    Retorna lista de (start, end) em amostras. Áudio curto vira um único segmento. Trechos que
    excedem `max_sec` (fala contínua sem pausa) são cortados no ponto de menor energia.
    """
    n = len(samples)
    if n == 0:
        return []
    if n <= int(max_sec * sr):
        return [(0, n)]

    w = max(1, int(win_sec * sr))
    nf = n // w
    frames = samples[: nf * w].reshape(nf, w)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1) + 1e-12)
    thresh = max(1e-4, float(np.median(rms)) * 0.5)
    voiced = rms > thresh
    min_sil = max(1, int(min_sil_sec / win_sec))

    # corta nos gaps de silêncio suficientemente longos
    cuts = [0]
    sil = 0
    for i, v in enumerate(voiced):
        sil = 0 if v else sil + 1
        if sil == min_sil and (i * w - cuts[-1]) > int(0.5 * sr):
            cuts.append(i * w)
    cuts.append(n)

    segs: list[tuple[int, int]] = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        # teto de duração: corta trechos longos no frame de menor energia
        while b - a > int(max_sec * sr):
            lo = a + int(0.5 * max_sec * sr)
            hi = min(b, a + int(max_sec * sr))
            fa, fb = lo // w, max(lo // w + 1, hi // w)
            split = (fa + int(np.argmin(rms[fa:fb]))) * w if fb > fa else hi
            segs.append((a, split))
            a = split
        if b > a:
            segs.append((a, b))
    return segs


def _infer_batch(sess, fbanks: list[np.ndarray], id2tok: dict[int, str]) -> list[str]:
    """Inferência ONNX de um batch de fbanks (cada [T,80]); pad ao maior T, greedy por linha."""
    tmax = max(f.shape[0] for f in fbanks)
    x = np.zeros((len(fbanks), tmax, 80), dtype=np.float32)
    xl = np.empty((len(fbanks),), dtype=np.int64)
    for i, f in enumerate(fbanks):
        x[i, : f.shape[0]] = f
        xl[i] = f.shape[0]
    lp, lpl = sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
    return [greedy(lp[i], int(lpl[i]), id2tok) for i in range(len(fbanks))]


def transcribe_folder(input_dir: str, out_dir: str, model: str, tokens: str,
                      batch: int = 8, workers: int = 4, threads: int = 6,
                      max_sec: float = 28.0) -> dict:
    files = sorted(p for p in Path(input_dir).iterdir()
                   if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
    if not files:
        raise FileNotFoundError(f"nenhum áudio ({sorted(AUDIO_EXTS)}) em {input_dir}")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.enable_cpu_mem_arena = False
    sess = ort.InferenceSession(model, so, providers=["CPUExecutionProvider"])
    id2tok = load_tokens(tokens)
    fb = Fbank(FbankConfig(num_mel_bins=80))

    t0 = time.perf_counter()

    # 1. decode + segmenta em paralelo (I/O-bound) -> lista de (file_idx, ordem, fbank)
    def prep(idx_path):
        idx, path = idx_path
        audio = decode_audio(str(path))
        out = []
        for k, (a, b) in enumerate(segment(audio, max_sec=max_sec)):
            seg = audio[a:b]
            if len(seg) >= SR // 4:  # ignora fragmentos < 0.25s
                out.append((idx, k, np.asarray(fb.extract(seg, SR), dtype=np.float32)))
        return out, len(audio) / SR

    total_audio_sec = 0.0
    items: list[tuple[int, int, np.ndarray]] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for segs, dur in ex.map(prep, enumerate(files)):
            items.extend(segs)
            total_audio_sec += dur

    # 2. inferência em batch (ordena por comprimento p/ padding eficiente)
    items.sort(key=lambda it: it[2].shape[0])
    texts: dict[tuple[int, int], str] = {}
    for i in range(0, len(items), batch):
        chunk = items[i : i + batch]
        for (idx, k, _), txt in zip(chunk, _infer_batch(sess, [c[2] for c in chunk], id2tok)):
            texts[(idx, k)] = txt

    # 3. remonta por arquivo (na ordem original dos segmentos) e escreve
    results = []
    for idx, path in enumerate(files):
        parts = [texts[(idx, k)] for (i2, k) in sorted(texts, key=lambda t: t[1]) if i2 == idx]
        full = " ".join(p for p in parts if p).strip()
        outp = Path(out_dir) / (path.stem + ".txt")
        outp.write_text(full + "\n", encoding="utf-8")
        results.append({"file": path.name, "chars": len(full), "out": str(outp)})

    wall = time.perf_counter() - t0
    summary = {
        "files": len(files),
        "segments": len(items),
        "audio_sec": round(total_audio_sec, 1),
        "wall_sec": round(wall, 1),
        "rtfx_agregado": round(total_audio_sec / wall, 1) if wall > 0 else None,
        "results": results,
    }
    (Path(out_dir) / "transcripts.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description="Transcrição em lote (pasta de áudios) — M5 ONNX CPU")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--out-dir", default="./transcricoes")
    ap.add_argument("--model", default="m5_avg.int8.onnx")
    ap.add_argument("--tokens", default="tokens.txt")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4, help="threads de decode paralelo")
    ap.add_argument("--threads", type=int, default=6, help="threads intra-op do ONNX")
    ap.add_argument("--max-sec", type=float, default=28.0, help="duração máx por segmento")
    a = ap.parse_args()
    s = transcribe_folder(a.input_dir, a.out_dir, a.model, a.tokens,
                          batch=a.batch, workers=a.workers, threads=a.threads, max_sec=a.max_sec)
    print(f"[lote] {s['files']} arquivos, {s['segments']} segmentos, {s['audio_sec']}s de áudio "
          f"em {s['wall_sec']}s → RTFx agregado {s['rtfx_agregado']}× | -> {a.out_dir}/")


if __name__ == "__main__":
    main()
