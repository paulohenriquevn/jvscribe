"""O modelo de linguagem n-grama do E6 — contrato de pontuação e de robustez."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "probes"))

CORPUS = [
    "o gato subiu no telhado",
    "o gato desceu do telhado",
    "o cachorro subiu no telhado",
    "o gato subiu no telhado",
]


@pytest.fixture
def lm():
    from lm_ngram import NgramLM
    return NgramLM.treinar(CORPUS, ordem=3)


class TestPontuacao:
    def test_continuacao_vista_pontua_melhor_que_nao_vista(self, lm):
        # "o gato subiu" aparece 2x; "o gato desceu" 1x
        assert lm.log_score("subiu", ("o", "gato")) > lm.log_score("desceu", ("o", "gato"))

    def test_palavra_fora_do_vocabulario_nao_e_menos_infinito(self, lm):
        """-inf mataria o beam: a hipótese inteira sairia da busca por uma palavra desconhecida.

        Um LM que pode ELIMINAR hipóteses acústicas plausíveis deixa de ser um prior e vira um
        filtro — e um filtro treinado em Wikipédia recusaria justamente os termos raros de call
        center que mais importam.
        """
        import math
        s = lm.log_score("bacen", ("o", "gato"))
        assert math.isfinite(s), "OOV tem de receber um piso finito, não -inf"
        assert s < lm.log_score("subiu", ("o", "gato"))

    def test_recua_para_contexto_menor_quando_o_maior_nao_foi_visto(self, lm):
        """Contexto inédito não pode zerar: recua para bigrama e depois para unigrama."""
        import math
        assert math.isfinite(lm.log_score("telhado", ("xyz", "abc")))

    def test_o_recuo_custa(self, lm):
        """Mesma palavra pontua PIOR por contexto recuado — é o desconto do backoff."""
        assert lm.log_score("subiu", ("o", "gato")) > lm.log_score("subiu", ("xyz", "abc"))

    def test_e_deterministico(self, lm):
        assert lm.log_score("subiu", ("o", "gato")) == lm.log_score("subiu", ("o", "gato"))


class TestPersistencia:
    def test_ida_e_volta_preserva_a_pontuacao(self, lm, tmp_path):
        from lm_ngram import NgramLM
        p = tmp_path / "lm.pkl"
        lm.salvar(p)
        outro = NgramLM.carregar(p)
        assert outro.log_score("subiu", ("o", "gato")) == lm.log_score("subiu", ("o", "gato"))
        assert outro.ordem == lm.ordem
