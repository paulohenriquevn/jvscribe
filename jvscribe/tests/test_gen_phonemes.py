"""Testes do build de alvos fonéticos (M4 fase 3) — lógica pura, sem G2P/lhotse.

Protege o mapeamento texto→ids da cabeça de fonema: um bug aqui envenenaria o alvo
auxiliar e a ablação mediria ruído.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gen_phonemes import build_targets  # noqa: E402


def test_vocab_convencao_ctc_e_ids_por_ordem_de_aparicao():
    out = build_targets(["oi", "aia"], ["o i", "a i a"])
    # convenção do icefall: 0=<blk>, 1=<unk>; símbolos ganham id na 1ª aparição.
    assert out["vocab"]["<blk>"] == 0 and out["vocab"]["<unk>"] == 1
    assert out["vocab"]["o"] == 2 and out["vocab"]["i"] == 3 and out["vocab"]["a"] == 4
    assert out["map"]["oi"] == [2, 3]
    assert out["map"]["aia"] == [4, 3, 4]  # 'a' e 'i' reusam os ids já atribuídos
    assert out["num_phones"] == 5  # blk, unk, o, i, a
    assert out["n_empty_g2p"] == 0


def test_g2p_vazio_nao_entra_no_mapa_e_e_contado():
    out = build_targets(["ok", ""], ["o k", ""])
    assert "" not in out["map"] and out["map"]["ok"] == [2, 3]
    assert out["n_empty_g2p"] == 1


def test_falha_alto_quando_g2p_desemparelhado():
    # Caso negativo: nº de saídas do G2P != nº de textos não pode virar alvo silencioso.
    with pytest.raises(ValueError, match="desemparelhad|devolveu"):
        build_targets(["a", "b"], ["a"])
