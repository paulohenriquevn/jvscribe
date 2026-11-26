"""Prepara o CORAA-v1.1 (fala espontânea PT-BR) no formato do datamodule REAL do icefall
(fase de dados de M5). Roda NA instância.

CORAA (gabrielrstan/CORAA-v1.1, ~290,77h humano-validado) agrega 5 subcorpora de fala
espontânea/preparada: NURC-Recife, ALIP, SP2010, C-ORAL-BRASIL I, TEDx. É o corpus-chave
de M5 para hitar o WER espontâneo — o MLS-PT de M4 é fala lida de audiobook.

Emite `cv-pt_cuts_{split}.jsonl.gz` + fbank 80-dim, o mesmo contrato de
`prep_icefall.py`, então `zipformer/train.py --language pt
--cv-manifest-dir {out}` roda SEM modificação.

Reuso (Regra 9 — sem duplicar):
  - `prep_icefall.normalize_ptbr`  → mesma normalização do treino de M4 (audit D2).
  - `lhotse.Fbank(FbankConfig(num_mel_bins=80))` → mesmo extractor do treino.

Layout de entrada esperado (após `unzip {split}.zip` no --audio-root):
  {audio-root}/{split}/sp/{idx}_sp_.wav   (o file_path do CSV é relativo ao audio-root)

INVARIANTE DO PROJETO: este script usa APENAS a transcrição humana do CSV do CORAA.
NUNCA gera pseudo-label. O split test é o anchor de eval espontâneo de M5.

Splits oficiais do CORAA (paper arXiv:2110.15731, Tab.4) [LITERATURA]:
  train=273,51h  dev=5,91h  test=11,35h  (total 290,77h). As horas MEDIDAS são
  emitidas por este script ao preparar cada split (duração somada dos cuts).

Uso (na instância):
  unzip -q dev.zip -d /workspace/coraa_work/audio
  unzip -q test.zip -d /workspace/coraa_work/audio
  python3 prep_coraa.py --out data/coraa \
      --audio-root /workspace/coraa_work/audio \
      --meta-dir /workspace/coraa_work \
      --splits dev test --num-jobs 8
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from lhotse import CutSet, Fbank, FbankConfig, Recording, SupervisionSegment, SupervisionSet
from lhotse.features.io import LilcomChunkyWriter
from lhotse.audio import RecordingSet
from lhotse.utils import fastcopy

import prep_icefall as PI  # reusa normalize_ptbr — sem duplicar (audit D2)

TARGET_SR = 16000  # mesma taxa do treino de M4 (MLS/FLEURS 16k); fbank misturando SR é bug

# nome do CSV por split (o dataset usa "final")
META_CSV = "metadata_{split}_final.csv"


def _clamp(c):
    """Supervisão não pode exceder a duração do cut (fbank arredonda num_frames p/ baixo).
    Mesma correção de prep_icefall — glue do lhotse, não regra de negócio."""
    return fastcopy(c, supervisions=[
        fastcopy(sp, duration=round(c.duration - sp.start, 4))
        if sp.start + sp.duration > c.duration else sp
        for sp in c.supervisions])


def read_rows(meta_dir: Path, split: str):
    """Lê o CSV do CORAA via módulo csv (sem depender de pandas na instância)."""
    path = meta_dir / META_CSV.format(split=split)
    if not path.exists():
        raise FileNotFoundError(f"metadata do CORAA não encontrado: {path}")
    with path.open(encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def build_split(split: str, audio_root: Path, meta_dir: Path,
                min_net_votes: int | None, limit: int | None):
    """Constrói Recording+Supervision para um split do CORAA a partir do CSV+wav.

    min_net_votes: se dado, mantém só segs com (up_votes - down_votes) >= min_net_votes.
      DEFAULT None (mantém o split oficial intacto — obrigatório p/ dev/test = anchor de
      eval comparável ao benchmark publicado). Só usar em train-side.
    """
    recs, sups = [], []
    n_total = n_kept = n_missing = n_empty = n_filtered = 0
    for row in read_rows(meta_dir, split):
        n_total += 1
        if limit is not None and n_kept >= limit:
            break
        text = PI.normalize_ptbr(row.get("text", ""))
        if not text:
            n_empty += 1
            continue
        if min_net_votes is not None:
            up = int(row.get("up_votes", 0) or 0)
            down = int(row.get("down_votes", 0) or 0)
            if (up - down) < min_net_votes:
                n_filtered += 1
                continue
        wav = audio_root / row["file_path"]
        if not wav.exists():
            n_missing += 1
            continue
        cid = f"coraa_{split}_{n_kept:07d}"
        rec = Recording.from_file(str(wav), recording_id=cid)
        recs.append(rec)
        sups.append(SupervisionSegment(
            id=f"{cid}-0", recording_id=cid, start=0.0, duration=rec.duration,
            channel=0, language="Portuguese", text=text))
        n_kept += 1
    print(f"[coraa] {split}: total={n_total} kept={n_kept} missing_wav={n_missing} "
          f"empty_text={n_empty} filtered_votes={n_filtered}", flush=True)
    if n_missing and n_kept == 0:
        raise RuntimeError(
            f"[coraa] {split}: 0 wav encontrado sob {audio_root} — extraiu o {split}.zip? "
            f"file_path esperado ex.: {audio_root / (split + '/sp/…_sp_.wav')}")
    return recs, sups


def prepare(split: str, audio_root: Path, meta_dir: Path, out: Path, extractor,
            num_jobs: int, min_net_votes: int | None, limit: int | None):
    recs, sups = build_split(split, audio_root, meta_dir, min_net_votes, limit)
    cuts = CutSet.from_manifests(
        recordings=RecordingSet.from_recordings(recs),
        supervisions=SupervisionSet.from_segments(sups))
    cuts = cuts.resample(TARGET_SR)  # garante 16k = distribuição do treino
        # `storage_type` EXPLÍCITO: o default do lhotse é `numpy_files`, que grava
        # **115 MB por hora** de áudio contra **33 MB** do `lilcom_chunky` `[MEDIDO]`
        # (`wiki/medicoes/m10-t3-fbank-e-storage.md`). Em 5.000 h a diferença é de ~410 GB,
        # e o lhotse não avisa — ele apenas grava maior.
    cuts = cuts.compute_and_store_features(
        extractor=extractor, storage_path=str(out / f"feats_{split}"), num_jobs=num_jobs,
        storage_type=LilcomChunkyWriter)
    cuts = CutSet.from_cuts(_clamp(c) for c in cuts)
    cuts.to_file(str(out / f"cv-pt_cuts_{split}.jsonl.gz"))
    hours = sum(c.duration for c in cuts) / 3600.0
    print(f"[coraa] {split}: {len(cuts)} cuts, {hours:.2f}h [MEDIDO] "
          f"→ cv-pt_cuts_{split}.jsonl.gz", flush=True)
    return [sp.text for sp in sups], hours


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/coraa")
    ap.add_argument("--audio-root", required=True,
                    help="dir onde os {split}.zip foram extraídos (contém train/ dev/ test/)")
    ap.add_argument("--meta-dir", required=True, help="dir com metadata_{split}_final.csv")
    ap.add_argument("--splits", nargs="+", default=["dev", "test"])
    ap.add_argument("--num-jobs", type=int, default=8)
    ap.add_argument("--min-net-votes", type=int, default=None,
                    help="filtro train-side (up-down>=N). NUNCA usar em dev/test (anchor).")
    ap.add_argument("--limit", type=int, default=None, help="máx utts por split (smoke)")
    args = ap.parse_args()

    # guarda-corpo do invariante: filtro de voto proibido no anchor de eval
    if args.min_net_votes is not None and any(s in ("dev", "test") for s in args.splits):
        sys.exit("[coraa] ERRO: --min-net-votes altera o split oficial; proibido em dev/test "
                 "(anchor de eval de M5, invariante do projeto). Rode dev/test sem o filtro.")

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    audio_root = Path(args.audio_root)
    meta_dir = Path(args.meta_dir)
    extractor = Fbank(FbankConfig(num_mel_bins=80))

    all_train_text = []
    for split in args.splits:
        texts, _ = prepare(split, audio_root, meta_dir, out, extractor,
                           args.num_jobs, args.min_net_votes, args.limit)
        if split == "train":
            all_train_text = texts
    if all_train_text:
        (out / "transcript_words.txt").write_text(
            "\n".join(all_train_text) + "\n", encoding="utf-8")
    print(f"[coraa] pronto em {out} (formato datamodule commonvoice)", flush=True)


if __name__ == "__main__":
    main()
