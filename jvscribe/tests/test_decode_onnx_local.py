"""`decode_onnx_local` — decode ONNX sobre manifest lhotse, medindo WER e RTFx.

Carregava três defeitos que a suíte não via:

1. `load_tokens`, `ids_to_text` e `greedy_ctc` **próprios**, duplicando `common/ctc.py`. Hoje o
   detok era idêntico (verificado), mas cópia diverge — e o shared kernel existe porque o
   colapso CTC já tinha sido replicado 7×;
2. defaults `model.int8.onnx` / `tokens.txt` relativos ao **diretório de trabalho**, ignorando
   o `model_card.json` — o mesmo defeito já corrigido em `mic_transcribe.py`;
3. `jiwer.wer(refs, hyps)` sobre texto **cru**, uma terceira régua no mesmo repositório.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "batch"))
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

pytest.importorskip("lhotse")


def test_o_colapso_ctc_vem_do_shared_kernel():
    """Não pode haver reimplementação: o kernel existe porque isso já foi replicado 7×."""
    import inspect

    import decode_onnx_local as d

    fonte = inspect.getsource(d)
    assert "import ctc" in fonte or "from ctc" in fonte, "não consome o shared kernel"
    for morto in ("def greedy_ctc", "def ids_to_text", "def load_tokens"):
        assert morto not in fonte, f"{morto} ainda é reimplementado aqui"


def test_o_decode_produz_o_mesmo_texto_que_o_kernel():
    """Equivalência comportamental, não só estrutural — o que importa é o texto sair igual."""
    import ctc

    import decode_onnx_local as d

    id2tok = {0: "<blk>", 5: "▁ola", 7: "mun", 9: "do"}
    lp = np.full((1, 6, 10), -9.0, dtype=np.float32)
    for t, tok in enumerate([5, 5, 0, 7, 9, 0]):
        lp[0, t, tok] = 0.0

    assert d.decodificar_lote(lp, np.array([6]), id2tok) == [
        ctc.greedy_text(lp[0], id2tok, 6)
    ]


def test_o_modelo_default_vem_do_artefato_canonico():
    """Default relativo ao cwd resolve para o que estiver na pasta — ou para nada."""
    import inspect

    import decode_onnx_local as d

    fonte = inspect.getsource(d)
    assert "default_model_path" in fonte
    assert 'default="model.int8.onnx"' not in fonte, "default relativo ao cwd voltou"


def test_o_wer_usa_a_regua_canonica():
    """Terceira régua no mesmo repositório torna nenhum WER comparável com outro."""
    import decode_onnx_local as d

    wer, cer = d.medir_wer_cer(["Não é a mesma régua, José!"], ["nao e a mesma regua jose"])
    assert wer == pytest.approx(0.0, abs=1e-9), (
        "com a régua canônica estas duas strings são idênticas; sem ela, WER seria 100%"
    )
    assert cer == pytest.approx(0.0, abs=1e-9)


def test_wer_sem_referencia_util_nao_divide_por_zero():
    """Negativo: manifest sem ground-truth é o modo QUALITATIVO, não um crash."""
    import decode_onnx_local as d

    assert d.medir_wer_cer([], []) == (None, None)
    assert d.medir_wer_cer(["   "], ["algo"]) == (None, None)
