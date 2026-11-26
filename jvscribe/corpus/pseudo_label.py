"""Pseudo-labeling com dois whisper sequenciais (M3 — T3.1, ADR-3).

Dois modelos faster-whisper de tamanhos distintos (ex.: small + medium) geram cada
um sua hipótese PT-BR. Reusa o padrão de `scripts/baseline_fleurs_ptbr.py:81,84,86`
(`[FONTE-REPO]`). Carga **sequencial** — um modelo por vez, liberado antes do
próximo (EC-3: RAM apertada; nunca 2 modelos residentes).

Caveat honesto (ADR-3): dois whisper parentes correlacionam erros → a concordância
superestima confiança. Um segundo transcritor de arquitetura distinta (parakeet) é
backlog técnico (Blueprint § Corner 3/Q7).
"""

from __future__ import annotations

import gc
from collections.abc import Callable

from faster_whisper import WhisperModel


def _transcribe_all(model: "WhisperModel", audio_paths: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for clip_id, path in audio_paths.items():
        segments, _info = model.transcribe(path, language="pt", beam_size=1)
        out[clip_id] = " ".join(seg.text.strip() for seg in segments).strip()
    return out


def transcribe_pair(
    audio_paths: dict[str, str],
    sizes: tuple[str, str] = ("small", "medium"),
    on_load: Callable[[str], None] | None = None,
    on_release: Callable[[str], None] | None = None,
) -> dict[str, tuple[str, str]]:
    """Transcreve cada áudio com 2 whisper distintos, SEQUENCIALMENTE (RAM-safe).

    Carrega um modelo por vez, libera (`del` + `gc.collect()`) ANTES de instanciar o
    próximo (EC-3: RAM apertada; nunca 2 residentes). Os hooks `on_load(size)` /
    `on_release(size)` tornam o ciclo de vida observável para teste sem depender de
    `__del__`/refcount (review M-4). Retorna {clip_id: (hyp_modelo1, hyp_modelo2)}.
    Fail-fast em entrada vazia.
    """
    if not audio_paths:
        raise ValueError("transcribe_pair: nenhum áudio fornecido")

    hyps_por_modelo: list[dict[str, str]] = []
    for size in sizes:
        model = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=1)
        if on_load is not None:
            on_load(size)
        hyps_por_modelo.append(_transcribe_all(model, audio_paths))
        del model  # libera ANTES de instanciar o próximo (EC-3 RAM)
        gc.collect()
        if on_release is not None:
            on_release(size)

    return {
        clip_id: (hyps_por_modelo[0][clip_id], hyps_por_modelo[1][clip_id])
        for clip_id in audio_paths
    }
