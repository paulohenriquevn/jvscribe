"""O portão de confiança — lógica pura da fase E1 do protocolo pré-registrado.

O portão sinaliza palavras cuja margem fica abaixo de τ. Os números que motivaram o protocolo vieram de **uma** passagem, e a
regra 3 da disciplina de medição (§ 3) proíbe concluir
de corrida única — este projeto errou três vezes assim.

O que estes testes fixam é a **aritmética** do portão, para que o probe meça o fenômeno e não um
bug de contagem. Dois casos merecem atenção por serem armadilha:

1. **Precisão sobre zero sinalizados é indefinida, não 100%.** Um τ tão baixo que não sinaliza
   nada tem de devolver `None` — senão a curva termina com um ponto perfeito e falso, que é
   exatamente o formato de gráfico que faz alguém escolher o τ errado.
2. **A unidade de reamostragem é a utterance, não a palavra.** Palavras da mesma locução são
   correlacionadas (mesmo locutor, mesmo áudio, mesmo contexto); reamostrá-las como independentes
   estreitaria o IC artificialmente — a falácia § 3 #12 com uma casa decimal a mais.
"""
from __future__ import annotations

import pytest

from probes.portao_correcao_probe import Avaliacao, ic95_bootstrap, precisao_recall, sinalizar


def _av(margem: float, errada: bool) -> Avaliacao:
    return Avaliacao(margem=margem, errada=errada)


class TestSinalizar:
    def test_sinaliza_abaixo_do_limiar_e_nada_acima(self):
        assert sinalizar([_av(0.3, True), _av(5.0, False)], tau=1.0) == [True, False]

    def test_o_limiar_e_estrito(self):
        """Margem exatamente τ NÃO é sinalizada — a fronteira precisa ser uma só."""
        assert sinalizar([_av(1.0, True)], tau=1.0) == [False]

    def test_lista_vazia_nao_explode(self):
        assert sinalizar([], tau=1.0) == []


class TestPrecisaoRecall:
    def test_conta_certo_no_caso_simples(self):
        av = [_av(0.3, True), _av(0.4, False), _av(5.0, True), _av(6.0, False)]
        prec, rec = precisao_recall(av, tau=1.0)
        assert prec == pytest.approx(0.5)      # 1 errada entre 2 sinalizadas
        assert rec == pytest.approx(0.5)       # 1 de 2 erradas foi pega

    def test_precisao_e_None_quando_nada_e_sinalizado(self):
        """Zero sinalizados não é precisão perfeita — é ausência de medição."""
        prec, rec = precisao_recall([_av(5.0, True)], tau=1.0)
        assert prec is None
        assert rec == pytest.approx(0.0)

    def test_recall_e_None_quando_nao_ha_erro(self):
        """Sem erro na amostra não há o que recuperar; 0% seria uma afirmação falsa."""
        prec, rec = precisao_recall([_av(0.3, False)], tau=1.0)
        assert rec is None

    def test_amostra_vazia_devolve_None_nos_dois(self):
        assert precisao_recall([], tau=1.0) == (None, None)


