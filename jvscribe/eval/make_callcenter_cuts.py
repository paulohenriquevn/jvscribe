"""Prepara a clip real de call-center (8 kHz) para decode qualitativo do DoD#3 real-world.
8 kHz -> resample 16 kHz (SR do treino) -> Silero VAD -> cuts por fala -> fbank 80-mel.
Reusa apply/VAD já usados no projeto (Regra 9). Roda NA instância.

Uso: python3 make_callcenter_cuts.py --mp3 /workspace/callcenter/texto.mp3 --out data/callcenter
"""
from __future__ import annotations
import argparse
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from lhotse import CutSet, Fbank, FbankConfig, Recording, SupervisionSegment, SupervisionSet
from lhotse.features.io import LilcomChunkyWriter
from lhotse.audio import RecordingSet
from scipy.signal import resample_poly


def _resample(x, sr_from: int, sr_to: int):
    if sr_from == sr_to:
        return x
    g = gcd(sr_from, sr_to)
    return resample_poly(x, sr_to // g, sr_from // g).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp3", required=True)
    ap.add_argument("--out", default="data/callcenter")
    ap.add_argument("--min-sil-ms", type=int, default=350)
    ap.add_argument("--max-seg-s", type=float, default=25.0)
    args = ap.parse_args()

    # Fail-fast COM instrução na fronteira: sem isto o script morre no traceback cru da lib
    # (`FileNotFoundError`/`LibsndfileError`), que não diz ao operador o que buscar.
    # `error-handling.md` § 2: valide na entrada, falhe claro. Achado no live test 2026-07-31.
    import pathlib as _p
    if not _p.Path(args.mp3).exists():
        raise SystemExit(
            f"gravação da ligação não encontrado: {args.mp3}\n"
            "O dado de call center é LOCAL por LGPD — não é versionado neste repositório."
        )
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    wav_dir = out / "wav"; wav_dir.mkdir(exist_ok=True)

    # 1) carregar mp3 (8 kHz) -> mono float32 -> resample 16 kHz
    x, sr = sf.read(args.mp3, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    x16 = _resample(x, sr, 16000)
    print(f"[cc] mp3 sr={sr} dur={len(x)/sr:.1f}s -> 16k dur={len(x16)/16000:.1f}s", flush=True)

    # 2) Silero VAD (torch.hub) -> timestamps de fala
    model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
    get_ts = utils[0]
    ts = get_ts(torch.from_numpy(x16), model, sampling_rate=16000,
                min_silence_duration_ms=args.min_sil_ms, max_speech_duration_s=args.max_seg_s)
    print(f"[cc] VAD: {len(ts)} segmentos de fala", flush=True)

    # 3) um wav+cut por segmento
    extractor = Fbank(FbankConfig(num_mel_bins=80))
    recs, sups = [], []
    for i, seg in enumerate(ts):
        a, b = seg["start"], seg["end"]
        clip = x16[a:b]
        if len(clip) < 1600:  # <0.1s, descarta
            continue
        cid = f"cc_{i:04d}"
        w = wav_dir / f"{cid}.wav"
        sf.write(str(w), clip, 16000)
        rec = Recording.from_file(str(w), recording_id=cid)
        recs.append(rec)
        sups.append(SupervisionSegment(id=f"{cid}-0", recording_id=cid, start=0.0,
                                       duration=rec.duration, channel=0,
                                       language="Portuguese", text=""))
    cs = CutSet.from_manifests(recordings=RecordingSet.from_recordings(recs),
                               supervisions=SupervisionSet.from_segments(sups))
        # `storage_type` EXPLÍCITO: o default do lhotse é `numpy_files`, que grava
        # **115 MB por hora** de áudio contra **33 MB** do `lilcom_chunky` `[MEDIDO]`
        # (`wiki/medicoes/m10-t3-fbank-e-storage.md`). Em 5.000 h a diferença é de ~410 GB,
        # e o lhotse não avisa — ele apenas grava maior.
    cs = cs.compute_and_store_features(extractor=extractor,
                                       storage_path=str(out / "feats"), num_jobs=1,
                                       storage_type=LilcomChunkyWriter)
    cs.to_file(str(out / "cv-pt_cuts_test.jsonl.gz"))
    print(f"[cc] {len(cs)} cuts -> {out}/cv-pt_cuts_test.jsonl.gz", flush=True)


if __name__ == "__main__":
    main()
