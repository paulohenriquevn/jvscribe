"""O numerador de todo WER e CER do projeto — sem teste até agora.

`word_edit_distance` é importada por 6 módulos (`eval_runtime_wer`, `cer_from_recogs`,
`bootstrap_wer_ci`, `compare_models`, e os dois probes) e é o numerador de cada número de
acurácia publicado. Um off-by-one aqui não quebra nada visivelmente: ele desloca TODOS os
WERs na mesma direção, o que os mantém internamente consistentes e portanto plausíveis.

É o modo de falha mais perigoso deste repositório — por isso os casos abaixo verificam as
três operações separadamente (S/D/I) em vez de só um exemplo agregado, e ancoram o resultado
em distâncias calculadas à mão.
"""
from __future__ import annotations

import pytest

from metrics import word_edit_distance


def test_sequencias_iguais_tem_distancia_zero():
    assert word_edit_distance(["a", "b", "c"], ["a", "b", "c"]) == 0


def test_substituicao_conta_uma_edicao():
    assert word_edit_distance(["casa", "azul"], ["casa", "verde"]) == 1


def test_delecao_conta_uma_edicao():
    assert word_edit_distance(["a", "b", "c"], ["a", "c"]) == 1


def test_insercao_conta_uma_edicao():
    assert word_edit_distance(["a", "c"], ["a", "b", "c"]) == 1


def test_as_tres_operacoes_somam():
    # ref: [o gato preto corre]  hyp: [o cachorro preto corre muito]
    #   sub: gato→cachorro (1) ; ins: muito (1)  → 2
    assert word_edit_distance(
        ["o", "gato", "preto", "corre"],
        ["o", "cachorro", "preto", "corre", "muito"],
    ) == 2


def test_ordem_diferente_nao_e_gratis():
    """Levenshtein não tem transposição — trocar duas palavras custa 2, não 1.

    Fixa a semântica: se alguém trocar por Damerau-Levenshtein, todo WER do projeto muda.
    """
    assert word_edit_distance(["a", "b"], ["b", "a"]) == 2


# ── Bordas (extremos VÁLIDOS) ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "ref,hyp,esperado",
    [
        ([], [], 0),                       # ambos vazios
        ([], ["a", "b"], 2),               # ref vazia → tudo é inserção
        (["a", "b", "c"], [], 3),          # hyp vazia → tudo é deleção (o caso do decode mudo)
        (["a"], ["b"], 1),                 # unitárias distintas
    ],
)
def test_bordas_de_sequencia_vazia(ref, hyp, esperado):
    assert word_edit_distance(ref, hyp) == esperado


def test_hipotese_vazia_e_o_piso_de_wer_100pct():
    """Um modelo que não emite nada tem de dar WER exatamente 100%, nunca mais.

    Se a distância excedesse `len(ref)`, um decode degenerado (blank em todos os frames —
    já observado neste projeto durante o finetune de M5) reportaria WER > 100% e mascararia
    a natureza da falha.
    """
    ref = ["uma", "frase", "de", "cinco", "palavras"]
    assert word_edit_distance(ref, []) == len(ref)


def test_a_distancia_nunca_excede_o_maior_comprimento():
    """Invariante matemática de Levenshtein — vale para qualquer par."""
    casos = [(["a"], ["x", "y", "z"]), (["a", "b", "c", "d"], ["a"]), (["p", "q"], ["q", "p"])]
    for ref, hyp in casos:
        assert word_edit_distance(ref, hyp) <= max(len(ref), len(hyp))


def test_e_simetrica():
    """d(a,b) == d(b,a) — inserção e deleção têm o mesmo custo nesta implementação."""
    a, b = ["o", "rato", "roeu"], ["o", "gato", "roeu", "tudo"]
    assert word_edit_distance(a, b) == word_edit_distance(b, a)


def test_serve_para_CER_operando_sobre_caracteres():
    """`cer_from_recogs` passa listas de CARACTERES na mesma função — o contrato tem de valer.

    "casaazul" → "casaazuis": prefixo "casaazu" comum, depois 'l' → 'is' = 2 edições.
    """
    assert word_edit_distance(list("casaazul"), list("casaazuis")) == 2
