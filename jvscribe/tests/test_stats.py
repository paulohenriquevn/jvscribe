"""Separação estatística — o gate que impede declarar vencedor a partir de ruído.

Motivo `[MEDIDO]` 2026-07-31. Três medições da MESMA configuração no harness ao vivo deram
RTFx 3,51× / 2,90× / 2,82× (e 2,50× numa quarta). No harness determinístico, `intra=2` deu
4,20 / 3,95 / 6,31 e `intra=6` deu 2,92 / 4,54 / 5,03 — medianas 4,20 contra 4,54, com
dispersões que se sobrepõem inteiramente.

Antes disto, este projeto concluiu três vezes a partir de corrida única:
- "intra=8 é 30,9% melhor" — não reproduziu;
- 158,8 ms vs 169,1 ms para configurações **idênticas** (35 ms de ruído);
- "afinidade nos P-cores é 25% melhor" — no sistema real piorou 46%.

O erro não é de quem mede, é de a ferramenta permitir. Aqui a separação é um objeto que
precisa ser afirmado, com o intervalo ao lado.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

from stats import Comparacao, comparar_pareado  # noqa: E402


def test_diferenca_grande_e_consistente_e_conclusiva():
    """B é sistematicamente ~30% menor que A, em toda rodada."""
    a = [100.0, 105.0, 98.0, 102.0, 110.0, 97.0, 103.0, 99.0]
    b = [70.0, 74.0, 69.0, 71.0, 77.0, 68.0, 72.0, 70.0]
    c = comparar_pareado(a, b)
    assert c.conclusivo and c.melhor == "B"
    assert c.ic95[1] < 0, "o IC do delta tem de ficar todo abaixo de zero"


def test_ruido_maior_que_o_efeito_e_inconclusivo():
    """O caso real: intra=2 vs intra=6 no soak. Medianas próximas, dispersões sobrepostas."""
    a = [4.20, 3.95, 6.31]
    b = [4.20, 4.50, 5.19]
    c = comparar_pareado(a, b)
    assert not c.conclusivo
    assert c.melhor is None, "sem separação, não existe vencedor a declarar"


def test_configuracoes_identicas_nunca_produzem_vencedor():
    """Guarda contra o defeito original: 158,8 ms e 169,1 ms para a MESMA configuração."""
    a = [158.8, 169.1, 140.9, 150.2, 137.5]
    c = comparar_pareado(a, list(a))
    assert not c.conclusivo and c.melhor is None
    assert c.delta_medio == pytest.approx(0.0, abs=1e-9)


def test_o_pareamento_cancela_a_flutuacao_comum():
    """Round-robin mede as duas configs na mesma rodada; a carga entra igual nas duas.

    Aqui a carga varia 3× entre rodadas, e B é consistentemente 10 menor. Sem pareamento a
    variância comum esconderia o efeito; com pareamento ele aparece.
    """
    carga = [100, 300, 150, 280, 120, 260, 130, 290]
    a = [float(x) for x in carga]
    b = [float(x - 10) for x in carga]
    c = comparar_pareado(a, b)
    assert c.conclusivo and c.melhor == "B"
    assert c.delta_medio == pytest.approx(-10.0, abs=0.5)


def test_amostra_pequena_demais_e_recusada_em_vez_de_adivinhar():
    """Negativo: 2 pontos não sustentam intervalo. Recusar é melhor que devolver um número."""
    with pytest.raises(ValueError, match="amostras"):
        comparar_pareado([1.0, 2.0], [3.0, 4.0])


def test_listas_de_tamanhos_diferentes_falham_alto():
    """Negativo: parear exige correspondência 1-para-1 entre as rodadas."""
    with pytest.raises(ValueError, match="pareada|tamanho"):
        comparar_pareado([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0])


def test_o_resumo_traz_o_intervalo_ao_lado_do_veredito():
    """Veredito sem intervalo é opinião. O texto tem de carregar os dois."""
    c = comparar_pareado([100.0] * 6, [70.0, 71.0, 69.0, 72.0, 70.0, 71.0])
    s = c.resumo()
    assert "IC95" in s and ("%" in s or "ms" in s or "×" in s)


def test_maior_e_melhor_inverte_o_vencedor_sem_inverter_o_intervalo():
    """RTFx: mais é melhor. Latência: menos é melhor. A mesma função serve os dois."""
    a = [3.0, 3.1, 2.9, 3.05, 3.0, 2.95]
    b = [5.0, 5.1, 4.9, 5.05, 5.0, 4.95]
    menor = comparar_pareado(a, b)                         # default: menor é melhor
    maior = comparar_pareado(a, b, maior_e_melhor=True)
    assert menor.melhor == "A" and maior.melhor == "B"
    assert menor.ic95 == maior.ic95, "o intervalo do delta não depende da direção"


def test_dataclass_construivel_para_reuso_em_relatorio():
    c = Comparacao(delta_medio=-5.0, ic95=(-8.0, -2.0), conclusivo=True, melhor="B",
                   n=10, rotulo_a="A", rotulo_b="B")
    assert "B" in c.resumo()
