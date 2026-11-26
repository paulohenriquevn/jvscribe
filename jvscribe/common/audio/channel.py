"""Augmentação telefônica on-the-fly em memória (M3 — T1.1, ADR-1).

Cadeia G.711 do canal de call center brasileiro (canal de call center do projeto), toda em RAM —
NUNCA materializa WAV em disco (DoD item 3):

  1. resample 16k→8k        (scipy.signal.resample_poly — com anti-aliasing)
  2. passa-banda 300-3400 Hz (scipy.signal.butter SOS ordem 4 — numericamente estável)
  3. G.711 A-law round-trip  (audioop.lin2alaw/alaw2lin — encode→decode)

Não usa sox/subprocess/tempfile, ao contrário de `common/audio/augment.sh` (M1),
que é a referência DSP. Aplicável como transform on-the-fly num dataloader.
Blueprint m3-corpus § Corner 4/Q2 (`[FONTE-REPO]` scipy+audioop; o `Narrowband`
nativo do lhotse não cobre A-law nem banda).
"""

from __future__ import annotations

from math import gcd

import numpy as np
from scipy.signal import butter, resample_poly, sosfilt

try:  # PEP 594: audioop foi removido no Python 3.13+
    import audioop
except ImportError:  # pragma: no cover - depende da versão do interpretador
    try:
        import audioop_lts as audioop  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "audioop ausente (Python 3.13+ o removeu — PEP 594). "
            "Instale 'audioop-lts' para a augmentação G.711 A-law."
        ) from exc

TELEPHONE_SR = 8000
_BAND_HZ = (300.0, 3400.0)
_BUTTER_ORDER = 4


def _to_int16_bytes(x: np.ndarray) -> bytes:
    """float [-1,1] → PCM int16 little-endian bytes (o formato que audioop espera)."""
    clipped = np.clip(x, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


def _from_int16_bytes(raw: bytes) -> np.ndarray:
    """PCM int16 bytes → float32 [-1,1]."""
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0


def apply_band(samples: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """Resample 16k→8k + passa-banda 300-3400 Hz (SEM codec); retorna (float32 8 kHz, 8000).

    Extraído para o codec ser plugável (M5 codec-pool, ADR D3/D4): a banda é o canal físico,
    o codec (G.711/GSM/Opus) é sorteado à parte. Fail-fast em entrada vazia (error-handling.md).
    """
    if samples is None or getattr(samples, "size", 0) == 0:
        raise ValueError("apply_band: array de áudio vazio")
    x = np.asarray(samples, dtype=np.float32)
    # 1. resample 16k→8k (resample_poly já faz anti-aliasing)
    if sr != TELEPHONE_SR:
        g = gcd(int(sr), TELEPHONE_SR)
        x = resample_poly(x, TELEPHONE_SR // g, int(sr) // g).astype(np.float32)
    # 2. passa-banda 300-3400 Hz @ 8 kHz — SOS ordem 4 (estável em banda estreita)
    sos = butter(_BUTTER_ORDER, _BAND_HZ, btype="band", fs=TELEPHONE_SR, output="sos")
    x = sosfilt(sos, x).astype(np.float32)
    return x, TELEPHONE_SR


def apply_telephone_channel(samples: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """Cadeia telefônica clássica: banda + G.711 A-law. Retrocompatível (= apply_band + A-law).

    Fail-fast (error-handling.md § 2): entrada vazia/None é ValueError tipado.
    """
    x, _ = apply_band(samples, sr)
    # 3. G.711 A-law round-trip, tudo em memória (width=2 → PCM 16-bit)
    alaw = audioop.lin2alaw(_to_int16_bytes(x), 2)
    pcm = audioop.alaw2lin(alaw, 2)
    return _from_int16_bytes(pcm), TELEPHONE_SR
