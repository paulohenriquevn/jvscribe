"""Manifests Lhotse com augmentação telefônica on-the-fly (M3 — T4.1, ADR-4).

Fluxo verificado no blueprint (§ Corner 3/Q6, `[FONTE-REPO]`):
  RecordingSet.from_dir → SupervisionSet.from_segments(text=pseudo_label) → CutSet.from_manifests

O texto do pseudo-label entra exclusivamente em `SupervisionSegment.text`. A
augmentação telefônica é aplicada **on-the-fly** por `load_telephone_audio` — no
carregamento sob demanda (equivalente ao `input_transform` do dataloader recomendado
no blueprint § Corner 4/Q2), nunca materializando o áudio aumentado em disco. O
`AudioTransform` nativo do lhotse não é usado porque a cadeia muda o sample rate
(16k→8k) e inclui banda+A-law sem equivalente nativo (evita reimplementar
`reverse_timestamps`).
"""

from __future__ import annotations

import numpy as np
from lhotse import CutSet, RecordingSet, SupervisionSegment, SupervisionSet

from corpus.telephone_channel import apply_telephone_channel


def build_cutset(wav_dir: str, labels: dict[str, str]) -> CutSet:
    """Constrói um CutSet a partir de um diretório de WAVs + pseudo-labels.

    `labels` mapeia o id da gravação (stem do arquivo) → texto do pseudo-label.
    Fail-fast se um recording não tiver label correspondente.
    """
    if not labels:
        raise ValueError("build_cutset: dicionário de labels vazio")

    recordings = RecordingSet.from_dir(wav_dir, pattern="*.wav")

    def _label_for(rec_id: str) -> str:
        # tolera tanto o id do lhotse quanto o stem do arquivo
        stem = rec_id.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if rec_id in labels:
            return labels[rec_id]
        if stem in labels:
            return labels[stem]
        raise KeyError(f"build_cutset: sem label para recording '{rec_id}'")

    supervisions = SupervisionSet.from_segments(
        SupervisionSegment(
            id=f"{rec.id}-0",
            recording_id=rec.id,
            start=0.0,
            duration=rec.duration,
            language="pt",
            text=_label_for(rec.id),
        )
        for rec in recordings
    )

    return CutSet.from_manifests(recordings=recordings, supervisions=supervisions)


def load_telephone_audio(cut) -> tuple[np.ndarray, int]:
    """Carrega o áudio do cut e aplica a cadeia telefônica ON-THE-FLY (8 kHz).

    Nunca escreve o áudio aumentado em disco — é gerado sob demanda, como faria o
    dataloader por batch. Retorna (áudio 8 kHz float32, 8000).
    """
    samples = cut.load_audio()  # (channels, n) @ sr original
    mono = samples[0] if samples.ndim > 1 else samples
    return apply_telephone_channel(np.asarray(mono, dtype=np.float32), int(cut.sampling_rate))
