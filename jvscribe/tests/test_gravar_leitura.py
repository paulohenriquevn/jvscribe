"""O portão de nível do gravador de leitura — fail-fast antes de a pessoa gravar em vão.

A alternativa é descobrir depois de 75 s de leitura que o sinal estava fraco demais para medir
qualquer coisa. `error-handling` § 2: valide na entrada, e devolva o MOTIVO, não um booleano
solto — quem chamou precisa saber o que fazer, não só que deu errado.
"""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "eval"))

from gravar_leitura import PICO_MINIMO, nivel_e_utilizavel  # noqa: E402


def _sinal(pico: float, n: int = 16000) -> np.ndarray:
    x = np.random.default_rng(3).standard_normal(n).astype(np.float32)
    return (x / np.abs(x).max() * pico).astype(np.float32)


class TestPortaoDeNivel:
    def test_fala_proxima_passa(self):
        """RMS de fala próxima fica em 0,05–0,20 — bem acima do piso."""
        ok, motivo = nivel_e_utilizavel(_sinal(0.30))
        assert ok and "pico" in motivo

    def test_nivel_baixo_reprova_e_diz_o_que_fazer(self):
        """`[MEDIDO]` mic distante deu pico ~0,13 e RMS 0,015 — perto do inutilizável."""
        ok, motivo = nivel_e_utilizavel(_sinal(PICO_MINIMO / 2))
        assert not ok
        assert "aproxime-se" in motivo and "regrave" in motivo

    def test_clipado_reprova(self):
        """Pico saturado destrói a forma de onda — o modelo veria distorção, não fala."""
        x = _sinal(0.5)
        x[10] = 1.0
        ok, motivo = nivel_e_utilizavel(x)
        assert not ok and "CLIPADO" in motivo

    def test_gravacao_vazia_reprova_com_motivo_proprio(self):
        """Zero amostras é falha de DISPOSITIVO, não de nível — a mensagem tem de distinguir."""
        ok, motivo = nivel_e_utilizavel(np.zeros(0, dtype=np.float32))
        assert not ok and "vazia" in motivo

    def test_o_motivo_nunca_e_vazio(self):
        """Mensagem genérica é o anti-pattern; toda recusa carrega diagnóstico."""
        for x in (_sinal(0.30), _sinal(0.001), np.zeros(0, dtype=np.float32)):
            _, motivo = nivel_e_utilizavel(x)
            assert motivo.strip()
