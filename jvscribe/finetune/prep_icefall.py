from __future__ import annotations
import sys
import pathlib
"""Prepara o corpus no formato do datamodule REAL do icefall (M4 — piloto). Roda NA GPU.

O ÚNICO código nosso para o piloto (o resto é a recipe real do icefall — Regra 9). Emite
`cv-{lang}_cuts_{train,dev,test}.jsonl.gz` + fbank 80-dim, exatamente o que
`asr_datamodule.CommonVoiceAsrDataModule` carrega (`load_manifest_lazy(cv-{lang}_cuts_{split})`).
Assim `zipformer/train.py --use-ctc 1 --use-transducer 0 --language {lang}` roda SEM
modificação na recipe.

Multi-fonte para ~161h+ (piloto que generaliza, ao contrário do smoke de 1h):
  - FLEURS pt_br (~10h, CC-BY) — parquet HF
  - MLS-PT (~161h, CC-BY) — parquet HF (facebook/multilingual_librispeech, config portuguese)

Uso (na instância, HF_TOKEN no ambiente):
  python3 prep_icefall.py --out data/pt --lang pt --sources fleurs mls
"""


import argparse
import io
import os
import subprocess
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf
from lhotse import CutSet, Fbank, FbankConfig, Recording, SupervisionSegment, SupervisionSet
from lhotse.audio import RecordingSet
from lhotse.utils import fastcopy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
# `normalize_train_target` PRESERVA acento — é o alvo de treino, e o modelo precisa
# aprender a escrever com acento. NÃO trocar pela régua de comparação de WER, que os
# remove: são duas semânticas distintas, e `common/text.py` expõe as duas de propósito.
from text import normalize_train_target as normalize_ptbr  # noqa: E402

PQ_DIR = os.environ.get("PARQUET_DIR", "/workspace/pq")
_TOK = os.environ.get("HF_TOKEN", "")

# (repo, config-path-template, splits) por fonte. text_col difere por dataset.
SOURCES = {
    "fleurs": dict(repo="google/fleurs",
                   path="parquet-data/pt_br/{split}-00000-of-00001.parquet",
                   splits={"train": "train", "dev": "validation", "test": "test"},
                   text_col="transcription"),
    "mls": dict(repo="facebook/multilingual_librispeech",
                path="data/portuguese/{split}/*.parquet",
                splits={"train": "train", "dev": "dev", "test": "test"},
                text_col="transcript"),
}



def _download(repo: str, path: str, dest: str) -> str:
    """curl direto (HF migrou p/ xet; resolve/main + token é o caminho robusto)."""
    if os.path.exists(dest):
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)  # PQ_DIR pode não existir ainda
    url = f"https://huggingface.co/datasets/{repo}/resolve/main/{path}"
    subprocess.run(["curl", "-sfL", "--retry", "3", "-H", f"Authorization: Bearer {_TOK}",
                    url, "-o", dest], check=True)  # -f: falha explícita em HTTP 4xx/5xx
    return dest


def build(source: str, split_key: str, out: Path, n_start: int,
          limit: int | None = None) -> tuple[list, list, int]:
    cfg = SOURCES[source]
    hf_split = cfg["splits"][split_key]
    pqfile = _download(cfg["repo"], cfg["path"].format(split=hf_split),
                       os.path.join(PQ_DIR, f"{source}_{split_key}.parquet"))
    wav_dir = out / "wav" / f"{source}_{split_key}"
    wav_dir.mkdir(parents=True, exist_ok=True)
    recs, sups = [], []
    n = n_start
    pf = pq.ParquetFile(pqfile)
    cols = ["audio", cfg["text_col"]]
    for batch in pf.iter_batches(batch_size=64, columns=cols):
        d = batch.to_pydict()
        for i in range(len(d[cfg["text_col"]])):
            if limit is not None and (n - n_start) >= limit:
                return recs, sups, n
            raw = d["audio"][i].get("bytes")
            text = normalize_ptbr(d[cfg["text_col"]][i])
            if not raw or not text:
                continue
            arr, sr = sf.read(io.BytesIO(raw), dtype="float32")
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            cid = f"{source}_{split_key}_{n:07d}"
            wav = wav_dir / f"{cid}.wav"
            sf.write(str(wav), arr, sr)
            rec = Recording.from_file(str(wav), recording_id=cid)
            recs.append(rec)
            sups.append(SupervisionSegment(id=f"{cid}-0", recording_id=cid, start=0.0,
                                           duration=rec.duration, channel=0,
                                           language="Portuguese", text=text))
            n += 1
    return recs, sups, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/pt")
    ap.add_argument("--lang", default="pt")
    ap.add_argument("--sources", nargs="+", default=["fleurs", "mls"])
    ap.add_argument("--limit", type=int, default=None, help="máx utts por fonte/split (teste)")
    ap.add_argument("--num-jobs", type=int, default=1,
                    help="paralelismo do fbank (1 no piloto de ~10h; subir p/ o prep de ~500h de M5)")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    extractor = Fbank(FbankConfig(num_mel_bins=80))
    all_train_text = []
    for split_key in ("train", "dev", "test"):
        recs, sups, n = [], [], 0
        for source in args.sources:
            # dev/test só do FLEURS (limpo, humano); train combina todas as fontes
            if split_key in ("dev", "test") and source != "fleurs":
                continue
            r, s, n = build(source, split_key, out, n, args.limit)
            recs += r; sups += s
        cuts = CutSet.from_manifests(recordings=RecordingSet.from_recordings(recs),
                                     supervisions=SupervisionSet.from_segments(sups))
        cuts = cuts.compute_and_store_features(extractor=extractor,
                                               storage_path=str(out / f"feats_{split_key}"),
                                               num_jobs=args.num_jobs)
        cuts = CutSet.from_cuts(
            fastcopy(c, supervisions=[
                fastcopy(sp, duration=round(c.duration - sp.start, 4))
                if sp.start + sp.duration > c.duration else sp
                for sp in c.supervisions]) for c in cuts)
        cuts.to_file(str(out / f"cv-{args.lang}_cuts_{split_key}.jsonl.gz"))
        if split_key == "train":
            all_train_text = [sp.text for sp in sups]
        print(f"[icefall] {split_key}: {len(recs)} cuts → cv-{args.lang}_cuts_{split_key}.jsonl.gz", flush=True)
    (out / "transcript_words.txt").write_text("\n".join(all_train_text) + "\n", encoding="utf-8")
    print(f"[icefall] pronto em {out} (formato do datamodule commonvoice)", flush=True)


if __name__ == "__main__":
    main()
