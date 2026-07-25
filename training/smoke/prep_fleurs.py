"""Prepara FLEURS pt_br para treino icefall (M4 — piloto). Roda NA INSTÂNCIA GPU.

Reuso máximo (Regra 9): baixa os parquets do FLEURS via huggingface_hub, constrói
manifests Lhotse (RecordingSet/SupervisionSet/CutSet) e computa fbank 80-dim — o
formato que a recipe icefall zipformer consome. Não reinventa nada: lhotse faz o
manifest e o fbank; nós só apontamos para FLEURS pt_br (a versão de lhotse da imagem
oficial não traz a recipe fleurs pronta).

Uso: python3 prep_fleurs.py --out data [--limit N]
"""

from __future__ import annotations

import argparse
import glob
import io
import os
import re
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf
import pyarrow.parquet as pq
from lhotse import CutSet, Fbank, FbankConfig, Recording, SupervisionSegment, SupervisionSet
from lhotse.audio import RecordingSet

# Parquets do FLEURS pt_br baixados via curl (HF migrou p/ xet; download direto por
# resolve/main com token é o caminho robusto — ver training/README).
PARQUET_DIR = os.environ.get("FLEURS_PARQUET_DIR", "/workspace/pq")


def normalize_ptbr(text: str) -> str:
    """Normalização mínima (lower, remove pontuação, colapsa espaço) — alvo de treino."""
    text = text.lower().strip()
    text = "".join(c for c in unicodedata.normalize("NFC", text))
    text = re.sub(r"[^\w\sáàâãéêíóôõúçü]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _parquet(split: str) -> str:
    path = os.path.join(PARQUET_DIR, f"{split}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"parquet '{split}' não encontrado em {PARQUET_DIR}; baixe via dl.sh primeiro"
        )
    return path


def build_split(split: str, out: Path, limit: int | None) -> int:
    wav_dir = out / "wav" / split
    wav_dir.mkdir(parents=True, exist_ok=True)
    recs, sups = [], []
    n = 0
    pf = pq.ParquetFile(_parquet(split))
    for batch in pf.iter_batches(batch_size=64, columns=["id", "audio", "transcription"]):
        d = batch.to_pydict()
        for i in range(len(d["id"])):
            if limit is not None and n >= limit:
                break
            raw = d["audio"][i].get("bytes")
            text = normalize_ptbr(d["transcription"][i] or "")
            if not raw or not text:
                continue
            arr, sr = sf.read(io.BytesIO(raw), dtype="float32")
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            if sr != 16000:
                import librosa
                arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
                sr = 16000
            # id sequencial ÚNICO — o campo 'id' do FLEURS se repete (mesma sentença,
            # múltiplos falantes), o que sobrescreveria WAVs e duplicaria supervisões.
            cid = f"fleurs_{split}_{n:06d}"
            wav_path = wav_dir / f"{cid}.wav"
            sf.write(str(wav_path), arr, sr)
            rec = Recording.from_file(str(wav_path), recording_id=cid)
            recs.append(rec)
            sups.append(SupervisionSegment(id=f"{cid}-0", recording_id=cid, start=0.0,
                                           duration=rec.duration, channel=0,
                                           language="Portuguese", text=text))
            n += 1
        if limit is not None and n >= limit:
            break
    rset = RecordingSet.from_recordings(recs)
    sset = SupervisionSet.from_segments(sups)
    cuts = CutSet.from_manifests(recordings=rset, supervisions=sset)
    # fbank 80-dim (o que a recipe zipformer espera)
    extractor = Fbank(FbankConfig(num_mel_bins=80))
    cuts = cuts.compute_and_store_features(
        extractor=extractor,
        storage_path=str(out / f"feats_{split}"),
        num_jobs=1,
    )
    # clampa a supervisão à duração das FEATURES (o fbank arredonda num_frames p/ baixo,
    # deixando a supervisão do áudio ligeiramente mais longa → quebra validate_for_asr).
    from lhotse.utils import fastcopy

    def _clamp(c):
        new = []
        for s in c.supervisions:
            if s.start + s.duration > c.duration:
                s = fastcopy(s, duration=round(c.duration - s.start, 4))
            new.append(s)
        return fastcopy(c, supervisions=new)

    cuts = CutSet.from_cuts(_clamp(c) for c in cuts)
    cuts.to_file(str(out / f"fleurs_cuts_{split}.jsonl.gz"))
    # texto para o BPE (só train)
    if True:  # texto do split (usado p/ BPE)
        (out / "transcript_words.txt").write_text(
            "\n".join(s.text for s in sups) + "\n", encoding="utf-8")
    print(f"[fleurs] {split}: {n} cuts, fbank em feats_{split}", flush=True)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--splits", nargs="+", default=["train", "validation", "test"])
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for split in args.splits:
        build_split(split, out, args.limit)
    print("[fleurs] pronto", flush=True)


if __name__ == "__main__":
    main()
