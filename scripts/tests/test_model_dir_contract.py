"""O contrato do diretório de artefato: o que o código resolve tem de existir.

Defeito real encontrado em 2026-07-30: `models/current` (symlink de M9/T1.3) aponta para um
diretório cujo modelo se chama `model.int8.onnx`, enquanto `batch_transcribe.py` tinha default
literal `m5_avg.int8.onnx`. Apontar o symlink canônico para o artefato certo e o script quebrar
por nome de arquivo é o pior dos dois mundos: o operador acha que canonizou e não canonizou.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "training" / "batch"))
sys.path.insert(0, str(REPO / "training" / "common"))

pytest.importorskip("lhotse")


def test_o_default_resolvido_aponta_para_um_modelo_que_existe():
    """Exercita o RESOLVEDOR, não o texto do código — comportamento, não estrutura."""
    from batch_transcribe import _default_model_path

    caminho = Path(_default_model_path())
    if not (REPO / "models" / "current").exists():
        pytest.skip("models/current ausente (artefatos não versionados)")
    assert caminho.exists(), (
        f"o default resolvido ({caminho}) não existe — o artefato canônico e o script "
        "discordam sobre o nome do modelo"
    )
    assert caminho.suffix == ".onnx"


def test_resolvedor_honra_MACAW_MODEL_DIR(monkeypatch, tmp_path):
    from batch_transcribe import _default_model_path

    (tmp_path / "model.int8.onnx").write_bytes(b"x")
    monkeypatch.setenv("MACAW_MODEL_DIR", str(tmp_path))
    assert Path(_default_model_path()).parent == tmp_path


def test_o_artefato_canonico_tem_tokens_e_card():
    current = REPO / "models" / "current"
    if not current.exists():
        pytest.skip("models/current ausente")
    for obrigatorio in ("tokens.txt", "model_card.json"):
        assert (current / obrigatorio).exists(), f"{obrigatorio} ausente no artefato canônico"
