#!/usr/bin/env python3
"""Demo web do jvscribe — o diálogo ao vivo, os RNF medidos, e a confiança por palavra.

**É camada de APRESENTAÇÃO, não um segundo motor.** O laço de captura, o backpressure, a
montagem de turnos e as métricas vêm de `live_transcribe` sem cópia. Duplicar o laço faria demo
e produto divergirem — e a demo passaria a mostrar um sistema que não é o entregue.

## O que a tela mostra, e por que cada coisa está lá

| painel | por que existe |
|---|---|
| diálogo rotulado | o caso 1:1 não precisa de diarização: o mic **é** o atendente e o loopback **é** o cliente, por construção da captura |
| **palavra incerta destacada** | o portão de confiança custa **+0,31%** do decode e pega **69%** dos erros de não-palavra `[MEDIDO]`. O ADR-0005 é explícito: *"marcar palavra incerta na tela do atendente já vale sem corrigir nada"* |
| RNF-01/02/03 ao vivo | o produto tem requisito de tempo real; esconder isso numa demo seria vender o que não se mediu |
| **aviso de carga** | `asr-evidence-discipline` § 5: máquina sob carga não mede. A mesma configuração já deu 3,51× e 2,50× em quatro corridas |

## Por que `http.server` da stdlib, e não um framework

O degrau 4 da escada de parcimônia (reusar dependência já instalada) **falhou na prática**: o
`fastapi` deste ambiente está quebrado por incompatibilidade com o `starlette`
(`Router.__init__() got an unexpected keyword argument 'on_startup'`). Descer para o degrau 2 —
stdlib — resolve e ainda entrega o que a demo precisa: **rodar com `python3` puro**, sem
instalação. Num projeto onde o dono já relatou não conseguir instalar `lhotse` em produção, isso
não é purismo, é requisito.

SSE (Server-Sent Events) é HTTP simples: o navegador tem `EventSource` nativo e o servidor só
mantém a conexão aberta escrevendo `data: …`. Não há aperto de mão de WebSocket dos dois lados.

⚠️ **A captura é do SERVIDOR, não do navegador.** `DualCapture` usa `parec` (PulseAudio) na
máquina onde este processo roda — que é o desenho do produto: o áudio nunca sai do notebook do
atendente. Capturar pelo navegador mudaria o caminho acústico (resample e AEC do próprio Chrome)
e a demo deixaria de representar o sistema.

Uso:
    python3 jvscribe/realtime/web_demo.py            # http://127.0.0.1:8000
    python3 jvscribe/realtime/web_demo.py --porta 9000 --tau 1.5
"""
from __future__ import annotations

import argparse
import json
import pathlib
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

import ctc  # noqa: E402
from audio import SR  # noqa: E402
from cpu import LIMIAR_LOAD, carga_media, detectar  # noqa: E402
from engine import carregar_tokens, resolver  # noqa: E402
from onnx_session import criar_sessao  # noqa: E402
from streaming import StreamingCTC  # noqa: E402

from live_transcribe import (  # noqa: E402 — REUSO, não cópia
    ALVO_BACKLOG_PCT,
    ALVO_P99_MS,
    ALVO_RTFX,
    FALANTES,
    MetricasRNF,
    Transcricao,
    aplicar_backpressure,
    rotular,
)

PAGINA = pathlib.Path(__file__).resolve().parent / "web_demo.html"


