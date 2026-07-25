"""Corpus de DECISÃO de M4 (fase 1): train = MLS-PT ~161h, dev/test = FLEURS held-out humano.

Roda NA instância. Emite `cv-pt_cuts_{train,dev,test}.jsonl.gz` + fbank no formato do
datamodule REAL do icefall — mesmo contrato do `prep_icefall.py`, então
`zipformer/train.py --language pt --cv-manifest-dir data/pt` roda sem modificação.

- **train** = MLS-PT (~161h, CC-BY, transcrição humana) via `lhotse.recipes.prepare_mls`
  (Regra 9 — a recipe do lhotse já lê o layout OpenSLR tar/opus; não reimplementamos).
- **dev/test** = FLEURS pt_br (humano), reusando `prep_icefall.build` (mesmo held-out do
  piloto, para comparar arquiteturas no MESMO test set).

Uso (na instância, HF_TOKEN no ambiente p/ o FLEURS):
  python3 prep_mls.py --out data/pt --num-jobs 8
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
from pathlib import Path

from lhotse import CutSet, Fbank, FbankConfig, SupervisionSet
from lhotse.recipes import prepare_mls
from lhotse.utils import fastcopy

import prep_icefall as PI  # reusa normalize_ptbr + build(FLEURS) — sem duplicar (audit D2)

# MLS opus (menor que flac) hospedado pela Meta; layout OpenSLR que o prepare_mls lê.
MLS_URL = "https://dl.fbaipublicfiles.com/mls/mls_portuguese_opus.tar.gz"


def _clamp(c):
    """Mesma correção do prep_icefall: supervisão não pode exceder a duração do cut
    (fbank arredonda num_frames para baixo). Glue do lhotse, não regra de negócio."""
    return fastcopy(c, supervisions=[
        fastcopy(sp, duration=round(c.duration - sp.start, 4))
        if sp.start + sp.duration > c.duration else sp
        for sp in c.supervisions])


def download_extract_mls(work: Path) -> Path:
    corpus = work / "mls_portuguese"
    if (corpus / "train").exists():
        return corpus
    tar = work / "mls_portuguese_opus.tar.gz"
    if not tar.exists():
        print(f"[mls] baixando {MLS_URL} ...", flush=True)
        subprocess.run(["curl", "-sfL", "--retry", "3", MLS_URL, "-o", str(tar)], check=True)
    print("[mls] extraindo ...", flush=True)
    with tarfile.open(tar) as t:
        t.extractall(work)
    return corpus


def mls_train(work: Path, out: Path, extractor, num_jobs: int) -> list[str]:
    corpus = download_extract_mls(work)
    manifests = prepare_mls(corpus, opus=True, num_jobs=num_jobs)
    # {split: {language: {recordings, supervisions}}} — um só idioma (portuguese)
    tr = manifests["train"]
    lang_key = next(iter(tr))
    recs = tr[lang_key]["recordings"]
    sups = SupervisionSet.from_segments(
        fastcopy(s, text=PI.normalize_ptbr(s.text)) for s in tr[lang_key]["supervisions"])
    cuts = CutSet.from_manifests(recordings=recs, supervisions=sups)
    cuts = cuts.compute_and_store_features(
        extractor=extractor, storage_path=str(out / "feats_train"), num_jobs=num_jobs)
    cuts = CutSet.from_cuts(_clamp(c) for c in cuts)
    cuts.to_file(str(out / "cv-pt_cuts_train.jsonl.gz"))
    print(f"[mls] train: {len(cuts)} cuts → cv-pt_cuts_train.jsonl.gz", flush=True)
    return [s.text for s in sups]


def fleurs_split(split_key: str, out: Path, extractor, num_jobs: int):
    """dev/test do FLEURS reusando o build do prep_icefall (mesmo held-out do piloto)."""
    recs, sups, _ = PI.build("fleurs", split_key, out, 0, None)
    from lhotse.audio import RecordingSet
    cuts = CutSet.from_manifests(recordings=RecordingSet.from_recordings(recs),
                                 supervisions=SupervisionSet.from_segments(sups))
    cuts = cuts.compute_and_store_features(
        extractor=extractor, storage_path=str(out / f"feats_{split_key}"), num_jobs=num_jobs)
    cuts = CutSet.from_cuts(_clamp(c) for c in cuts)
    cuts.to_file(str(out / f"cv-pt_cuts_{split_key}.jsonl.gz"))
    print(f"[fleurs] {split_key}: {len(cuts)} cuts → cv-pt_cuts_{split_key}.jsonl.gz", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/pt")
    ap.add_argument("--work", default=os.environ.get("MLS_WORK", "/workspace/mls_work"))
    ap.add_argument("--num-jobs", type=int, default=8)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    extractor = Fbank(FbankConfig(num_mel_bins=80))

    train_text = mls_train(work, out, extractor, args.num_jobs)
    for split in ("dev", "test"):
        fleurs_split(split, out, extractor, args.num_jobs)

    (out / "transcript_words.txt").write_text("\n".join(train_text) + "\n", encoding="utf-8")
    print(f"[icefall] pronto em {out} — train=MLS-PT, dev/test=FLEURS (datamodule commonvoice)", flush=True)


if __name__ == "__main__":
    main()
