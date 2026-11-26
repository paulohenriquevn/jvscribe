"""Contrato do patch `prep_finetune.py` (M5). Protege as garantias do patch
reprodutível: injeta as 3 peças (flags, load_model_params, bloco do_finetune),
o resultado COMPILA, é idempotente e falha-alto quando um anchor não bate 1×.

Não testa o treino (isso é run de GPU) — testa o MECANISMO de patch offline,
mesmo idioma de test_prep_phoneme_head.py.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prep_finetune  # noqa: E402


# train.py mínimo com os 3 anchors que o patch procura.
FIXTURE_TRAIN_PY = '''\
import argparse


def str2bool(x):
    return x


def add_model_arguments(parser):
    parser.add_argument("--num-encoder-layers", type=str)


def get_parser():
    parser = argparse.ArgumentParser()
    add_model_arguments(parser)
    return parser


def run(params, model):
    assert params.start_epoch > 0, params.start_epoch
    optimizer = None
    return optimizer
'''


def _write_fixture(tmp_path: Path, content: str = FIXTURE_TRAIN_PY) -> Path:
    f = tmp_path / "train.py"
    f.write_text(content)
    return f


def test_injeta_as_tres_pecas_e_compila(tmp_path):
    f = _write_fixture(tmp_path)
    prep_finetune.patch_train_py(f)
    out = f.read_text()
    # as 3 injeções presentes
    assert "def add_finetune_arguments(parser" in out
    assert "def load_model_params(" in out
    assert "if params.do_finetune:" in out
    assert "--finetune-ckpt" in out and "--init-modules" in out
    # e o arquivo continua Python válido
    ast.parse(out)


def test_bloco_do_finetune_antes_do_assert_start_epoch(tmp_path):
    f = _write_fixture(tmp_path)
    prep_finetune.patch_train_py(f)
    out = f.read_text()
    # o load do base ckpt tem de vir ANTES do assert (e do otimizador)
    assert out.index("if params.do_finetune:") < out.index(
        "assert params.start_epoch > 0, params.start_epoch"
    )
    # e a chamada add_finetune_arguments vem antes de add_model_arguments no parser
    assert out.index("add_finetune_arguments(parser)") < out.index(
        "    add_model_arguments(parser)"
    )


def test_idempotente_quando_marcador_presente(tmp_path):
    f = _write_fixture(tmp_path)
    prep_finetune.patch_train_py(f)
    first = f.read_text()
    prep_finetune.patch_train_py(f)  # 2ª vez: marcador presente → no-op
    assert f.read_text() == first
    # não duplicou a função
    assert first.count("def add_finetune_arguments(parser") == 1


def test_falha_alto_quando_anchor_ausente(tmp_path):
    # remove o anchor do assert de start_epoch → patch deve abortar (SystemExit)
    broken = FIXTURE_TRAIN_PY.replace(
        "    assert params.start_epoch > 0, params.start_epoch\n", ""
    )
    f = _write_fixture(tmp_path, broken)
    with pytest.raises(SystemExit):
        prep_finetune.patch_train_py(f)


def test_falha_alto_quando_train_py_inexistente(tmp_path):
    with pytest.raises(SystemExit):
        prep_finetune.patch_train_py(tmp_path / "nao_existe.py")
