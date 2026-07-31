"""A classificação do erro é a ciência da sonda — e não tinha teste.

`eval/analyze_error_composition.py` testa uma hipótese real (Paulo, 2026-07-26): *"se a palavra
existe em PT-BR não mexe; se não existe, corrige"*. A resposta decide se vale construir
correção por léxico. A regra que produz essa resposta vivia dentro de um laço aninhado dentro
de `main()`, junto com subprocess e escrita de WAV: **não era importável, logo não era
testável**. Os dois testes que citavam o módulo testavam a régua de texto, não a classificação.

Três defeitos que os testes abaixo fixam como comportamento:

1. **`max(subs, 1)` fabricava denominador.** Com zero substituições o relatório imprimia
   "0,0% ATACÁVEL" sob o rótulo `[MEDIDO]` — conclusão a partir de evidência nenhuma.
   `fracao()` devolve `None`, e o relatório diz que não há o que classificar.
2. **Percentual sem intervalo de confiança**, com n=100 — a falácia § 3 #12 do próprio
   contrato de evidência do projeto. O IC agora existe e reamostra **utterances**, não
   substituições: substituições dentro da mesma utterance são correlacionadas, e reamostrá-las
   como independentes estreitaria o IC artificialmente.
3. **A recusa com n < 3**, mesma postura de `common/stats.comparar_pareado`.
"""
from __future__ import annotations

import pytest

from eval.analyze_error_composition import Composicao, analisar, classificar

LEXICO = {"casa", "gato", "cachorro", "porta", "correu"}


class TestClassificar:
    """Cada classe existe porque implica uma AÇÃO diferente — não são rótulos decorativos."""

    def test_hyp_fora_do_lexico_com_ref_real_e_atacavel(self):
        """O alvo do método: `casa` → `kasa`. Um filtro por léxico pegaria."""
        assert classificar("casa", "kasa", LEXICO) == "non_word_hyp"

    def test_ambas_palavras_reais_e_inatacavel(self):
        """`casa` → `gato`: o erro passa no filtro. Nenhum léxico o detecta."""
        assert classificar("casa", "gato", LEXICO) == "real_word_hyp"

    def test_ref_fora_do_lexico_e_alvo_de_biasing_nao_de_lexico(self):
        """Nome próprio/OOV: corrigir por dicionário destruiria a referência correta."""
        assert classificar("jvscribe", "gessescraibe", LEXICO) == "rare_ref"

    def test_ref_fora_do_lexico_vence_mesmo_com_hyp_fora(self):
        """Ordem importa: se a REF não está no dicionário, o dicionário não é a ferramenta.

        Sem esta precedência, um par OOV→OOV seria contado como 'atacável' e a sonda
        superestimaria o ganho do método exatamente onde ele não se aplica.
        """
        assert classificar("jvscribe", "xyz", LEXICO) == "rare_ref"


class TestAnalisar:
    def test_conta_substituicoes_e_acertos_da_utterance(self):
        ref = ["a", "casa", "gato"]
        hyp = ["a", "kasa", "gato"]
        u = analisar(ref, hyp, LEXICO | {"a"})
        assert u.substituicoes == ("non_word_hyp",)
        assert u.corretas == 2                       # "a" e "gato"
        assert u.pares == (("casa", "kasa"),)

    def test_palavra_correta_fora_do_lexico_e_risco_de_falso_positivo(self):
        """O método "corrigiria" uma palavra que já estava certa — o dano do lado oposto."""
        u = analisar(["jvscribe"], ["jvscribe"], LEXICO)
        assert u.corretas == 1
        assert u.corretas_fora_do_lexico == 1
        assert u.falsos_positivos == ("jvscribe",)


class TestComposicao:
    def _com(self, *utterances):
        return Composicao(tuple(utterances))

    def test_sem_substituicoes_a_fracao_e_desconhecida_e_nao_zero(self):
        """`max(subs, 1)` devolvia 0,0% — um número onde não há medição.

        Zero por cento afirma "medimos e nada é atacável". `None` afirma "não há substituição
        para classificar". São coisas diferentes, e a primeira é falsa.
        """
        c = self._com(analisar(["casa"], ["casa"], LEXICO))
        assert c.total_substituicoes == 0
        assert c.fracao("non_word_hyp") is None

    def test_fracao_sobre_o_total_de_substituicoes(self):
        c = self._com(
            analisar(["casa", "porta"], ["kasa", "gato"], LEXICO),   # 1 non_word + 1 real_word
        )
        assert c.total_substituicoes == 2
        assert c.fracao("non_word_hyp") == pytest.approx(0.5)

    def test_ic_recusa_amostra_pequena_em_vez_de_devolver_intervalo_falso(self):
        """Mesma postura de `common/stats.comparar_pareado`, que recusa n < 3.

        Um IC de duas utterances é aritmética, não estatística — e publicado ao lado de um
        rótulo `[MEDIDO]` seria pior que ausência de IC.
        """
        c = self._com(analisar(["casa"], ["kasa"], LEXICO),
                      analisar(["porta"], ["kasa"], LEXICO))
        assert c.ic95("non_word_hyp") is None

    def test_ic_reamostra_utterances_e_e_reprodutivel(self):
        """A unidade de amostragem é a utterance — reamostrar substituição infla a confiança."""
        us = [analisar(["casa", "porta"], ["kasa", "gato"], LEXICO) for _ in range(5)]
        c = self._com(*us)
        a, b = c.ic95("non_word_hyp"), c.ic95("non_word_hyp")
        assert a == b, "seed fixa → IC reprodutível"
        lo, hi = a
        assert 0.0 <= lo <= c.fracao("non_word_hyp") <= hi <= 1.0

    def test_exemplos_sao_limitados_e_deterministicos(self):
        us = [analisar(["casa"], [f"kasa{i}"], LEXICO) for i in range(20)]
        ex = self._com(*us).exemplos("non_word_hyp", limite=3)
        assert len(ex) == 3
        assert ex == self._com(*us).exemplos("non_word_hyp", limite=3)


def test_exemplos_de_falso_positivo_respeitam_o_limite_e_a_ordem():
    """A lacuna que eu mesmo deixei: escrevi o método e não o exercitei.

    O `limite` existe para o relatório não virar dump — e o corte tem de ser determinístico,
    senão duas corridas idênticas produzem documentos diferentes.
    """
    us = [analisar([f"oov{i}"], [f"oov{i}"], LEXICO) for i in range(20)]
    c = Composicao(tuple(us))
    assert c.corretas_fora_do_lexico == 20
    ex = c.exemplos_de_falso_positivo(limite=5)
    assert ex == ["oov0", "oov1", "oov2", "oov3", "oov4"]
    assert ex == Composicao(tuple(us)).exemplos_de_falso_positivo(limite=5)


def test_sem_falso_positivo_a_lista_e_vazia_e_nao_um_placeholder():
    c = Composicao((analisar(["casa"], ["casa"], LEXICO),))
    assert c.exemplos_de_falso_positivo() == []
    assert c.risco_de_falso_positivo() == 0.0
