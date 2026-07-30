#!/usr/bin/env python3
"""Extrai o wav 16 kHz da MESMA utterance FLEURS pt_br usada por
`training/results/onnx/fleurs_one.f32`/`fleurs_one.txt` (consumidos por
`crates/macaw-asr/tests/real_speech_test.rs`), para fechar o teste end-to-end
real (wav → `macaw_audio::kaldi_fbank` → `AsrEngine::transcribe`) em
`crates/macaw-asr/tests/real_speech_from_wav_test.rs`.

Por que não versionamos o wav resultante: mesma decisão já registrada em
`real_speech_test.rs` para `fleurs_one.f32` — dado derivado do FLEURS (licença
CC-BY-4.0, mas redistribuição de áudio bruto fora do escopo deste repo). O teste
que o consome usa `#[ignore]` + checagem de existência, igual aos demais
fixtures de fala real "não versionados".

Localiza a utterance por casamento do início da transcrição normalizada (a
mesma lida em `fleurs_one.txt`) dentro do parquet de teste do FLEURS pt_br
(cache local do `huggingface_hub`, o mesmo usado por `training/smoke/prep_fleurs.py`).

Uso:
    python3 training/tools/extract_fleurs_one_wav.py
"""
from __future__ import annotations

import glob
import io
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_TXT = REPO_ROOT / "training" / "results" / "onnx" / "fleurs_one.txt"
OUT_WAV = REPO_ROOT / "crates" / "macaw-audio" / "tests" / "fixtures" / "fleurs_one_16k.wav"


def find_test_parquet() -> Path:
    candidates = list(
        Path.home().glob(
            ".cache/huggingface/hub/datasets--google--fleurs/snapshots/*/parquet-data/pt_br/test-*.parquet"
        )
    )
    if not candidates:
        raise SystemExit(
            "parquet de teste do FLEURS pt_br não encontrado no cache local "
            "(~/.cache/huggingface/hub/datasets--google--fleurs/...). Baixe primeiro "
            "com `datasets.load_dataset('google/fleurs', 'pt_br')` ou aponte "
            "FLEURS_PARQUET manualmente."
        )
    return candidates[0]


def main() -> None:
    if not REFERENCE_TXT.exists():
        raise SystemExit(f"referência ausente: {REFERENCE_TXT}")
    reference = REFERENCE_TXT.read_text(encoding="utf-8").strip().lower()
    needle = reference[:30]

    parquet_path = find_test_parquet()
    pf = pq.ParquetFile(parquet_path)

    found = None
    for batch in pf.iter_batches(batch_size=64, columns=["id", "audio", "transcription"]):
        d = batch.to_pydict()
        for i in range(len(d["id"])):
            text = (d["transcription"][i] or "").strip().lower()
            if needle in text:
                found = d["audio"][i]
                break
        if found:
            break

    if found is None:
        raise SystemExit(
            f"nenhuma utterance do FLEURS pt_br test casa com o início de "
            f"'{needle}' — a referência local pode ter mudado"
        )

    arr, sr = sf.read(io.BytesIO(found["bytes"]), dtype="float32")
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    if sr != 16_000:
        raise SystemExit(f"esperado 16 kHz, utterance encontrada tem {sr} Hz")

    OUT_WAV.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(OUT_WAV), arr, sr, subtype="PCM_16")
    print(f"gravado: {OUT_WAV} ({len(arr)} amostras, {len(arr) / sr:.2f}s)")


if __name__ == "__main__":
    main()
