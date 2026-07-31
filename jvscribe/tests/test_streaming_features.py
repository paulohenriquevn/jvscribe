"""Cache incremental de features do `StreamingCTC`.

O motor redecodifica a janela a cada hop e, antes deste cache, reextraía o fbank da janela
INTEIRA junto — 21,6% do custo de decode em trabalho que já tinha sido feito. O cache só é
legítimo se produzir exatamente as mesmas features; senão troca CPU por WER em silêncio.

A extração por pedaço só equivale à extração completa quando o offset é MÚLTIPLO do frame
shift (160 amostras a 16 kHz). Com offset desalinhado a divergência medida foi de 6,57 —
ordens de grandeza acima do ruído de float32.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "realtime"))

pytest.importorskip("lhotse")

from streaming import SHIFT, SR, FeatureCache  # noqa: E402


def _ruido(segundos: float, seed: int = 0) -> np.ndarray:
    """Ruído determinístico — fala sintética serve: o que se testa é o fbank, não o ASR."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(segundos * SR)) / SR
    return (0.3 * np.sin(2 * np.pi * 220 * t) + 0.05 * rng.standard_normal(len(t))).astype(
        np.float32
    )


def _extracao_completa(audio: np.ndarray) -> np.ndarray:
    from lhotse import Fbank, FbankConfig

    return np.asarray(Fbank(FbankConfig(num_mel_bins=80)).extract(audio, SR), dtype=np.float32)


def test_alimentar_em_pedacos_da_as_mesmas_features_que_extrair_de_uma_vez():
    audio = _ruido(3.0)
    cache = FeatureCache()
    passo = int(0.5 * SR)
    for i in range(0, len(audio), passo):
        cache.append(audio[i : i + passo])

    esperado = _extracao_completa(audio)
    obtido = cache.features()
    n = min(len(esperado), len(obtido))
    assert n >= 250, f"esperava ~300 frames de 3 s, veio {n}"
    assert np.abs(obtido[:n] - esperado[:n]).max() < 1e-3


def test_pedacos_de_tamanho_irregular_nao_quebram_o_alinhamento():
    """O `read()` da captura devolve lotes de tamanho variável — o caso real, não o ideal."""
    audio = _ruido(2.5, seed=7)
    cache = FeatureCache()
    i, k = 0, 0
    for passo in (1234, 8000, 321, 16000, 999, 5000, 7777, 20000):
        if i >= len(audio):
            break
        cache.append(audio[i : i + passo])
        i += passo
        k += 1
    cache.append(audio[i:])

    esperado = _extracao_completa(audio)
    obtido = cache.features()
    n = min(len(esperado), len(obtido))
    assert np.abs(obtido[:n] - esperado[:n]).max() < 1e-3


def test_descartar_frames_do_inicio_mantem_o_resto_intacto():
    """O trim da janela joga fora áudio antigo; as features restantes não podem deslocar."""
    audio = _ruido(4.0, seed=3)
    cache = FeatureCache()
    cache.append(audio)
    antes = cache.features().copy()

    cache.descartar(100)                     # descarta 100 frames = 1 s

    depois = cache.features()
    assert len(depois) == len(antes) - 100
    assert np.array_equal(depois, antes[100:])


def test_append_vazio_e_no_op():
    """Negativo: uma leitura da captura pode vir vazia — não pode corromper o cache."""
    cache = FeatureCache()
    cache.append(_ruido(1.0))
    antes = cache.features().copy()
    cache.append(np.zeros(0, dtype=np.float32))
    assert np.array_equal(cache.features(), antes)


def test_audio_curto_demais_para_um_frame_nao_produz_frame():
    cache = FeatureCache()
    cache.append(np.zeros(SHIFT // 4, dtype=np.float32))
    assert len(cache.features()) == 0


def test_descartar_mais_do_que_existe_falha_alto():
    """Negativo: pedir descarte além do cache é bug do chamador — não pode virar cache vazio."""
    cache = FeatureCache()
    cache.append(_ruido(0.5))
    with pytest.raises(ValueError, match="descartar"):
        cache.descartar(10_000)
