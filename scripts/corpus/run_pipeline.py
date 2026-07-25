"""Orquestra o pipeline de corpus de M3 ponta-a-ponta sobre FLEURS pt_br real.

Fluxo (Integration Validation do plano m3-corpus):
  FLEURS pt_br (N clips) → 2 whisper sequenciais → CER par-a-par → τ calibrado →
  filtro por concordância → manifest Lhotse com telephone on-the-fly → evidência [MEDIDO].

Grava `knowledge-base/corpus/m3-cer-distribution.md`. Uso:
  python3 scripts/corpus/run_pipeline.py --n 20
"""

from __future__ import annotations

import argparse
import glob
import io
import os
import statistics
import sys
import tempfile
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/

from corpus.agreement_filter import calibrate_tau, pairwise_cer  # noqa: E402
from corpus.build_manifest import build_cutset, load_telephone_audio  # noqa: E402
from corpus.pseudo_label import transcribe_pair  # noqa: E402

REPORT = "knowledge-base/corpus/m3-cer-distribution.md"


def load_fleurs_wavs(n: int, out_dir: str) -> dict[str, str]:
    """Escreve N clips de FLEURS pt_br (test) como WAV 16 kHz. Parquet direto (sem torchcodec)."""
    pattern = str(
        Path.home()
        / ".cache/huggingface/hub/datasets--google--fleurs/snapshots/*/pt_br/test/0000.parquet"
    )
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError("FLEURS pt_br parquet não encontrado no cache HF")
    col = pq.read_table(matches[0]).column("audio").to_pylist()
    paths: dict[str, str] = {}
    for i, a in enumerate(col):
        if len(paths) >= n:
            break
        raw = a.get("bytes")
        if not raw:
            continue
        arr, sr = sf.read(io.BytesIO(raw), dtype="float32")
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        if sr != 16000:
            import librosa

            arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
        cid = f"fleurs_{i:03d}"
        path = os.path.join(out_dir, f"{cid}.wav")
        sf.write(path, arr, 16000)
        paths[cid] = path
    return paths


def write_report(cers: dict[str, float], tau: float, kept: set[str],
                 sizes: tuple[str, str], sr_proof: int) -> None:
    vals = list(cers.values())
    mean = statistics.mean(vals)
    median = statistics.median(vals)
    std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    lines = [
        "# M3 — Distribuição de CER par-a-par (evidência [MEDIDO])",
        "",
        f"**Data:** run do pipeline · **Fonte:** FLEURS pt_br (test), {len(vals)} clips reais",
        f"**Transcritores:** faster-whisper `{sizes[0]}` + `{sizes[1]}` (int8, CPU, sequenciais — RAM-safe)",
        f"**Métrica:** CER par-a-par (normalizado PT-BR) entre as 2 hipóteses de máquina.",
        "",
        "## Estatística da distribuição `[MEDIDO]`",
        "",
        f"- média {mean:.3f} ± {std:.3f} · mediana {median:.3f} · min {min(vals):.3f} · max {max(vals):.3f} (n={len(vals)})",
        f"- **τ calibrado** (manter 80% mais concordantes, percentil empírico): **{tau:.3f}**",
        f"- cuts **mantidos** {len(kept)} / **descartados** {len(vals) - len(kept)} (invariante § 3 #10: só pool de treino)",
        f"- prova on-the-fly: `load_telephone_audio` do 1º cut retorna sr = **{sr_proof} Hz** (augmentação em RAM, sem WAV em disco)",
        "",
        "## CER por clip",
        "",
        "| clip | CER(h1,h2) | mantido? |",
        "|---|---|---|",
    ]
    for cid in sorted(cers):
        lines.append(f"| {cid} | {cers[cid]:.3f} | {'✅' if cid in kept else '❌ descartado'} |")
    lines += [
        "",
        "## Leitura honesta",
        "",
        "- Caveat (ADR-3): os 2 whisper são da mesma família → correlacionam erros; a concordância",
        "  superestima confiança. Um 2º transcritor de arquitetura distinta (parakeet) melhora o sinal (backlog).",
        "- τ é derivado da distribuição empírica desta amostra (não a priori); re-calibrar em corpus maior (M4).",
    ]
    Path(REPORT).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--keep", type=float, default=0.8)
    ap.add_argument("--sizes", nargs=2, default=["small", "base"])
    args = ap.parse_args()
    sizes = (args.sizes[0], args.sizes[1])

    out_dir = tempfile.mkdtemp(prefix="m3_corpus_")
    print(f"[pipeline] carregando {args.n} clips FLEURS pt_br → {out_dir}", flush=True)
    paths = load_fleurs_wavs(args.n, out_dir)
    print(f"[pipeline] {len(paths)} WAVs; transcrevendo com {sizes} (sequencial)...", flush=True)

    pairs = transcribe_pair(paths, sizes=sizes)
    cers = {cid: pairwise_cer(h1, h2) for cid, (h1, h2) in pairs.items()}
    tau = calibrate_tau(list(cers.values()), keep_fraction=args.keep)
    kept = {cid for cid, c in cers.items() if c <= tau}
    print(f"[pipeline] τ={tau:.3f}; mantidos {len(kept)}/{len(cers)}", flush=True)

    # manifest Lhotse com telephone on-the-fly (labels = hipótese do professor #1)
    labels = {cid: pairs[cid][0] for cid in paths}
    cutset = build_cutset(out_dir, labels)
    first = list(cutset)[0]
    _audio, sr_proof = load_telephone_audio(first)
    print(f"[pipeline] manifest: {len(cutset)} cuts; telephone on-the-fly → {sr_proof} Hz", flush=True)

    write_report(cers, tau, kept, sizes, sr_proof)
    print(f"[pipeline] evidência gravada em {REPORT}", flush=True)


if __name__ == "__main__":
    main()
