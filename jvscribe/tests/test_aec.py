"""Cancelamento de eco acústico — opcional, e com a troca de RNF declarada.

O problema que motivou: com o áudio saindo pelo alto-falante, o microfone captura o que as caixas
tocam. Os dois canais recebem a MESMA fonte e o sistema produz um diálogo falso — dois falantes
onde há um — **com confiança total**, porque o desenho `mic = atendente / loopback = cliente`
nunca verifica a própria premissa.

Não é diarização. É AEC, o problema clássico de VoIP. E nosso caso é privilegiado: todo AEC exige
o sinal de referência do far-end, e nós **já capturamos o loopback por construção**.

⚠️ **A troca de RNF é consciente e fica registrada.** `[MEDIDO]` nesta CPU o LocalVQE v1.4-AEC
entrega **10,3×** — não os 19× do README, que são de outro hardware. Combinado com o ASR ao vivo
de 3,58× dá **2,65×**, abaixo do RNF-01 de 3×. O dono aceitou 2,5×. Aceitar é legítimo; aceitar
**em silêncio** não é — daí `--aceitar-rtfx`, que rebaixa o alvo *explicitamente* e faz o
relatório dizer que o requisito foi negociado.
"""
from __future__ import annotations

import numpy as np
import pytest

from aec import SemAec, checar_orcamento_do_aec


class TestSemAec:
    """O padrão: nenhum processamento. É a implementação correta com fone de ouvido."""

    def test_devolve_o_mic_intacto(self):
        mic = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        saida = SemAec().processar(mic, np.zeros(3, dtype=np.float32))
        assert np.array_equal(saida, mic)

    def test_nao_copia_o_array_a_toa(self):
        """No caminho quente, cópia por hop é desperdício que ninguém vê."""
        mic = np.zeros(256, dtype=np.float32)
        assert SemAec().processar(mic, mic) is mic

    def test_rtfx_infinito_porque_nada_e_processado(self):
        assert SemAec().rtfx == float("inf")


class TestOrcamento:
    """O portão não bloqueia quando a troca é declarada — mas exige que ela SEJA declarada."""

    def test_recusa_quando_nao_cabe_e_nada_foi_aceito(self):
        ok, motivo = checar_orcamento_do_aec(rtfx_asr=3.58, rtfx_aec=10.3, aceitar=None)
        assert ok is False
        # o valor combinado (2,66×) e o alvo têm de aparecer — casar o dígito exato seria testar
        # arredondamento, não comportamento
        assert "2.6" in motivo and "3" in motivo
        assert "aceitar-rtfx" in motivo, "a recusa tem de dizer COMO destravar"

    def test_aceita_quando_o_dono_rebaixa_o_alvo_explicitamente(self):
        ok, motivo = checar_orcamento_do_aec(rtfx_asr=3.58, rtfx_aec=10.3, aceitar=2.5)
        assert ok is True
        assert "negociado" in motivo.lower() or "aceito" in motivo.lower(), (
            "aceitar em silêncio é o que esta flag existe para impedir"
        )

    def test_recusa_mesmo_com_aceite_quando_nem_o_aceite_e_atingido(self):
        """`--aceitar-rtfx 2.5` não é um cheque em branco: 2,0× continua reprovado."""
        ok, _ = checar_orcamento_do_aec(rtfx_asr=3.0, rtfx_aec=4.0, aceitar=2.5)
        assert ok is False

    def test_o_motivo_sempre_cita_o_alvo_original(self):
        """Quem lê o relatório precisa saber DE QUANTO se abriu mão, não só o valor final."""
        _, motivo = checar_orcamento_do_aec(rtfx_asr=3.58, rtfx_aec=10.3, aceitar=2.5)
        assert "3" in motivo, "o alvo do RNF-01 tem de aparecer"


