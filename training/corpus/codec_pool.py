"""Pool de codecs telefônicos realistas para augmentação (M5 — plano m5-8khz, ADR D3/D4).

Substitui o G.711 A-law fixo (`telephone_channel.py`) por um pool amostrável: o G.711 é o
codec mais inócuo (APSIPA 2019); os agressivos (GSM-FR, Opus baixo-bitrate) é que transferem
para telefonia real. Cada codec aplica sua própria degradação de banda/compressão e devolve
áudio na taxa de entrada, para o resto da cadeia ficar consistente.

Tooling (Regra 9 — não reinventar): G.711 μ/a via `audioop` (puro, in-RAM); GSM/Opus via
`ffmpeg` em pipes (sem WAV em disco). Na instância de treino, o caminho on-the-fly rápido é o
torchaudio `AudioEffector` (ADR D4) — aqui usamos ffmpeg como referência portável e testável.
"""
from __future__ import annotations

import shutil
import subprocess

import numpy as np

try:  # PEP 594: audioop removido no Python 3.13+
    import audioop
except ImportError:  # pragma: no cover
    import audioop_lts as audioop  # type: ignore

# Pool ON-THE-FLY (treino): só codecs IN-PROCESS rápidos (sem spawn de subprocess, que starva a
# GPU — medido a ~0,45 batch/s com ffmpeg). opus (torchaudio, ~21ms) = tier agressivo que
# transfere (APSIPA 2019); G.711 (audioop) = tier brando. GSM fica no builder OFFLINE (ffmpeg).
POOL_DEFAULT = {"g711a": 0.20, "g711u": 0.20, "opus_low": 0.60}

_FFMPEG_CODECS = {
    # codec -> (args de encode a partir de s16le@sr, args p/ reler o container no decode)
    "gsm": (["-ar", "8000", "-ac", "1", "-c:a", "libgsm", "-f", "gsm"], ["-f", "gsm"]),
    "opus_low": (["-ac", "1", "-c:a", "libopus", "-b:a", "6000", "-f", "ogg"], ["-f", "ogg"]),
}


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def sample_codec(rng: np.random.Generator, pool: dict[str, float] | None = None) -> str:
    """Amostra um codec do pool ponderado (soma dos pesos normalizada)."""
    pool = pool or POOL_DEFAULT
    codecs = list(pool)
    w = np.array([pool[c] for c in codecs], dtype=float)
    total = w.sum()
    if total <= 0:
        raise ValueError(f"pesos do pool somam {total}; devem ser > 0")
    return codecs[int(rng.choice(len(codecs), p=w / total))]


def _to_i16_bytes(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def _from_i16_bytes(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype="<i2").astype(np.float32) / 32767.0


def _apply_g711(x: np.ndarray, law: str) -> np.ndarray:
    pcm = _to_i16_bytes(x)
    if law == "a":
        dec = audioop.alaw2lin(audioop.lin2alaw(pcm, 2), 2)
    else:
        dec = audioop.ulaw2lin(audioop.lin2ulaw(pcm, 2), 2)
    return _from_i16_bytes(dec)


def _apply_torchaudio(x: np.ndarray, sr: int, fmt: str, encoder: str, bit_rate: int | None) -> np.ndarray:
    """Codec roundtrip IN-PROCESS via torchaudio AudioEffector (sem spawn — rápido no treino)."""
    import torch
    from torchaudio.io import AudioEffector, CodecConfig
    t = torch.from_numpy(np.ascontiguousarray(x)).unsqueeze(1)  # (T,1)
    cfg = CodecConfig(bit_rate=bit_rate) if bit_rate else None
    eff = AudioEffector(format=fmt, encoder=encoder, codec_config=cfg)
    y = eff.apply(t, sr)
    return np.ascontiguousarray(y[:, 0].numpy()).astype(np.float32)


def _apply_ffmpeg(x: np.ndarray, sr: int, codec: str) -> np.ndarray:
    if not _ffmpeg_available():
        raise RuntimeError(f"ffmpeg ausente — codec '{codec}' indisponível")
    enc_args, dec_container = _FFMPEG_CODECS[codec]
    pcm = _to_i16_bytes(x)
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    try:
        encoded = subprocess.run(
            base + ["-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0", *enc_args, "pipe:1"],
            input=pcm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout
        decoded = subprocess.run(
            base + [*dec_container, "-i", "pipe:0", "-f", "s16le", "-ar", str(sr), "-ac", "1", "pipe:1"],
            input=encoded, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:  # erro tipado + contexto (error-handling.md)
        raise RuntimeError(
            f"ffmpeg falhou no codec '{codec}': {exc.stderr.decode('utf-8', 'ignore')[:200]}"
        ) from exc
    return _from_i16_bytes(decoded)


def apply_codec(samples: np.ndarray, sr: int, codec: str) -> np.ndarray:
    """Aplica um codec ao sinal float [-1,1], devolvendo float na taxa de entrada.

    codec ∈ {identity, g711a, g711u, gsm, opus_low}. Levanta erro tipado para codec
    desconhecido ou dependência ausente (fail-fast — error-handling.md).
    """
    x = np.asarray(samples, dtype=np.float32)
    if codec == "identity":
        return x.copy()
    if codec == "g711a":
        return _apply_g711(x, "a")
    if codec == "g711u":
        return _apply_g711(x, "u")
    if codec == "opus_low":
        # rápido in-process (torchaudio); fallback ffmpeg (ex.: local sem torchaudio)
        try:
            return _apply_torchaudio(x, sr, "ogg", "libopus", bit_rate=6000)
        except Exception:
            return _apply_ffmpeg(x, sr, "opus_low")
    if codec in _FFMPEG_CODECS:      # gsm etc. — offline (builder), não no pool on-the-fly
        return _apply_ffmpeg(x, sr, codec)
    raise ValueError(f"codec desconhecido: {codec!r} (esperado {list(POOL_DEFAULT)}, gsm ou 'identity')")
