"""Resume da extração de features do TAGARELA (M5) — recupera o run cujo build_split
COMPLETOU (429.885 wavs escritos em wav_train/) mas cujo compute_and_store_features
DEADLOCKOU (bug num_jobs>1 + torch threads>1 — lição m4-icefall-training-gotchas).

Em vez de re-decodificar 483k FLAC (~90 min já feitos), reconstrói o CutSet a partir dos
wavs EXISTENTES: reaplica os MESMOS filtros de `prep_tagarela.build_split` (ordem idêntica
via `iter_parquet_shards` sorted + as mesmas funções importadas — DRY, sem duplicar a lógica),
mas obtém a duração do `bad_ratio` por `sf.info` (header-only, microssegundos) em vez de decode.
Referencia o wav já em disco (`Recording.from_file`). `assert kept==429885` é o safety net:
qualquer desalinhamento aborta ANTES de gerar features, sem risco de corromper o par texto↔áudio.

Roda com OMP_NUM_THREADS=1 (o fix do deadlock). Uso:
    OMP_NUM_THREADS=1 python3 resume_tagarela_feats.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import soundfile as sf

sys.path.insert(0, "/workspace")
import pyarrow.parquet as pq  # noqa: E402
import torch  # noqa: E402

torch.set_num_threads(1)  # defesa extra além do OMP_NUM_THREADS=1 do env

import prep_tagarela as PT  # noqa: E402  (reusa filtros/constantes — sem duplicar)
from lhotse import (  # noqa: E402
    CutSet,
    Fbank,
    FbankConfig,
    Recording,
    RecordingSet,
    SupervisionSegment,
    SupervisionSet,
)

EXPECTED = 429885  # kept do build_split original (log: "kept=429885")
TDIR = Path("/workspace/icefall/egs/commonvoice/ASR/data/tagarela")
WAV_DIR = TDIR / "wav_train"
PARQUET_DIR = Path("/workspace/tagarela_raw/data")


def reconstruct():
    recs, sups = [], []
    kept = missing = 0
    for shard in PT.iter_parquet_shards(PARQUET_DIR):
        pf = pq.ParquetFile(shard)
        for batch in pf.iter_batches(columns=["audio", "sentence", "accent", "path"]):
            d = batch.to_pydict()
            for audio, sentence, accent in zip(d["audio"], d["sentence"], d["accent"]):
                if accent != PT.ACCENT_KEEP:
                    continue
                text = PT.PI.normalize_ptbr(sentence or "")
                if not text:
                    continue
                if PT.is_hallucinated_text(text):
                    continue
                # bad_ratio: duração via header FLAC (sf.info) — IDÊNTICA a len(arr)/sr, sem decode
                try:
                    dur = sf.info(io.BytesIO(audio["bytes"])).duration
                except Exception:
                    continue  # mesmo caminho do decode_error do original
                cps = len(text) / dur if dur > 0 else 0.0
                if cps < PT.MIN_CPS or cps > PT.MAX_CPS:
                    continue
                cid = f"{PT.CUT_ID_PREFIX}_{kept:08d}"
                wav = WAV_DIR / f"{cid}.wav"
                if not wav.exists():
                    missing += 1
                    if missing <= 5:
                        print(f"[resume] FALTA {wav}", flush=True)
                    continue
                rec = Recording.from_file(str(wav), recording_id=cid)
                recs.append(rec)
                sups.append(SupervisionSegment(
                    id=f"{cid}-0", recording_id=cid, start=0.0, duration=rec.duration,
                    channel=0, language="Portuguese", text=text))
                kept += 1
    return recs, sups, kept, missing


def main():
    recs, sups, kept, missing = reconstruct()
    print(f"[resume] reconstruído: kept={kept} missing={missing}", flush=True)
    assert missing == 0, f"{missing} wavs faltando — build_split incompleto? abortando"
    assert kept == EXPECTED, (
        f"MISALIGN: kept={kept} != {EXPECTED} original — abortando p/ NÃO corromper o par "
        f"texto↔áudio do mux")

    cuts = CutSet.from_manifests(
        recordings=RecordingSet.from_recordings(recs),
        supervisions=SupervisionSet.from_segments(sups))
    cuts = cuts.resample(PT.TARGET_SR)  # no-op p/ 16k; paridade com prepare()
    cuts = cuts.compute_and_store_features(
        extractor=Fbank(FbankConfig(num_mel_bins=80)),
        storage_path=str(TDIR / "feats_train"), num_jobs=8)
    cuts = CutSet.from_cuts(PT._clamp(c) for c in cuts)
    cuts.to_file(str(TDIR / "tagarela_cuts_train.jsonl.gz"))
    hours = sum(c.duration for c in cuts) / 3600.0
    print(f"[resume] {len(cuts)} cuts, {hours:.2f}h [MEDIDO] → tagarela_cuts_train.jsonl.gz",
          flush=True)


if __name__ == "__main__":
    main()