class TestLocalVqe:
    """A implementação real. Pulada quando a biblioteca não está compilada."""

    def _aec(self):
        localvqe = pytest.importorskip("aec")
        import pathlib
        so = pathlib.Path("/home/paulo/workspace/LocalVQE/ggml/build/bin/liblocalvqe.so")
        gguf = pathlib.Path(
            "/home/paulo/workspace/LocalVQE/modelos/localvqe-v1.4-aec-200K-f32.gguf")
        if not (so.exists() and gguf.exists()):
            pytest.skip("LocalVQE não compilado nesta máquina")
        return localvqe.LocalVqeAec(so, gguf, rtfx=10.3)

    def test_o_hop_e_o_que_a_biblioteca_declara(self):
        """Passar um hop diferente do esperado corrompe o estado interno em silêncio."""
        a = self._aec()
        assert a.hop == 256

    def test_processa_um_hop_e_devolve_o_mesmo_tamanho(self):
        a = self._aec()
        rng = np.random.default_rng(1)
        mic = (rng.standard_normal(a.hop) * 0.1).astype(np.float32)
        ref = (rng.standard_normal(a.hop) * 0.1).astype(np.float32)
        saida = a.processar(mic, ref)
        assert saida.shape == mic.shape and saida.dtype == np.float32

    def test_hop_errado_falha_alto_em_vez_de_corromper(self):
        a = self._aec()
        curto = np.zeros(a.hop // 2, dtype=np.float32)
        with pytest.raises(ValueError, match="hop"):
            a.processar(curto, curto)

    def test_eco_puro_e_atenuado(self):
        """O teste que importa: mic == ref (eco perfeito) deve sair com MENOS energia.

        Se a saída tiver a mesma energia da entrada, o AEC não está fazendo nada — e um AEC que
        não cancela é pior que nenhum, porque custa RTFx e dá a impressão de estar protegendo.
        """
        a = self._aec()
        rng = np.random.default_rng(3)
        sinal = (rng.standard_normal(a.hop) * 0.2).astype(np.float32)
        for _ in range(60):                      # o filtro adaptativo precisa convergir
            saida = a.processar(sinal.copy(), sinal.copy())
        rms_in = float(np.sqrt((sinal**2).mean()))
        rms_out = float(np.sqrt((saida**2).mean()))
        assert rms_out < rms_in, f"nenhuma atenuação: entrada {rms_in:.4f} → saída {rms_out:.4f}"


class AecFalso:
    """Marca o que passou por ele — deixa o teste ver o pareamento, não o filtro."""

    rtfx = 100.0
    hop = 4

    def __init__(self) -> None:
        self.refs_vistas: list[list[float]] = []

    def processar(self, mic, ref):
        self.refs_vistas.append(list(ref))
        return mic * 10.0


class TestCancelamentoDuplo:
    """O pareamento mic↔referência. Onde mora o risco de engolir áudio."""

    def test_sem_aec_devolve_o_mic_intacto(self):
        from aec import CancelamentoDuplo, SemAec

        c = CancelamentoDuplo(SemAec())
        mic = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert np.array_equal(c.limpar(mic), mic)

    def test_o_resto_do_frame_nao_e_descartado(self):
        from aec import CancelamentoDuplo

        c = CancelamentoDuplo(AecFalso())
        c.alimentar_referencia(np.zeros(64, dtype=np.float32))
        saida = c.limpar(np.arange(10, dtype=np.float32))
        # 10 amostras, hop 4 → 8 saem limpas; as 2 finais NÃO somem: voltam no próximo bloco
        assert len(saida) == 8
        resto = c.limpar(np.zeros(6, dtype=np.float32))
        assert len(resto) == 8, "as 2 retidas + 6 novas = 8 → dois frames"
        assert resto[0] == 80.0, "a amostra retida (8.0) é a primeira a sair depois"

    def test_referencia_seca_vira_silencio_e_nao_erro(self):
        from aec import CancelamentoDuplo

        c = CancelamentoDuplo(AecFalso())  # nada alimentado
        saida = c.limpar(np.ones(8, dtype=np.float32))
        assert len(saida) == 8, "sem far-end não há eco — processa contra silêncio"
        assert all(r == [0.0] * 4 for r in c._aec.refs_vistas)

    def test_a_referencia_e_consumida_em_lockstep(self):
        from aec import CancelamentoDuplo

        c = CancelamentoDuplo(AecFalso())
        c.alimentar_referencia(np.arange(12, dtype=np.float32))
        c.limpar(np.zeros(8, dtype=np.float32))
        assert c._aec.refs_vistas == [[0.0, 1.0, 2.0, 3.0], [4.0, 5.0, 6.0, 7.0]]
        assert len(c._ref) == 4, "sobrou referência para o próximo bloco de mic"
