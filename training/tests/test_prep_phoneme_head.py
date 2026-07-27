"""Testes do aplicador de patch determinístico da cabeça de fonema (M4 fase 3).

Protege as três garantias do patch reprodutível: aplica exatamente 1×, é idempotente
(marcador), e FALHA ALTO se o padrão não bater 1× (nunca patcheia às cegas).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from prep_phoneme_head import apply_patch  # noqa: E402


def test_aplica_substituicao_e_cria_backup(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n")
    apply_patch(f, [("x = 1", "x = 2")], already_applied_marker="x = 2")
    assert f.read_text() == "x = 2\n"
    # backup preserva o original (recuperável)
    assert (tmp_path / "mod.py.orig-phoneme-patch").read_text() == "x = 1\n"


def test_idempotente_quando_marcador_presente(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("x = 2\n")  # já "patcheado": marcador presente
    apply_patch(f, [("x = 1", "x = 2")], already_applied_marker="x = 2")
    assert f.read_text() == "x = 2\n"  # inalterado — não tenta aplicar de novo


def test_falha_alto_quando_padrao_nao_bate_1x(tmp_path):
    # Caso negativo: padrão ausente (0×) → SystemExit, nunca patch parcial/silencioso.
    f = tmp_path / "mod.py"
    f.write_text("y = 1\n")
    with pytest.raises(SystemExit):
        apply_patch(f, [("z = 9", "z = 0")], already_applied_marker="MARKER_AUSENTE")
