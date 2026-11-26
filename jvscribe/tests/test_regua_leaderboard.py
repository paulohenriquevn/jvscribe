"""As três réguas são distintas, e o teste trava a diferença caso a caso.

Este projeto já publicou WER com uma régua defeituosa e moveu uma geração inteira de números
quando ela foi consertada (`wiki/medicoes/e9-*`). A lição registrada é que régua é instrumento,
e instrumento sem golden deriva em silêncio.

Agora são três, e elas discordam nos dois eixos que mais pesam em PT-BR:

| | acento | dígito | `[ruído]` |
|---|---|---|---|
| `normalize_for_wer_compare` | removido | mantido | conteúdo mantido |
| `normalize_train_target` | preservado | mantido | conteúdo mantido |
| `normalize_for_leaderboard` | preservado | **forma falada** | **descartado** |

Uma comparação entre número deste projeto e número publicado por terceiro só é honesta na
terceira. Se este arquivo ficar vermelho, nenhuma afirmação de SOTA que dependa dela vale.
"""
from __future__ import annotations

import pytest

from text import (
    normalize_for_leaderboard,
    normalize_for_wer_compare,
    normalize_train_target,
)

# (entrada, wer_compare, train_target, leaderboard)
GOLDEN = [
    (
        "Coração, atenção!",
        "coracao atencao",
        "coração atenção",
        "coração atenção",
    ),
    (
        "A fatura venceu no dia 15 de março.",
        "a fatura venceu no dia 15 de marco",
        "a fatura venceu no dia 15 de março",
        "a fatura venceu no dia quinze de março",
    ),
    (
        "Pra pagar R$ 100, ligue já!",
        "para pagar 100 reais ligue ja",
        "pra pagar r 100 ligue já",
        "pra pagar r cem ligue já",
    ),
    (
        "O protocolo é 4 7 2 9 1 3.",
        "o protocolo e 4 7 2 9 1 3",
        "o protocolo é 4 7 2 9 1 3",
        "o protocolo é quatro sete dois nove um três",
    ),
    (
        "Bom dia [ruído] (aparte) tudo bem?",
        "bom dia ruido aparte tudo bem",
        "bom dia ruído aparte tudo bem",
        "bom dia tudo bem",
    ),
    (
        "São 10 000 unidades.",
        "sao 10 000 unidades",
        "são 10 000 unidades",
        "são dez mil unidades",
    ),
]


@pytest.mark.parametrize("entrada,esperado_wer,esperado_treino,esperado_lb", GOLDEN)
def test_as_tres_reguas_produzem_o_golden(entrada, esperado_wer, esperado_treino, esperado_lb):
    assert normalize_for_wer_compare(entrada) == esperado_wer
    assert normalize_train_target(entrada) == esperado_treino
    assert normalize_for_leaderboard(entrada) == esperado_lb


def test_leaderboard_preserva_acento_e_wer_compare_nao():
    """O eixo do acento separa a régua pública da régua publicada por este projeto."""
    assert normalize_for_leaderboard("análise") == "análise"
    assert normalize_for_wer_compare("análise") == "analise"


def test_leaderboard_fala_o_digito_e_as_internas_nao():
    """O eixo do dígito é o outro, e é o que mais move o WER em áudio de atendimento."""
    assert (
        normalize_for_leaderboard("protocolo 472913")
        == "protocolo quatrocentos e setenta e dois mil novecentos e treze"
    )
    assert normalize_for_wer_compare("protocolo 472913") == "protocolo 472913"
    assert normalize_train_target("protocolo 472913") == "protocolo 472913"


def test_leaderboard_e_estavel_sob_decomposicao_unicode():
    """Mesma palavra em NFC e NFD tem de normalizar igual.

    Sem preservar as marcas combinantes (categoria 'M'), o acento sobreviveria em NFC e
    sumiria em NFD — a régua mudaria de "com acento" para "sem acento" dependendo apenas de
    como o arquivo foi salvo, e ninguém veria.
    """
    import unicodedata

    nfc = unicodedata.normalize("NFC", "operação")
    nfd = unicodedata.normalize("NFD", "operação")
    assert nfc != nfd  # garante que o caso realmente exercita a diferença
    assert normalize_for_leaderboard(nfc) == normalize_for_leaderboard(nfd) == "operação"


def test_leaderboard_nao_trata_moeda_e_isso_e_deliberado():
    """Fidelidade ao original vence justiça: o objetivo é reproduzir o número DELES.

    `normalize_for_wer_compare` transforma "R$ 100" em "100 reais" porque é a régua deste
    projeto e PT-BR fala assim. O leaderboard não faz isso, e replicar a diferença é o que
    torna a comparação válida.
    """
    assert normalize_for_leaderboard("R$ 100") == "r cem"
    assert normalize_for_wer_compare("R$ 100") == "100 reais"


def test_entrada_vazia_nao_explode():
    assert normalize_for_leaderboard("") == ""
    assert normalize_for_leaderboard(None) == ""
