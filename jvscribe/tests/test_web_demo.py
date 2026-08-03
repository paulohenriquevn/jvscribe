"""A demo web — as rotas e a única lógica dela que não é apresentação.

O laço de captura, backpressure e métricas **não** são testados aqui: eles vêm de
`live_transcribe` por reuso e já têm testes próprios. Duplicar a cobertura daria a impressão
falsa de que a demo tem um motor seu.
"""
import json
import pathlib
import sys
import threading
import urllib.request

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "realtime"))
sys.path.insert(0, str(RAIZ / "common"))


@pytest.fixture(scope="module")
def servidor():
    """Sobe o servidor real numa porta efêmera — sem tocar no microfone."""
    from web_demo import Rotas, Servidor

    srv = Servidor(("127.0.0.1", 0), Rotas)
    srv.args_sessao = {"hop": 0.5, "window": 6.0, "threads": 1, "tau": 1.0}
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def pegar(base, rota, metodo="GET"):
    req = urllib.request.Request(base + rota, method=metodo)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read()


class TestRotas:
    def test_a_pagina_e_servida(self, servidor):
        status, corpo = pegar(servidor, "/")
        assert status == 200
        assert b"jvscribe" in corpo and b"EventSource" in corpo

    def test_estado_declara_se_o_tempo_e_confiavel(self, servidor):
        """O consumidor precisa saber se pode acreditar no RTFx — não só recebê-lo."""
        _, corpo = pegar(servidor, "/api/estado")
        d = json.loads(corpo)
        assert d["rodando"] is False
        assert "tempo_confiavel" in d and isinstance(d["tempo_confiavel"], bool)
        assert d["limiar_load"] > 0

    def test_parar_sem_sessao_recusa_tipado(self, servidor):
        """Fail-fast: não fingir sucesso quando não há nada para parar."""
        _, corpo = pegar(servidor, "/api/parar", "POST")
        d = json.loads(corpo)
        assert d["ok"] is False and "nada rodando" in d["erro"]

    def test_rota_desconhecida_e_404(self, servidor):
        with pytest.raises(urllib.error.HTTPError) as e:
            pegar(servidor, "/nao-existe")
        assert e.value.code == 404


class TestFilaDeEventos:
    """A única regra de negócio da camada: o que fazer quando o navegador não acompanha."""

    def _sessao_falsa(self):
        from web_demo import Sessao
        s = Sessao.__new__(Sessao)          # sem carregar modelo — só a fila interessa
        import queue
        s.eventos = queue.Queue(maxsize=3)
        return s

    def test_descarta_o_evento_mais_ANTIGO_quando_enche(self):
        """Numa demo ao vivo, o que acabou de ser dito vale mais que o de dez segundos atrás.

        Bloquear aqui travaria o laço de captura — o mesmo raciocínio do backpressure do áudio.
        """
        s = self._sessao_falsa()
        for i in range(5):
            s._enfileirar({"n": i})
        restantes = [s.eventos.get_nowait()["n"] for _ in range(3)]
        assert restantes == [2, 3, 4], "deveria manter os mais RECENTES"

    def test_nunca_bloqueia(self):
        s = self._sessao_falsa()
        for i in range(200):
            s._enfileirar({"n": i})        # se bloqueasse, o teste travaria
        assert s.eventos.qsize() == 3
