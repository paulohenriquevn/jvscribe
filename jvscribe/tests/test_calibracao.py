"""Escolha da janela a partir da curva de custo medida NA MÁQUINA-ALVO.

A janela de 6 s não é uma constante do produto — é o resultado de uma medição neste hardware:
a de 10 s custava 262 ms de decode e, com 2 canais a cada 0,5 s, pedia **104,9% da CPU**.
Noutra CPU a conta é outra, e uma constante herdada seria pior que nenhuma.

Este módulo é a parte **determinística** da calibração: dada a curva `janela → custo`, quantos
canais e qual hop, devolve a maior janela que cabe no orçamento. Janela maior é melhor para a
acurácia (mais contexto para o LocalAgreement-2 confirmar), então a busca é pelo maior valor
que ainda cabe — não pelo mais rápido.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

from cpu import janela_maxima, ocupacao  # noqa: E402

# Curva medida neste i7 em 2026-07-31 — {segundos de janela: ms de decode}
CURVA_I7 = {2.0: 86.0, 4.0: 142.0, 6.0: 172.0, 8.0: 218.0, 10.0: 262.0, 12.0: 264.0}


def test_ocupacao_e_canais_vezes_custo_dividido_pelo_hop():
    """2 canais × 172 ms a cada 500 ms = 68,8% da CPU."""
    assert ocupacao(custo_ms=172.0, canais=2, hop_s=0.5) == pytest.approx(0.688, abs=0.001)


def test_ocupacao_de_um_canal_e_metade():
    assert ocupacao(custo_ms=172.0, canais=1, hop_s=0.5) == pytest.approx(0.344, abs=0.001)


def test_hop_menor_aumenta_a_ocupacao():
    """Contra-intuitivo e medido: hop menor NÃO deixa mais responsivo, satura antes."""
    assert ocupacao(172.0, 2, 0.25) > ocupacao(172.0, 2, 0.5)


def test_escolhe_a_maior_janela_que_cabe_no_orcamento():
    """Neste i7, 2 canais, hop 0,5 s, teto de 80%: 6 s cabe (68,8%), 8 s não (87,3%)."""
    assert janela_maxima(CURVA_I7, canais=2, hop_s=0.5, teto=0.80) == 6.0


def test_maquina_mais_rapida_permite_janela_maior():
    """Metade do custo → o orçamento comporta a janela de 12 s."""
    rapida = {k: v / 2 for k, v in CURVA_I7.items()}
    assert janela_maxima(rapida, canais=2, hop_s=0.5, teto=0.80) == 12.0


def test_maquina_mais_lenta_cai_para_a_janela_menor():
    """3× mais lenta: só a de 2 s cabe (34,5% × 3 = 103%… ainda estoura)."""
    lenta = {k: v * 3 for k, v in CURVA_I7.items()}
    assert janela_maxima(lenta, canais=2, hop_s=0.5, teto=0.80) is None


def test_quando_nada_cabe_devolve_None_em_vez_de_chutar():
    """Negativo: recusar é a resposta certa. Devolver a menor janela esconderia que a máquina
    não aguenta o caso de uso — e o operador seguiria achando que está tudo bem."""
    lenta = {2.0: 5000.0}
    assert janela_maxima(lenta, canais=2, hop_s=0.5, teto=0.80) is None


def test_um_canal_so_permite_janela_maior_que_dois():
    """O caso de 1 canal (só mic) tem o dobro do orçamento."""
    um = janela_maxima(CURVA_I7, canais=1, hop_s=0.5, teto=0.80)
    dois = janela_maxima(CURVA_I7, canais=2, hop_s=0.5, teto=0.80)
    assert um is not None and dois is not None and um > dois


def test_curva_vazia_falha_alto():
    """Negativo: sem medição não há calibração. Não pode devolver um default silencioso."""
    with pytest.raises(ValueError, match="curva"):
        janela_maxima({}, canais=2, hop_s=0.5, teto=0.80)


def test_teto_invalido_falha_alto():
    with pytest.raises(ValueError, match="teto"):
        janela_maxima(CURVA_I7, canais=2, hop_s=0.5, teto=1.5)


def test_hop_zero_falha_em_vez_de_dividir_por_zero():
    with pytest.raises(ValueError, match="hop"):
        ocupacao(172.0, 2, 0.0)


def test_curva_nao_monotonica_nao_quebra_a_escolha():
    """Medição real tem ruído: 12 s custou 264 ms e 10 s custou 262 ms — quase iguais.

    A busca é pela MAIOR janela que cabe, avaliada ponto a ponto; não assume monotonicidade.
    """
    ruidosa = {2.0: 90.0, 4.0: 85.0, 6.0: 172.0, 8.0: 160.0}
    assert janela_maxima(ruidosa, canais=2, hop_s=0.5, teto=0.70) == 8.0
