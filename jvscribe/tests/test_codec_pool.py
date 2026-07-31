"""Testes do pool de codecs realistas (T1.1). G.711 é puro (audioop); gsm/opus via
ffmpeg (skip se ausente). Determinístico; sem WAV em disco (pipes)."""
import numpy as np
import pytest

from audio.codecs import sample_codec, apply_codec, POOL_DEFAULT, _ffmpeg_available


def _tone(sr=16000, dur=0.5, f=1000.0):
    t = np.arange(int(sr * dur)) / sr
    return (0.6 * np.sin(2 * np.pi * f * t)).astype(np.float32)


def test_sample_codec_respeita_pesos():
    rng = np.random.default_rng(0)
    pool = {"g711a": 0.0, "gsm": 1.0}  # só gsm pode sair
    got = {sample_codec(rng, pool) for _ in range(50)}
    assert got == {"gsm"}


def test_sample_codec_default_cobre_o_pool():
    rng = np.random.default_rng(1)
    draws = {sample_codec(rng) for _ in range(500)}
    assert draws.issubset(set(POOL_DEFAULT))
    assert len(draws) >= 2  # amostra mais de um codec


def test_apply_codec_identity_passthrough():
    x = _tone()
    out = apply_codec(x, 16000, "identity")
    assert np.allclose(out, x)


def test_apply_codec_g711a_altera_mantem_comprimento_e_finito():
    x = _tone()
    out = apply_codec(x, 16000, "g711a")
    assert out.shape == x.shape
    assert np.all(np.isfinite(out))
    assert not np.allclose(out, x)          # companding degrada
    assert np.max(np.abs(out)) <= 1.01      # continua normalizado


def test_apply_codec_g711u_tambem_degrada():
    x = _tone()
    out = apply_codec(x, 16000, "g711u")
    assert out.shape == x.shape and not np.allclose(out, x)


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg ausente")
def test_gsm_degrada_mais_que_g711():
    x = _tone(f=1000.0)
    mse_g711 = float(np.mean((apply_codec(x, 16000, "g711a") - x) ** 2))
    mse_gsm = float(np.mean((apply_codec(x, 16000, "gsm")[: len(x)] - x[: len(apply_codec(x, 16000, "gsm"))]) ** 2))
    assert mse_gsm > mse_g711    # GSM (8k, comprimido) distorce mais que μ/a-law a 16k


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg ausente")
def test_gsm_saida_finita_e_normalizada():
    out = apply_codec(_tone(), 16000, "gsm")
    assert out.size > 0 and np.all(np.isfinite(out)) and np.max(np.abs(out)) <= 1.01


def test_bug_real_no_torchaudio_nao_e_engolido_pelo_fallback(monkeypatch):
    """`except Exception` trocava o codec do dado de TREINO em silêncio.

    O fallback existe para "backend indisponível" (ImportError / RuntimeError / OSError).
    Um defeito de programação — `ValueError` de shape, `TypeError` de dtype — tem de SUBIR:
    se for engolido, a augmentação aplica outro codec do que o declarado e o efeito só
    aparece como WER pior semanas depois, sem nenhum erro no log.
    """
    from audio import codecs as cp

    def _explode(*a, **k):
        raise ValueError("shape errado — defeito de programação, não backend ausente")

    monkeypatch.setattr(cp, "_apply_torchaudio", _explode)
    with pytest.raises(ValueError, match="defeito de programação"):
        cp.apply_codec(_tone(), 16000, "opus_low")


@pytest.mark.parametrize("erro", [ImportError, RuntimeError, OSError])
def test_backend_ausente_cai_para_ffmpeg_avisando(monkeypatch, erro):
    """A família "backend indisponível" continua caindo para ffmpeg — mas AVISANDO.

    O fallback silencioso escondia que a máquina roda o caminho lento; o aviso torna a
    degradação de performance visível sem quebrar a execução.
    """
    from audio import codecs as cp

    if not _ffmpeg_available():
        pytest.skip("ffmpeg ausente — o fallback não tem para onde cair")

    def _sem_backend(*a, **k):
        raise erro("backend não compilado")

    monkeypatch.setattr(cp, "_apply_torchaudio", _sem_backend)
    with pytest.warns(RuntimeWarning, match="torchaudio indisponível"):
        out = cp.apply_codec(_tone(), 16000, "opus_low")
    assert out.size > 0 and np.all(np.isfinite(out))
