"""Confiança por palavra — o instrumento da fase E0 do protocolo do portão.

A margem (top-1 menos top-2, em
nats) é o único sinal de confiança que sai **de graça** do decode que já rodamos, e mediu
separação real: a τ=1,0 sinaliza 10,3% das palavras e contém 49,8% dos erros.

⚠️ **R4 é o maior risco do protocolo.** `ctc.greedy_text` tem seis chamadores de produção e
qualquer divergência na sua saída altera TODO WER publicado. Por isso `greedy_text` NÃO foi
tocada, e o contrato entre as duas funções é verificável:

    [p.texto for p in greedy_palavras(x)] == greedy_text(x).split()

O plano esboçava `greedy_text` virando invólucro de `greedy_palavras`. **Isso foi refutado
durante a execução**: o vocabulário tem o token id 7 == `'▁'` (verificado no `tokens.txt` do
artefato canônico). Emitido, ele vira um espaço solto, e `detok_pieces` produziria `"a  b"`
enquanto uma junção por palavras produziria `"a b"`. Comparar por `.split()` é exato nos dois
casos e não exige tocar em nada.
"""
from __future__ import annotations

import numpy as np
import pytest

import ctc

# vocabulário mínimo com as três armadilhas: blank, peça inicial, peça de continuação e o `▁` solto
ID2TOK = {0: "<blk>", 1: "▁ca", 2: "sa", 3: "▁de", 4: "▁", 5: "▁gato"}


def _logprobs(caminho: list[int], margens: list[float] | None = None) -> np.ndarray:
    """(T,V) onde o frame t tem `caminho[t]` no topo, com a margem pedida sobre o segundo."""
    T, V = len(caminho), len(ID2TOK)
    lp = np.full((T, V), -20.0, dtype=np.float32)
    for t, tid in enumerate(caminho):
        m = 5.0 if margens is None else margens[t]
        lp[t, tid] = 0.0
        segundo = (tid + 1) % V
        lp[t, segundo] = -m
    return lp


class TestContratoComGreedyText:
    """A invariante que fecha R4."""

    @pytest.mark.parametrize("caminho", [
        [1, 2, 0, 3],            # "casa de"
        [0, 0, 1, 1, 2, 0],      # blank nas pontas e repetição adjacente
        [4, 1, 2],               # o token `▁` solto ANTES de uma palavra
        [1, 2, 4, 3],            # o token `▁` solto no MEIO — o caso que refutou o desenho
        [5],                     # uma palavra só
    ])
    def test_as_palavras_sao_exatamente_o_split_do_texto(self, caminho):
        lp = _logprobs(caminho)
        assert [p.texto for p in ctc.greedy_palavras(lp, ID2TOK)] == ctc.greedy_text(lp, ID2TOK).split()

    def test_greedy_text_nao_mudou(self):
        """Verificação direta de que a assinatura antiga segue produzindo o de sempre."""
        lp = _logprobs([1, 2, 0, 3])
        assert ctc.greedy_text(lp, ID2TOK) == "casa de"


class TestMargem:
    def test_a_margem_da_palavra_e_o_minimo_dos_tokens(self):
        """O elo mais fraco: uma palavra com um token duvidoso é uma palavra duvidosa."""
        lp = _logprobs([1, 2], margens=[7.0, 0.4])
        assert ctc.greedy_palavras(lp, ID2TOK)[0].margem == pytest.approx(0.4)

    def test_usa_o_PRIMEIRO_frame_de_uma_emissao_repetida(self):
        """A regra tem de ser a mesma que produziu os números medidos do protocolo.

        Um token que dura vários frames tem uma margem por frame. Trocar "primeiro" por "máximo
        sobre o span" muda a distribuição inteira — e as predições pré-registradas de E1 e E2
        foram calibradas com o primeiro. Alternativas ficam para E1 medir, não para o código
        escolher em silêncio.
        """
        lp = _logprobs([1, 1, 1], margens=[0.3, 9.0, 9.0])
        assert ctc.greedy_palavras(lp, ID2TOK)[0].margem == pytest.approx(0.3)

    def test_margem_e_finita_e_nao_negativa(self):
        lp = _logprobs([1, 2, 0, 3])
        for p in ctc.greedy_palavras(lp, ID2TOK):
            assert np.isfinite(p.margem) and p.margem >= 0


class TestCasosDegenerados:
    def test_so_blank_nao_produz_palavra(self):
        assert ctc.greedy_palavras(_logprobs([0, 0, 0]), ID2TOK) == []

    def test_entrada_vazia_nao_explode(self):
        assert ctc.greedy_palavras(np.zeros((0, len(ID2TOK)), dtype=np.float32), ID2TOK) == []

    def test_valid_len_recorta_como_no_greedy_text(self):
        lp = _logprobs([1, 2, 0, 3])
        assert ([p.texto for p in ctc.greedy_palavras(lp, ID2TOK, valid_len=2)]
                == ctc.greedy_text(lp, ID2TOK, valid_len=2).split())

    def test_vocabulario_de_um_token_nao_tem_segundo_colocado(self):
        """Margem exige top-2. Um vocabulário degenerado não pode virar IndexError."""
        lp = np.zeros((2, 1), dtype=np.float32)
        assert ctc.greedy_palavras(lp, {0: "x"}, blank=-1) is not None
