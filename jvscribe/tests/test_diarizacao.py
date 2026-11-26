"""A opção de diarização — e a aritmética que decide se ela cabe.

No caso 1:1 não existe diarização* — o mic **é** o atendente e o loopback **é** o
cliente, por construção da captura: custo zero, acurácia 100%. Esta opção não revoga isso; ela
destrava os casos que a demo de 2026-07-31 mostrou serem reais e que a captura por canal não
resolve:

| caso | onde o canal falha |
|---|---|
| open-plan | o mic pega o atendente da baia ao lado |
| supervisor entra na ligação | três falantes, dois canais |
| duas pessoas do lado do cliente | o loopback carrega duas vozes |

⚠️ **O orçamento é o portão, e ele é aritmético.** Taxas somam pelo INVERSO (RNF-01..05,
racional do RNF-07): ASR a 3× somado a diarização a 3× dá **1,5×**, não 3×. Com o RTFx ao vivo
medido de **3,58×**, um diarizador teria de rodar a **18,5×** para o pipeline ficar em ≥3×.

Por isso a flag não apenas liga: ela **confere a conta antes**. Ligar diarização sem verificar o
orçamento é como este projeto já errou antes — benchmark de componente que não transfere para o
sistema (§ 4 da disciplina; a afinidade de CPU deu 25% melhor isolada e 46% pior no pipeline).
"""
from __future__ import annotations

import pytest

from diarizacao import SemDiarizacao
# A aritmética do orçamento mora em `cpu` — capacidade da máquina é o domínio dela, e o AEC é o
# segundo consumidor da mesma decisão. Importar daqui, e não de `diarizacao`, é o que mantém um
# símbolo com um caminho só.
from cpu import cabe_no_orcamento, rtfx_combinado, rtfx_minimo_do_estagio


class TestAritmeticaDoOrcamento:
    """Taxas somam pelo inverso. É a conta que decide tudo, e ela não é intuitiva."""

    def test_dois_estagios_iguais_dao_metade(self):
        """ASR a 3× + diarização a 3× = 1,5×. O erro intuitivo é achar que dá 3×."""
        assert rtfx_combinado(3.0, 3.0) == pytest.approx(1.5)

    def test_um_estagio_sozinho_e_ele_mesmo(self):
        assert rtfx_combinado(6.0) == pytest.approx(6.0)

    def test_estagio_muito_rapido_quase_nao_custa(self):
        """Um diarizador a 100× tira pouco de um ASR a 6×."""
        assert rtfx_combinado(6.0, 100.0) == pytest.approx(5.66, abs=0.01)

    def test_taxa_nao_positiva_e_recusada(self):
        """Zero ou negativo não é lentidão — é erro de programação."""
        with pytest.raises(ValueError, match="positiva"):
            rtfx_combinado(3.0, 0.0)


class TestExigenciaDoEstagio:
    def test_calcula_o_minimo_necessario(self):
        """ASR a 4,6× e alvo 3× → o diarizador precisa de 8,6×."""
        assert rtfx_minimo_do_estagio(4.6, alvo=3.0) == pytest.approx(8.6, abs=0.1)

    def test_devolve_None_quando_o_ASR_ja_esta_no_limite(self):
        """Sem folga não existe diarizador rápido o bastante — nem um infinitamente rápido.

        Devolver um número grande aqui sugeriria que basta otimizar. `None` diz a verdade:
        o problema é o ASR, não o diarizador.
        """
        assert rtfx_minimo_do_estagio(3.0, alvo=3.0) is None
        assert rtfx_minimo_do_estagio(2.5, alvo=3.0) is None


class TestPortaoDeOrcamento:
    def test_recusa_quando_a_conta_nao_fecha(self):
        cabe, motivo = cabe_no_orcamento(rtfx_asr=3.58, rtfx_estagio=5.0, alvo=3.0)
        assert cabe is False
        assert "18.5" in motivo or "18,5" in motivo, "o motivo tem de dizer o que faltou"

    def test_aceita_quando_fecha(self):
        cabe, _ = cabe_no_orcamento(rtfx_asr=10.0, rtfx_estagio=50.0, alvo=3.0)
        assert cabe is True

    def test_o_motivo_nunca_e_vazio(self):
        """Recusa sem explicação vira flag que alguém remove por não entender."""
        for d in (1.0, 100.0):
            _, motivo = cabe_no_orcamento(rtfx_asr=4.0, rtfx_estagio=d, alvo=3.0)
            assert motivo.strip()


class TestSemDiarizacao:
    """O padrão: o caso 1:1, que não precisa de modelo nenhum."""

    def test_devolve_o_rotulo_fixo_do_canal(self):
        d = SemDiarizacao("ATENDENTE")
        assert d.rotular(audio=None, sr=16000) == "ATENDENTE"

    def test_custo_declarado_e_infinito_porque_nao_processa_nada(self):
        """RTFx infinito não é exagero: nenhum áudio é processado. A conta tem de refletir isso."""
        assert SemDiarizacao("X").rtfx == float("inf")

    def test_nao_muda_o_rotulo_entre_chamadas(self):
        d = SemDiarizacao("CLIENTE")
        assert d.rotular(None, 16000) == d.rotular(None, 16000) == "CLIENTE"
