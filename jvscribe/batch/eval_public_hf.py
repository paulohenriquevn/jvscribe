#!/usr/bin/env python3
"""Mede WER do `batch_transcribe` num dataset PÚBLICO do HF (FLEURS pt_br).

Fala lida, banda larga (~128 kbps). Pega os bytes crus (`decode=False`, sem torchcodec), grava
como arquivos, roda o pipeline de lote e compara com a referência humana.

Uso:
    python3 jvscribe/batch/eval_public_hf.py --n 100
    python3 jvscribe/batch/eval_public_hf.py --n 919 --json resultado.json

⚠️ **A régua de normalização é a canônica do projeto**, não uma local. A versão anterior deste
script tinha a própria `norm()`, que **preservava acentos** enquanto
`normalize_for_wer_compare` os remove. Consequência medida: o WER de **16,14%** publicado em
`jvscribe/results/public-benchmarks.md` saiu daqui, e os **15,99%** medidos com a régua
canônica no mesmo subconjunto — a diferença **não era ruído de amostra, era régua diferente**.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

from artifact import default_model_path, default_sibling  # noqa: E402
from batch_transcribe import transcribe_folder  # noqa: E402
from text_normalize_ptbr import normalize_for_wer_compare  # noqa: E402


def baixar_amostras(destino: pathlib.Path, n: int) -> dict[str, str]:
    """Grava `n` áudios do FLEURS pt_br test e devolve `{id: transcrição de referência}`."""
    from datasets import Audio, load_dataset

    destino.mkdir(parents=True, exist_ok=True)
    ds = load_dataset("google/fleurs", "pt_br", split="test", streaming=True)
    ds = ds.cast_column("audio", Audio(decode=False))

    refs: dict[str, str] = {}
    for i, ex in enumerate(ds):
        if i >= n:
            break
        b = ex["audio"]["bytes"]
        if b is None:                       # às vezes o dataset entrega caminho em vez de bytes
            b = pathlib.Path(ex["audio"]["path"]).read_bytes()
        fid = f"utt{i:04d}"
        (destino / f"{fid}.wav").write_bytes(b)
        refs[fid] = ex["transcription"]
    return refs


def medir(refs: dict[str, str], saida: pathlib.Path) -> tuple[list[str], list[str]]:
    """Pareia referência e hipótese, ambas na régua CANÔNICA. Ignora referência vazia."""
    R, H = [], []
    for fid, ref in refs.items():
        arq = saida / f"{fid}.txt"
        hyp = arq.read_text(encoding="utf-8").strip() if arq.exists() else ""
        rn = normalize_for_wer_compare(ref)
        if rn:
            R.append(rn)
            H.append(normalize_for_wer_compare(hyp))
    return R, H


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=100, help="quantas utterances do test set")
    ap.add_argument("--model", default=None, help="default: o artefato canônico (model_card.json)")
    ap.add_argument("--tokens", default=None)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--json", type=pathlib.Path, default=None, help="grava o resultado")
    a = ap.parse_args()

    if a.n < 1:
        raise SystemExit(f"--n tem de ser >= 1, veio {a.n}")

    import jiwer

    modelo = a.model or default_model_path()
    tokens = a.tokens or default_sibling("tokens.txt")

    # `TemporaryDirectory` como context manager: a versão anterior usava `mkdtemp` sem cleanup
    # e cada execução deixava N wavs mais as transcrições em /tmp.
    with tempfile.TemporaryDirectory(prefix="fleurs_eval_") as tmp:
        base = pathlib.Path(tmp)
        aud, out = base / "aud", base / "out"

        refs = baixar_amostras(aud, a.n)
        print(f"[fleurs] {len(refs)} amostras gravadas · modelo: {modelo}", flush=True)

        s = transcribe_folder(str(aud), str(out), modelo, tokens,
                              batch=a.batch, workers=a.workers, threads=a.threads)
        R, H = medir(refs, out)

    o = jiwer.process_words(R, H)
    palavras = o.hits + o.substitutions + o.deletions
    resultado = {
        "dataset": "google/fleurs pt_br test",
        "modelo": modelo,
        "regua": "normalize_for_wer_compare (canônica — remove acento)",
        "n": len(R),
        "ref_words": palavras,
        "WER_pct": round(o.wer * 100, 2),
        "hits_pct": round(100 * o.hits / palavras, 1),
        "sub_pct": round(100 * o.substitutions / palavras, 1),
        "del_pct": round(100 * o.deletions / palavras, 1),
        "ins_pct": round(100 * o.insertions / palavras, 1),
        "audio_sec": s["audio_sec"],
        "wall_sec": s["wall_sec"],
        "rtfx": s["rtfx_agregado"],
    }
    saida = json.dumps(resultado, ensure_ascii=False, indent=2)
    print(saida)
    if a.json:
        a.json.write_text(saida + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
