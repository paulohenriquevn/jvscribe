"""Experimento #1 do chief scientist: mede a penalidade telefônica no modelo de 161h JÁ
treinado, sem treinar nada. Degrada o held-out FLEURS pela cadeia telefônica do M3
(banda 300-3400 Hz + G.711 A-law) e re-decodifica → WER telefônico vs WER limpo.

Design honesto: após a degradação (que sai a 8 kHz), faz resample de volta a 16 kHz
antes do fbank — assim o extrator vê a MESMA sample-rate do treino, isolando o dano do
CANAL (band-limiting/A-law) do confound de mismatch de sample-rate. Reusa
`telephone_channel.apply_telephone_channel` do M3 (Regra 9).

Roda NA instância: python3 make_telephone_test.py --in data/pt --out data/pt_tel
"""

from __future__ import annotations

import argparse
from math import gcd
from pathlib import Path

import soundfile as sf
from lhotse import CutSet, Fbank, FbankConfig, Recording, SupervisionSegment, SupervisionSet
from lhotse.audio import RecordingSet
from lhotse.utils import fastcopy
from scipy.signal import resample_poly

from telephone_channel import apply_telephone_channel


def _resample(x, sr_from: int, sr_to: int):
    if sr_from == sr_to:
        return x
    g = gcd(sr_from, sr_to)
    return resample_poly(x, sr_to // g, sr_from // g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/pt")
    ap.add_argument("--out", default="data/pt_tel")
    ap.add_argument("--split", default="test")
    args = ap.parse_args()
    src = Path(args.inp); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    wav_dir = out / "wav"; wav_dir.mkdir(exist_ok=True)
    extractor = Fbank(FbankConfig(num_mel_bins=80))

    cuts = CutSet.from_file(str(src / f"cv-pt_cuts_{args.split}.jsonl.gz"))
    recs, sups = [], []
    for cut in cuts:
        samples = cut.load_audio()[0]  # (T,) mono float32, 16 kHz
        deg8k, sr8 = apply_telephone_channel(samples, int(cut.sampling_rate))
        deg16k = _resample(deg8k, sr8, int(cut.sampling_rate))  # volta à SR do treino
        cid = cut.id
        wav = wav_dir / f"{cid}.wav"
        sf.write(str(wav), deg16k, int(cut.sampling_rate))
        rec = Recording.from_file(str(wav), recording_id=cid)
        recs.append(rec)
        text = cut.supervisions[0].text
        sups.append(SupervisionSegment(id=f"{cid}-0", recording_id=cid, start=0.0,
                                       duration=rec.duration, channel=0,
                                       language="Portuguese", text=text))

    cs = CutSet.from_manifests(recordings=RecordingSet.from_recordings(recs),
                               supervisions=SupervisionSet.from_segments(sups))
    cs = cs.compute_and_store_features(extractor=extractor,
                                       storage_path=str(out / f"feats_{args.split}"),
                                       num_jobs=1)
    cs = CutSet.from_cuts(
        fastcopy(c, supervisions=[
            fastcopy(sp, duration=round(c.duration - sp.start, 4))
            if sp.start + sp.duration > c.duration else sp
            for sp in c.supervisions]) for c in cs)
    cs.to_file(str(out / f"cv-pt_cuts_{args.split}.jsonl.gz"))
    print(f"[tel] {len(cs)} cuts telefônicos → {out}/cv-pt_cuts_{args.split}.jsonl.gz", flush=True)


if __name__ == "__main__":
    main()
