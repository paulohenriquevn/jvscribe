"""O backpressure do caminho de UM canal — o defeito que fez a demo parecer muda.

Sem ele, `mic_transcribe` processava todo chunk da fila num laço bloqueante. Com a CPU
saturada a fila crescia sem limite: 401% de CPU, 3,0 GB de RAM `[MEDIDO]`, e o texto que saía
era de MINUTOS atrás — do lado do usuário, indistinguível de "não transcreve nada".

`live_transcribe` já tinha a proteção desde o soak que mediu o atraso subir de 392 ms para
18.798 ms e ficar lá. Este arquivo ficou de fora. O mesmo defeito em dois lugares, corrigido
num só, é o que estes testes existem para impedir de voltar.
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "realtime"))
sys.path.insert(0, str(RAIZ / "common"))

from mic_transcribe import atraso_da_fila  # noqa: E402


class TestAtrasoDaFila:
    """Quanto áudio está esperando para ser processado — a entrada do backpressure."""

    def test_fila_vazia_nao_tem_atraso(self):
        assert atraso_da_fila(0, amostras_por_chunk=8000) == 0.0

    def test_atraso_cresce_com_a_fila(self):
        """10 chunks de 0,5 s esperando = 5 s de atraso."""
        assert atraso_da_fila(10, amostras_por_chunk=8000) == 5.0

    def test_o_atraso_dispara_o_descarte(self):
        """Acima do teto de 2 s o backpressure tem de agir — senão nunca recupera."""
        import numpy as np

        from live_transcribe import aplicar_backpressure

        atraso = atraso_da_fila(20, amostras_por_chunk=8000)   # 10 s de fila
        assert atraso > 2.0
        _, descartadas = aplicar_backpressure(np.zeros(16000 * 6, dtype=np.float32), atraso)
        assert descartadas > 0, "com 10 s de atraso o descarte tem de acontecer"


def test_o_backpressure_e_REUSADO_do_live_transcribe():
    """Guarda contra a cópia — foi a divergência entre os dois arquivos que causou o defeito."""
    import mic_transcribe

    assert mic_transcribe.aplicar_backpressure.__module__ == "live_transcribe"
