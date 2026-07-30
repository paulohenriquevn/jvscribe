"""Testes da transcrição em lote. Funções puras (greedy, segment) sem I/O + um smoke
de ponta-a-ponta com áudio sintético (prova o pipeline decode→segment→ONNX→saída)."""
import pytest

# Dependência de ambiente, não do produto: em runner limpo o módulo pode faltar.
# `importorskip` transforma isso em SKIP VISÍVEL em vez de erro de coleta, que
# derrubaria a suíte inteira (M9 — descoberto rodando o CI).
pytest.importorskip("lhotse")
pytest.importorskip("onnxruntime")

import shutil
import numpy as np
import pytest

from batch_transcribe import greedy, segment, SR

# Resolvido pelo kernel compartilhado, NUNCA por caminho literal: em 2026-07-30 o artefato foi
# renomeado e estas duas constantes, absolutas e com o nome antigo, transformaram o smoke de
# ponta a ponta num `skip` silencioso — suíte verde, cobertura perdida.
from artifact import default_model_path, default_sibling  # noqa: E402

MODEL = default_model_path()
TOKENS = default_sibling("tokens.txt")


# --- greedy (colapso CTC de uma linha) --------------------------------------

def _id2tok():
    return {0: "<blk>", 1: "▁a", 2: "▁b"}


def test_greedy_colapsa_repeticoes_e_blank():
    # frames: a a <blk> b  -> "a b"
    V = 3
    rows = np.full((4, V), -9.0, dtype=np.float32)
    for i, tok in enumerate([1, 1, 0, 2]):
        rows[i, tok] = 0.0
    assert greedy(rows, 4, _id2tok()) == "a b"


def test_greedy_respeita_valid_len():
    rows = np.full((4, 3), -9.0, dtype=np.float32)
    rows[0, 1] = 0.0; rows[1, 2] = 0.0  # a, b nos 2 primeiros
    rows[2, 2] = 0.0; rows[3, 1] = 0.0  # ignorados (valid_len=2)
    assert greedy(rows, 2, _id2tok()) == "a b"


# --- segment (VAD de energia + teto de duração) -----------------------------

def test_segment_audio_curto_um_segmento():
    x = (0.3 * np.sin(2 * np.pi * 440 * np.arange(SR) / SR)).astype(np.float32)  # 1s
    assert segment(x, max_sec=28.0) == [(0, len(x))]


def test_segment_vazio():
    assert segment(np.zeros(0, dtype=np.float32)) == []


def test_segment_longo_respeita_teto():
    # 60s de tom contínuo (sem silêncio) → hard-split, cada trecho <= max_sec
    x = (0.3 * np.sin(2 * np.pi * 300 * np.arange(60 * SR) / SR)).astype(np.float32)
    segs = segment(x, max_sec=20.0)
    assert len(segs) >= 3
    assert all((b - a) <= int(20.0 * SR) + SR for a, b in segs)  # cada <= ~max_sec
    assert segs[0][0] == 0 and segs[-1][1] == len(x)             # cobre tudo


def test_segment_corta_em_silencio():
    # 10s fala + 1s silêncio + 10s fala = 21s. Com max_sec=15 (< 21) a segmentação roda e
    # prefere cortar NO silêncio (não no meio da fala) → >= 2 segmentos.
    sr = SR
    fala = 0.3 * np.sin(2 * np.pi * 300 * np.arange(10 * sr) / sr)
    sil = np.zeros(sr)
    x = np.concatenate([fala, sil, fala]).astype(np.float32)
    segs = segment(x, max_sec=15.0)
    assert len(segs) >= 2
    # existe um corte perto do silêncio (~10s), não só no teto de duração
    corte_perto_do_silencio = any(abs(a - 10 * sr) < sr or abs(b - 10 * sr) < sr for a, b in segs)
    assert corte_perto_do_silencio


# --- smoke de ponta-a-ponta (precisa do modelo + ffmpeg) --------------------

@pytest.mark.skipif(not (shutil.which("ffmpeg") and __import__("os").path.exists(MODEL)),
                    reason="ffmpeg ou modelo ausente")
def test_smoke_transcreve_pasta(tmp_path):
    import soundfile as sf
    from batch_transcribe import transcribe_folder
    # gera 2 áudios sintéticos (tom+ruído) numa pasta
    ad = tmp_path / "audios"; ad.mkdir()
    for i in range(2):
        x = (0.3 * np.sin(2 * np.pi * 300 * np.arange(3 * SR) / SR)
             + 0.02 * np.random.default_rng(i).standard_normal(3 * SR)).astype(np.float32)
        sf.write(str(ad / f"a{i}.wav"), x, SR)
    out = tmp_path / "out"
    s = transcribe_folder(str(ad), str(out), MODEL, TOKENS, batch=2, workers=2, threads=2)
    assert s["files"] == 2
    assert s["rtfx_agregado"] is not None and s["rtfx_agregado"] > 0
    assert (out / "a0.txt").exists() and (out / "transcripts.json").exists()
