"""Fase 4 — corpus no formato de manifest do NeMo p/ o 2º finalista (FastConformer-CTC).

train = MLS-PT ~161h, dev/test = FLEURS held-out humano — MESMO corpus/test que o
Zipformer (comparação justa). Reusa `download_extract_mls`+`prepare_mls` e o `build` do
FLEURS do prep_mls/prep_icefall (Regra 9). Emite JSONL do NeMo
`{audio_filepath, duration, text}` — NeMo computa features on-the-fly (sem fbank).

Roda NA instância NeMo (precisa de lhotse: pip install lhotse; HF_TOKEN p/ o FLEURS).
Uso: python3 prep_nemo.py --out data_nemo --work /workspace/mls_work
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lhotse.recipes import prepare_mls

import prep_icefall as PI  # normalize_ptbr + build(FLEURS)
from prep_mls import download_extract_mls


def _write(path: Path, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _entry(rec, text: str) -> dict | None:
    text = PI.normalize_ptbr(text)
    if not text:
        return None
    return {"audio_filepath": rec.sources[0].source,
            "duration": round(rec.duration, 3), "text": text}


def mls_train_entries(work: Path, num_jobs: int) -> list[dict]:
    corpus = download_extract_mls(work)
    m = prepare_mls(corpus, opus=True, num_jobs=num_jobs)
    lang = next(iter(m))
    tr = m[lang]["train"]
    recs = {r.id: r for r in tr["recordings"]}
    out = []
    for s in tr["supervisions"]:
        e = _entry(recs[s.recording_id], s.text)
        if e:
            out.append(e)
    return out


def fleurs_entries(split_key: str, out_dir: Path) -> list[dict]:
    recs, sups, _ = PI.build("fleurs", split_key, out_dir, 0, None)  # grava wavs
    rd = {r.id: r for r in recs}
    out = []
    for s in sups:
        e = _entry(rd[s.recording_id], s.text)
        if e:
            out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data_nemo")
    ap.add_argument("--work", default="/workspace/mls_work")
    ap.add_argument("--num-jobs", type=int, default=8)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    train = mls_train_entries(Path(args.work), args.num_jobs)
    _write(out / "train.json", train)
    print(f"[nemo] train: {len(train)} utts → train.json", flush=True)
    for split in ("dev", "test"):
        ent = fleurs_entries(split, out)
        _write(out / f"{split}.json", ent)
        print(f"[nemo] {split}: {len(ent)} utts → {split}.json", flush=True)

    (out / "transcript.txt").write_text(
        "\n".join(e["text"] for e in train) + "\n", encoding="utf-8")
    print(f"[nemo] pronto em {out} (train=MLS-PT, dev/test=FLEURS)", flush=True)


if __name__ == "__main__":
    main()
