"""Testes do scorer de recogs (WER+CER) — lógica pura, determinística, sem I/O.

Protege o cálculo que fecha a tabela comparativa de M4 (Zipformer vs Conformer):
um bug aqui produziria um número errado num artefato de decisão.
"""

import pytest

from metrics import score_recogs  # noqa: E402


def test_wer_e_cer_de_um_recogs_conhecido():
    # ref=[casa, azul] / hyp=[casa, azuis]: 1 sub de palavra em 2 → WER 50%.
    # chars: "casaazul"(8) → "casaazuis"(9): prefixo "casaazu", 'l'→'is' = 2 edições.
    text = (
        "u1:\tref=['casa', 'azul']\n"
        "u1:\thyp=['casa', 'azuis']\n"
        "u1:\ttimestamp_hyp=[(0.0, 0.4), (0.5, 0.9)]\n"  # ignorado
    )
    r = score_recogs(text)
    assert r["utterances"] == 1
    assert r["words"] == 2 and r["werr"] == 1
    assert r["wer"] == pytest.approx(50.0)
    assert r["chars"] == 8 and r["cerr"] == 2
    assert r["cer"] == pytest.approx(25.0)


def test_transcricao_perfeita_da_wer_e_cer_zero():
    text = "u1:\tref=['ola', 'mundo']\nu1:\thyp=['ola', 'mundo']\n"
    r = score_recogs(text)
    assert r["wer"] == pytest.approx(0.0)
    assert r["cer"] == pytest.approx(0.0)


def test_falha_alto_quando_ref_sem_hyp_correspondente():
    # Caso negativo: recogs truncado (hyp faltando) NÃO pode virar número silencioso.
    text = "u1:\tref=['casa']\nu1:\thyp=['casa']\nu2:\tref=['carro']\n"
    with pytest.raises(ValueError, match="desemparelhados"):
        score_recogs(text)


def test_falha_alto_em_recogs_vazio():
    # Caso negativo: arquivo vazio / formato errado (0 linhas ref=/hyp=) NÃO pode
    # virar WER 0,00% silencioso (era o defeito do review M4).
    with pytest.raises(ValueError, match="vazio"):
        score_recogs("lixo sem ref nem hyp\ntimestamp_hyp=[(0,1)]\n")