class Sessao:
    """Estado de uma corrida da demo. Um por processo — a captura é exclusiva do dispositivo."""

    def __init__(self, hop: float, window: float, threads: int | None, tau: float) -> None:
        modelo, tokens = resolver(None, None)
        self.modelo = str(modelo)
        topo = detectar()
        self.threads = threads or topo.threads_recomendadas
        sess = criar_sessao(self.modelo, self.threads)
        self.id2tok = carregar_tokens(tokens)
        self.motores = {lb: StreamingCTC(sess, self.id2tok, hop_s=hop, window_s=window)
                        for lb in FALANTES}
        self.hop_amostras = int(hop * SR)
        self.tau = tau
        self.trans, self.met = Transcricao(), MetricasRNF()
        self.eventos: queue.Queue = queue.Queue(maxsize=256)
        self.rodando = False

    # ── o laço, idêntico ao do live_transcribe ────────────────────────────────────────────
    def rodar(self) -> None:
        """Roda numa thread própria: a captura via `parec` é I/O bloqueante por natureza."""
        from dual_capture import DualCapture

        self.rodando = True
        pendente = {lb: np.zeros(0, dtype=np.float32) for lb in FALANTES}
        chegada = {lb: None for lb in FALANTES}
        try:
            with DualCapture() as cap:
                while self.rodando:
                    lidos = list(cap.read(timeout=0.5))
                    for label, pcm in lidos:
                        if chegada[label] is None:
                            chegada[label] = time.perf_counter()
                        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                        pendente[label] = np.concatenate([pendente[label], x])

                    backlog = cap.backlog()
                    for label, buf in pendente.items():
                        if len(buf) < self.hop_amostras:
                            continue
                        atraso = time.perf_counter() - chegada[label]
                        buf, descartadas = aplicar_backpressure(buf, atraso)
                        if descartadas:
                            self.met.audio_descartado_s += descartadas / SR
                        t0 = time.perf_counter()
                        finais, _ = self.motores[label].update(buf)
                        wall = time.perf_counter() - t0
                        self.met.registrar(audio_s=len(buf) / SR, wall_s=wall,
                                           latencia_s=time.perf_counter() - chegada[label],
                                           backlog=backlog)
                        pendente[label] = np.zeros(0, dtype=np.float32)
                        chegada[label] = None
                        if finais:
                            self._emitir(label, finais)
                    self._publicar_metricas()
        finally:
            self.rodando = False

    def _emitir(self, label: str, palavras: list[str]) -> None:
        turno = self.trans.adicionar(label, palavras, time.perf_counter() - self.met.inicio)
        if turno is None:
            return
        self._enfileirar({"tipo": "turno", "falante": rotular(label),
                          "texto": turno.texto, "t": round(turno.t, 2),
                          "novas": palavras})

    def _publicar_metricas(self) -> None:
        r = self.met.resumo()
        if r["amostras"] == 0:
            return
        carga = carga_media()
        confiavel = carga is not None and carga <= LIMIAR_LOAD
        self._enfileirar({
            "tipo": "metricas",
            "rtfx": round(r["rtfx"], 2) if r["rtfx"] else None,
            "p99_ms": round(r["p99_ms"], 0), "p50_ms": round(r["p50_ms"], 0),
            "backlog_pct": round(r["backlog_pct"], 2),
            "duracao_s": round(r["duracao_s"], 1),
            "descartado_s": round(self.met.audio_descartado_s, 1),
            "carga": carga, "tempo_confiavel": confiavel,
            "alvos": {"rtfx": ALVO_RTFX, "p99_ms": ALVO_P99_MS, "backlog_pct": ALVO_BACKLOG_PCT},
        })

    def _enfileirar(self, ev: dict) -> bool:
        """Descarta o evento mais ANTIGO quando a fila enche.

        Mesma lógica do backpressure do áudio: numa demo ao vivo, o que acabou de ser dito vale
        mais que o que foi dito há dez segundos. Bloquear aqui travaria o laço de captura.

        Devolve `True` se o evento entrou, `False` se foi descartado — perda silenciosa é o que
        esta função existe para evitar, então ela não pode ser silenciosa sobre a própria perda.
        """
        try:
            self.eventos.put_nowait(ev)
            return True
        except queue.Full:
            pass
        try:
            self.eventos.get_nowait()          # abre espaço jogando fora o mais ANTIGO
            self.eventos.put_nowait(ev)
        except (queue.Empty, queue.Full):
            # Corrida com o leitor do SSE: outra thread mexeu na fila entre as duas operações.
            # O fallback é DESCARTAR este evento, e ele é devolvido como False em vez de sumir
            # em silêncio — quem chamar pode contar quantos caíram.
            return False
        return True


