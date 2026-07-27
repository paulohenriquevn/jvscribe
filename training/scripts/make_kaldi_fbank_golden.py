#!/usr/bin/env python3
"""Gera a referência golden de fbank 80-bin (lhotse) usada pelo teste de
casamento numérico `crates/macaw-audio/tests/kaldi_fbank_golden_test.rs`.

Por que existe: o modelo de produção (`training/results/onnx/model.int8.onnx`)
foi treinado com `Fbank(FbankConfig(num_mel_bins=80))` — a MESMA chamada usada
em `training/prep_mls.py:99` e `training/prep_icefall.py:112` (kaldi/HTK fbank
via `lhotse.features.kaldi`, `torchaudio_compatible_mel_scale=True`, todos os
outros campos no default). Este script roda EXATAMENTE essa chamada sobre a
fixture de áudio versionada (`tests/fixtures/tone_440hz_16k.wav`, determinística
— tom 440 Hz, sox, sem RNG) e grava o resultado como referência binária para o
teste Rust comparar bin-a-bin. `[FONTE-REPO]`: config lida de
`lhotse/features/kaldi/extractors.py:23-44` (FbankConfig) — não usa
torchaudio.compliance.kaldi (torchaudio não está instalado neste ambiente);
lhotse reimplementa o algoritmo Kaldi em PyTorch puro
(`lhotse/features/kaldi/layers.py`), documentado como
"very close to Kaldi's" (docstring do módulo, linha 9-12).

Uso:
    python3 training/scripts/make_kaldi_fbank_golden.py
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import soundfile as sf
from lhotse import Fbank, FbankConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_WAV = REPO_ROOT / "tests" / "fixtures" / "tone_440hz_16k.wav"
GOLDEN_DIR = REPO_ROOT / "crates" / "macaw-audio" / "tests" / "fixtures"
GOLDEN_F32 = GOLDEN_DIR / "kaldi_fbank80_golden.f32"
GOLDEN_META = GOLDEN_DIR / "kaldi_fbank80_golden.meta"


def main() -> None:
    if not FIXTURE_WAV.exists():
        raise SystemExit(
            f"fixture ausente em {FIXTURE_WAV} — rode scripts/make_fixtures.sh primeiro"
        )

    samples, sample_rate = sf.read(str(FIXTURE_WAV), dtype="float32")
    if sample_rate != 16_000:
        raise SystemExit(f"esperado 16 kHz, fixture tem {sample_rate} Hz")

    extractor = Fbank(FbankConfig(num_mel_bins=80))
    # lhotse aceita numpy float32 (samples_channel-major); shape esperado (num_samples,).
    feats = extractor.extract(samples, sampling_rate=sample_rate)
    feats = np.asarray(feats, dtype=np.float32)

    n_frames, n_bins = feats.shape
    assert n_bins == 80, f"esperado 80 bins, veio {n_bins}"

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_F32.write_bytes(feats.tobytes(order="C"))
    GOLDEN_META.write_text(
        f"n_frames={n_frames}\nn_bins={n_bins}\nsample_rate={sample_rate}\n"
        f"num_input_samples={len(samples)}\n"
        f"source_wav=tests/fixtures/tone_440hz_16k.wav\n"
        f"lhotse_config=Fbank(FbankConfig(num_mel_bins=80))\n",
        encoding="utf-8",
    )
    print(f"golden gravado: {GOLDEN_F32} ({n_frames} frames x {n_bins} bins)")
    print(f"meta: {GOLDEN_META}")
    print(f"mean={feats.mean():.6f} std={feats.std():.6f} min={feats.min():.6f} max={feats.max():.6f}")


if __name__ == "__main__":
    main()