class TestBootstrap:
    def test_reamostra_UTTERANCES_e_nao_palavras(self):
        """O IC tem de refletir a variância ENTRE locuções.

        A primeira versão deste teste tinha a premissa errada — usava locuções onde toda palavra
        sinalizada era errada, e aí a precisão vale 1,0 em qualquer reamostragem: degenerada por
        construção, não por bug. O fixture correto mistura locuções com precisão **diferente**,
        que é o que a reamostragem por utterance precisa capturar.
        """
        # locução A: tudo que o portão pega está errado → precisão 1,0
        a = [[_av(0.1, True)] * 5]
        # locução B: tudo que o portão pega está certo → precisão 0,0
        b = [[_av(0.1, False)] * 5]
        lo, hi = ic95_bootstrap(a * 5 + b * 5, tau=1.0, metrica="precisao", n_boot=800, seed=1)
        assert lo < hi, "IC degenerado — provavelmente reamostrou palavra, não utterance"
        assert 0.0 <= lo < 0.5 < hi <= 1.0, "o IC deveria abraçar a mistura 50/50"

    def test_e_reprodutivel_com_a_mesma_seed(self):
        dados = [[_av(0.2, True), _av(5.0, False)] for _ in range(8)]
        a = ic95_bootstrap(dados, tau=1.0, metrica="precisao", n_boot=300, seed=7)
        b = ic95_bootstrap(dados, tau=1.0, metrica="precisao", n_boot=300, seed=7)
        assert a == b

    def test_recusa_amostra_pequena_em_vez_de_devolver_intervalo_falso(self):
        """Mesma postura de `common/stats.comparar_pareado`, que recusa n < 3."""
        assert ic95_bootstrap([[_av(0.2, True)]] * 2, tau=1.0, metrica="precisao",
                              n_boot=300, seed=1) is None

    def test_o_ponto_estimado_cai_dentro_do_proprio_IC(self):
        dados = [[_av(0.2, True), _av(0.9, False), _av(5.0, False)] for _ in range(20)]
        prec, _ = precisao_recall([a for u in dados for a in u], tau=1.0)
        lo, hi = ic95_bootstrap(dados, tau=1.0, metrica="precisao", n_boot=800, seed=3)
        assert lo <= prec <= hi


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E2 — o corretor (fase E2 do protocolo pré-registrado).
#
# O corretor só age onde a classe o admite. A precondição do caminho do dicionário é exatamente
# `non_word_hyp`: a hipótese NÃO é palavra e a referência é. Mexer numa palavra que já existe é
# a over-correction que `arXiv:2505.17410` nomeia — e a medição de E1 diz que 44,1% do que o
# portão sinaliza está CORRETO, então um corretor que toque em tudo quebra quase metade.
# ═══════════════════════════════════════════════════════════════════════════════════════════

from probes.portao_correcao_probe import Corretor, orcamento_de_distancia  # noqa: E402

LEXICO = {"incidente", "gato", "gata", "gate", "pinto", "segunda", "tragico"}


class TestOrcamentoDeDistancia:
    """Uma edição numa palavra de 3 letras é outra coisa que numa de 12."""

    @pytest.mark.parametrize("palavra, esperado", [
        ("pix", 1), ("casa", 1), ("gatos", 1), ("incidente", 2), ("determinismo", 3),
    ])
    def test_cresce_com_o_tamanho(self, palavra, esperado):
        assert orcamento_de_distancia(palavra) == esperado

    def test_nunca_e_zero(self):
        """Orçamento zero tornaria o corretor inerte em palavras curtas, em silêncio."""
        assert orcamento_de_distancia("a") >= 1


class TestCorretor:
    def test_corrige_nao_palavra_para_o_vizinho_mais_proximo(self):
        assert Corretor(LEXICO).corrigir("inncidente") == "incidente"

    def test_nao_toca_palavra_que_ja_e_do_lexico(self):
        """`real_word_hyp` não é escopo deste corretor. `segunda` existe — mexer é over-correction."""
        assert Corretor(LEXICO).corrigir("segunda") is None

    def test_abstem_em_empate(self):
        """`gata` está a 1 de `gato` e a 1 de `gate`. Não escolher é a resposta honesta."""
        assert Corretor({"gato", "gate"}).corrigir("gata") is None

    def test_abstem_quando_nada_cabe_no_orcamento(self):
        assert Corretor(LEXICO).corrigir("xyzabcqwerty") is None

    def test_respeita_o_orcamento_em_palavra_curta(self):
        """`pix` → `pinto` é distância 4; orçamento de 3 letras é 1."""
        assert Corretor({"pinto"}).corrigir("pix") is None

    def test_lexico_vazio_nao_explode(self):
        assert Corretor(set()).corrigir("qualquer") is None

    def test_e_deterministico(self):
        c = Corretor(LEXICO)
        assert c.corrigir("inncidente") == c.corrigir("inncidente")