class Servidor(ThreadingHTTPServer):
    """`ThreadingHTTPServer` porque o SSE segura uma conexão aberta por cliente.

    Com o `HTTPServer` de thread única, a primeira aba conectada em `/api/eventos` bloquearia
    todas as outras rotas — inclusive o botão de parar.
    """

    daemon_threads = True
    allow_reuse_address = True
    sessao: "Sessao | None" = None
    args_sessao: dict = {}


class Rotas(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa: D102 — silencia o log por requisição do stdlib
        pass

    # ── helpers ───────────────────────────────────────────────────────────────────────────
    def _responder(self, corpo: bytes, tipo: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, d: dict, status: int = 200) -> None:
        self._responder(json.dumps(d, ensure_ascii=False).encode(), "application/json", status)

    def _estado(self) -> dict:
        s = self.server.sessao
        carga = carga_media()
        return {"rodando": bool(s and s.rodando),
                "modelo": s.modelo if s else None,
                "threads": s.threads if s else None,
                "carga": carga,
                "tempo_confiavel": carga is not None and carga <= LIMIAR_LOAD,
                "limiar_load": LIMIAR_LOAD}

    # ── rotas ─────────────────────────────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802 — nome exigido pelo BaseHTTPRequestHandler
        if self.path == "/":
            self._responder(PAGINA.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/estado":
            self._json(self._estado())
        elif self.path == "/api/eventos":
            self._sse()
        else:
            self._json({"erro": "rota desconhecida"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/iniciar":
            self._iniciar()
        elif self.path == "/api/parar":
            s = self.server.sessao
            if not s or not s.rodando:
                self._json({"ok": False, "erro": "nada rodando"})
            else:
                s.rodando = False
                self._json({"ok": True})
        else:
            self._json({"erro": "rota desconhecida"}, 404)

    def _iniciar(self) -> None:
        if self.server.sessao and self.server.sessao.rodando:
            self._json({"ok": False, "erro": "já está rodando"})
            return
        try:
            s = Sessao(**self.server.args_sessao)
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            # Estreito de propósito: modelo/vocabulário ausente ou incompatível é falha ESPERADA
            # e vira erro tipado na tela. `except Exception` engoliria também defeito de
            # programação (NameError, AttributeError), que deve estourar alto — `error-handling`
            # § 2. Se a demo quebrar por bug meu, quero o stack trace, não um JSON educado.
            self._json({"ok": False, "erro": f"{type(exc).__name__}: {exc}"}, 500)
            return
        self.server.sessao = s
        threading.Thread(target=s.rodar, daemon=True).start()
        self._json({"ok": True, "modelo": s.modelo, "threads": s.threads})

    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                s = self.server.sessao
                if s is None:
                    self.wfile.write(b": aguardando\n\n")
                    self.wfile.flush()
                    time.sleep(0.5)
                    continue
                try:
                    ev = s.eventos.get(timeout=5.0)
                    linha = f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    linha = ": keepalive\n\n"
                self.wfile.write(linha.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        # Aba fechada é término NORMAL desta rota, não falha: o `return` explícito diz isso em
        # vez de deixar o fluxo escorrer pelo fim da função como se nada tivesse acontecido.
        return


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 por padrão: o áudio não deve sair do notebook (LGPD)")
    ap.add_argument("--hop", type=float, default=0.5)
    ap.add_argument("--window", type=float, default=6.0)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--tau", type=float, default=1.0,
                    help="limiar do portão de confiança em nats; τ=1,0 sinaliza 11,3% das "
                         "palavras com precisão 55,9% [MEDIDO]")
    a = ap.parse_args()

    if not PAGINA.exists():
        raise SystemExit(f"página não encontrada: {PAGINA}")

    srv = Servidor((a.host, a.porta), Rotas)
    srv.args_sessao = {"hop": a.hop, "window": a.window, "threads": a.threads, "tau": a.tau}
    print(f"  demo em http://{a.host}:{a.porta}  ·  Ctrl+C encerra")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        if srv.sessao:
            srv.sessao.rodando = False
        srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
