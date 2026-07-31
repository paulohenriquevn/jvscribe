#!/usr/bin/env python3
"""Transcrição ao vivo dos DOIS lados da conversa, com rótulo de falante e medição de RNF.

O que faz: captura simultaneamente o microfone (atendente) e o loopback da placa (cliente),
transcreve os dois em tempo real com um motor `StreamingCTC` por canal, e imprime o diálogo
rotulado — ao mesmo tempo em que mede os critérios de real-time do `PRD.md § 6`.

**Por que não há diarização aqui.** No caso 1:1 — o dominante — ela não precisa existir: o
mic É o atendente por construção e o loopback É o cliente. Roteamento de stream custa zero e
acerta 100%. Um modelo de diarização só entra no caso de 3 falantes (M7).

Uso:
    python3 jvscribe/realtime/live_transcribe.py                     # até Ctrl+C
    python3 jvscribe/realtime/live_transcribe.py --duracao 1800      # soak de 30 min (RNF-04)
    python3 jvscribe/realtime/live_transcribe.py --relatorio out.md  # grava a evidência

⚠️ Este script MEDE, não julga sozinho: RNF-04 (estabilidade térmica) exige ≥ 30 min de
execução e RNF-05 exige carga concorrente real (softphone/Zoom ativo). O relatório declara
explicitamente quando essas condições não foram satisfeitas — ver `veredito_condicoes()`.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

from artifact import default_model_path, default_sibling  # noqa: E402
from artifact import validar_par_modelo_vocabulario  # noqa: E402
from cpu_topology import detectar  # noqa: E402
from onnx_session import criar_sessao  # noqa: E402
from streaming import SR, StreamingCTC, load_tokens  # noqa: E402

# mic e loopback são papéis fixos por construção da captura — ver o docstring.
FALANTES = {"mic": "ATENDENTE", "loopback": "CLIENTE"}

# Limiares do PRD § 6. Mudá-los aqui sem mudar o PRD é falsificar evidência.
ALVO_RTFX = 3.0        # RNF-01 — pipeline completo
ALVO_P99_MS = 500.0    # RNF-02 — fim da fala → texto disponível
ALVO_BACKLOG_PCT = 0.1  # RNF-03 — backlog = 0 em 99,9% das amostras
MIN_SOAK_S = 1800.0    # RNF-04 — 30 min; benchmark curto em chip U mente (falácia § 3 #4)

CORES = {"ATENDENTE": "\033[36m", "CLIENTE": "\033[33m"}
DIM, RESET = "\033[2m", "\033[0m"


def rotular(label: str) -> str:
    """Converte o label do stream no papel do falante. Falha alto em label desconhecido."""
    if label not in FALANTES:
        raise ValueError(
            f"label de stream desconhecido: {label!r} — esperado um de {sorted(FALANTES)}. "
            "Atribuir um falante por default trocaria quem disse o quê."
        )
    return FALANTES[label]


def aplicar_backpressure(audio, atraso_s: float, teto_s: float = 2.0):
    """Descarta áudio ANTIGO quando o consumidor ficou para trás. Devolve `(mantido, n)`.

    Achado do soak de 2026-07-31: sem isto, o laço que fica atrasado **nunca recupera** — o
    atraso medido subiu de 392 ms para 18.798 ms e ficou lá, porque cada ciclo chegava tarde
    e o seguinte herdava o débito.

    Num sistema de tempo real áudio velho vale menos que áudio novo: numa ligação, o que o
    cliente acabou de dizer importa mais do que o que ele disse há 15 s. Então o descarte é
    do INÍCIO, preservando a cauda — e nunca esvazia tudo, senão jogaria fora o áudio novo
    junto com o velho.

    A perda é real e deve aparecer no relatório: preferir texto recente a texto completo é
    uma troca, não um conserto grátis.
    """
    if atraso_s <= teto_s or len(audio) == 0:
        return audio, 0
    manter = max(1, int(teto_s * SR))
    if len(audio) <= manter:
        return audio, 0
    descartar = len(audio) - manter
    return audio[descartar:], descartar


@dataclass
class Turno:
    falante: str
    texto: str
    t: float


class Transcricao:
    """Diálogo montado em turnos: palavras seguidas do mesmo falante viram um turno só."""

    def __init__(self) -> None:
        self.turnos: list[Turno] = []

    def adicionar(self, label: str, palavras: list[str], t: float) -> Turno | None:
        """Anexa palavras confirmadas. Devolve o turno tocado, ou None se nada foi dito.

        Rodada de decode sem palavra confirmada é o caso COMUM (LocalAgreement-2 só confirma
        o que se repetiu) — não pode abrir turno vazio.
        """
        if not palavras:
            return None
        falante = rotular(label)
        if self.turnos and self.turnos[-1].falante == falante:
            self.turnos[-1].texto += " " + " ".join(palavras)
            return self.turnos[-1]
        self.turnos.append(Turno(falante, " ".join(palavras), t))
        return self.turnos[-1]

    def linhas(self) -> list[str]:
        return [f"[{x.t:7.2f}s] {x.falante}: {x.texto}" for x in self.turnos]


@dataclass
class Criterio:
    """Resultado de um critério de RNF — sempre com o medido AO LADO do alvo."""

    aprovado: bool
    medido: str
    alvo: str
    nota: str = ""


@dataclass
class MetricasRNF:
    """Acumula as amostras de decode e traduz em veredito contra o `PRD.md § 6`."""

    audio_total_s: float = 0.0
    wall_total_s: float = 0.0
    latencias_s: list[float] = field(default_factory=list)
    com_backlog: int = 0
    audio_descartado_s: float = 0.0    # backpressure: a perda tem de ser VISÍVEL
    inicio: float = field(default_factory=time.perf_counter)

    def registrar(self, audio_s: float, wall_s: float, latencia_s: float, backlog: int) -> None:
        self.audio_total_s += audio_s
        self.wall_total_s += wall_s
        self.latencias_s.append(latencia_s)
        if backlog > 0:
            self.com_backlog += 1

    @staticmethod
    def _percentil(ordenadas: list[float], q: float) -> float:
        """Percentil por rank mais próximo — sem interpolação, para o p99 enxergar a cauda."""
        if not ordenadas:
            raise ValueError("percentil de amostra vazia")
        k = max(0, min(len(ordenadas) - 1, int(round(q * (len(ordenadas) - 1)))))
        return ordenadas[k]

    def resumo(self) -> dict:
        n = len(self.latencias_s)
        if n == 0:
            return {"amostras": 0, "rtfx": None, "p50_ms": None, "p95_ms": None,
                    "p99_ms": None, "backlog_pct": None, "duracao_s": 0.0}
        ord_ = sorted(self.latencias_s)
        return {
            "amostras": n,
            "rtfx": self.audio_total_s / self.wall_total_s if self.wall_total_s else None,
            "p50_ms": self._percentil(ord_, 0.50) * 1000,
            "p95_ms": self._percentil(ord_, 0.95) * 1000,
            "p99_ms": self._percentil(ord_, 0.99) * 1000,
            "backlog_pct": 100.0 * self.com_backlog / n,
            "duracao_s": time.perf_counter() - self.inicio,
        }

    def veredito(self) -> dict[str, Criterio]:
        r = self.resumo()
        if r["amostras"] == 0:
            vazio = Criterio(False, "sem amostras", "—", "nenhum decode registrado")
            return {"RNF-01": vazio, "RNF-02": vazio, "RNF-03": vazio}
        return {
            "RNF-01": Criterio(
                r["rtfx"] >= ALVO_RTFX, f"{r['rtfx']:.2f}×", f"≥ {ALVO_RTFX:g}×",
                "RTFx sustentado do pipeline completo"),
            "RNF-02": Criterio(
                r["p99_ms"] <= ALVO_P99_MS, f"p99 {r['p99_ms']:.0f} ms",
                f"≤ {ALVO_P99_MS:g} ms", f"p50 {r['p50_ms']:.0f} ms · p95 {r['p95_ms']:.0f} ms"),
            "RNF-03": Criterio(
                r["backlog_pct"] <= ALVO_BACKLOG_PCT,
                f"backlog presente em {r['backlog_pct']:.1f}%".replace(".", ","),
                f"≤ {ALVO_BACKLOG_PCT:g}% das amostras",
                f"{self.com_backlog} de {r['amostras']} amostras"),
        }

    def veredito_condicoes(self, carga_declarada: bool) -> dict[str, Criterio]:
        """RNF-04 e RNF-05 dependem da CONDIÇÃO da execução, não do que foi medido.

        Separados de propósito: um RTFx excelente em 40 s de execução sem carga não diz nada
        sobre um chip U de 15 W numa ligação de meia hora.
        """
        dur = self.resumo()["duracao_s"]
        return {
            "RNF-04": Criterio(
                dur >= MIN_SOAK_S, f"{dur / 60:.1f} min de execução",
                f"≥ {MIN_SOAK_S / 60:g} min",
                "abaixo disso a medição pega o turbo e mente sobre o regime térmico"),
            "RNF-05": Criterio(
                carga_declarada, "carga concorrente declarada" if carga_declarada
                else "NÃO declarada", "softphone/Zoom ativo",
                "use --com-carga apenas se houver de fato carga concorrente rodando"),
        }


def render_relatorio(m: MetricasRNF, t: Transcricao, carga: bool, modelo: str) -> str:
    r = m.resumo()
    L = ["# Transcrição ao vivo — evidência de RNF", "",
         f"- modelo: `{modelo}`",
         f"- duração: {r['duracao_s'] / 60:.1f} min · amostras de decode: {r['amostras']}",
         f"- áudio processado: {m.audio_total_s:.1f} s em {m.wall_total_s:.1f} s de CPU",
         (f"- ⚠️ **{m.audio_descartado_s:.1f} s de áudio DESCARTADO** por backpressure "
          f"({100 * m.audio_descartado_s / max(m.audio_total_s, 1e-9):.1f}%) — o laço ficou "
          "para trás e preferiu texto recente a texto completo"
          if m.audio_descartado_s > 0 else "- nenhum áudio descartado por backpressure"), "",
         "## Critérios medidos", "", "| critério | medido | alvo | veredito |", "|---|---|---|---|"]
    for chave, c in {**m.veredito(), **m.veredito_condicoes(carga)}.items():
        L.append(f"| {chave} | {c.medido} | {c.alvo} | {'✅' if c.aprovado else '❌'} |")
    L += ["", "> RNF-04 e RNF-05 são condições da execução, não resultados: um RTFx alto numa",
          "> corrida curta e sem carga não sustenta conclusão sobre chip U de 15 W.",
          "", "## Diálogo", ""]
    L += t.linhas() or ["_(nenhuma fala transcrita)_"]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=None)
    ap.add_argument("--tokens", default=None)
    ap.add_argument("--duracao", type=float, default=0.0, help="segundos; 0 = até Ctrl+C")
    # Defaults MEDIDOS, não escolhidos: o decode custa ~172 ms numa janela de 6 s (mediana de
    # 5, i7 12-core, int8, 4 threads). Dois canais a cada 0,5 s ocupam 69% da CPU. Com a
    # janela de 10 s o custo sobe para 262 ms e a ocupação passa de 100% — satura e o backlog
    # cresce sem limite. Ver `wiki/medicoes/m6-rnf-ao-vivo.md`.
    ap.add_argument("--hop", type=float, default=0.5, help="intervalo de re-decode por canal (s)")
    ap.add_argument("--window", type=float, default=6.0, help="janela redecodificada (s) — ver o envelope medido")
    ap.add_argument("--threads", type=int, default=None,
                    help="intra_op; default = metade dos lógicos RÁPIDOS (ver cpu_topology)")
    ap.add_argument("--relatorio", type=pathlib.Path, default=None)
    ap.add_argument("--com-carga", action="store_true",
                    help="declara que há carga concorrente real rodando (RNF-05)")
    a = ap.parse_args()

    from dual_capture import DualCapture

    modelo = a.model or default_model_path()
    tokens = a.tokens or default_sibling("tokens.txt")
    # Fail-fast do par (modelo, vocabulário): trocar o tokens.txt produz português PLAUSÍVEL
    # e errado, sem erro nenhum (CLAUDE.md § O modelo, fato 3). Validar aqui é o que separa
    # "transcrição ruim inexplicável" de um erro que diz o que aconteceu.
    validar_par_modelo_vocabulario(pathlib.Path(modelo).parent, tokens_path=tokens)
    print(f"{DIM}[init] modelo: {modelo}{RESET}", flush=True)

    # A topologia decide só a CONTAGEM de threads. Medido no soak de 2 canais: intra=2 dá
    # RTFx 6,88× contra 4,95× de intra=6 e 3,94× de intra=12 — mais threads gastam mais
    # instruções em spin-wait de barreira do que em conta. Afinidade NÃO é aplicada: ela vaza
    # para os `parec` da captura e derrubou o RTFx de 4,60× para 2,33% ao vivo.
    topo = detectar()
    threads = a.threads or topo.threads_recomendadas
    print(f"{DIM}[init] CPU: {topo.total} lógicos"
          + (f", híbrida (rápidos {topo.afinidade_taskset()} @ {topo.mhz_max} MHz)" if topo.hibrida else "")
          + f" · intra={threads} (sem afinidade — ver cpu_topology)"
          + f"{RESET}", flush=True)

    # Fábrica do shared kernel — a mesma configuração medida para todos os entrypoints.
    sess = criar_sessao(modelo, threads)
    id2tok = load_tokens(tokens)

    # Uma sessão ONNX compartilhada pelos dois canais (`run()` é thread-safe e o modelo tem
    # 68 MB — duplicar custaria memória sem ganho); um StreamingCTC por canal, porque o
    # ESTADO (buffer, palavras confirmadas) é por falante.
    motores = {lb: StreamingCTC(sess, id2tok, hop_s=a.hop, window_s=a.window) for lb in FALANTES}
    pendente = {lb: np.zeros(0, dtype=np.float32) for lb in FALANTES}
    chegada = {lb: None for lb in FALANTES}

    trans, met = Transcricao(), MetricasRNF()
    t_ini = time.perf_counter()
    hop_amostras = int(a.hop * SR)

    print(f"{DIM}[init] falando: ATENDENTE = mic · CLIENTE = loopback. Ctrl+C encerra.{RESET}\n",
          flush=True)
    try:
        with DualCapture() as cap:
            while True:
                if a.duracao and time.perf_counter() - t_ini >= a.duracao:
                    break
                for label, pcm in cap.read(timeout=0.5):
                    if chegada[label] is None:
                        chegada[label] = time.perf_counter()
                    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                    pendente[label] = np.concatenate([pendente[label], x])

                backlog = cap.backlog()
                for label, buf in pendente.items():
                    if len(buf) < hop_amostras:
                        continue
                    atraso = time.perf_counter() - chegada[label]
                    buf, descartadas = aplicar_backpressure(buf, atraso)
                    if descartadas:
                        met.audio_descartado_s += descartadas / SR
                    t0 = time.perf_counter()
                    finais, _ = motores[label].update(buf)
                    wall = time.perf_counter() - t0
                    met.registrar(audio_s=len(buf) / SR, wall_s=wall,
                                  latencia_s=time.perf_counter() - chegada[label],
                                  backlog=sum(backlog.values()))
                    pendente[label] = np.zeros(0, dtype=np.float32)
                    chegada[label] = None
                    turno = trans.adicionar(label, finais, time.perf_counter() - t_ini)
                    if turno is not None:
                        cor = CORES[turno.falante]
                        print(f"{cor}{turno.falante}{RESET}: {' '.join(finais)}", flush=True)
    except KeyboardInterrupt:
        print(f"\n{DIM}[fim] encerrado pelo usuário{RESET}", flush=True)

    rel = render_relatorio(met, trans, a.com_carga, modelo)
    print("\n" + rel)
    if a.relatorio:
        a.relatorio.write_text(rel, encoding="utf-8")
        print(f"{DIM}relatório: {a.relatorio}{RESET}")
    return 0 if all(c.aprovado for c in met.veredito().values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
