#!/usr/bin/env python3
"""Soak com o modelo REAL: mede degradação ao longo do tempo, não numa foto.

Complementa `jvscribe/tests/test_stress_invariants.py`, que é rápido e usa sessão falsa para
caber em CI. Aqui roda o ONNX de verdade, em relógio de parede, para responder o que um teste
curto não pode: **o RTFx do minuto 30 é o mesmo do minuto 1?** (RNF-04). O i7-1355U é um chip
U de 15 W e não sustenta turbo — benchmark de 30 s mede o turbo e mente
(`asr-evidence-discipline.md` § 3, falácia #4).

Alimenta N canais em paralelo no ritmo do tempo real, a partir de um diretório de áudio, e
reporta por janela de minuto: RTFx, p99 de latência, RSS e tamanho do estado do motor.

Uso:
    python3 jvscribe/bench/stress_test.py --audio-dir <wavs> --minutos 30
    python3 jvscribe/bench/stress_test.py --audio-dir <wavs> --minutos 5 --canais 4
"""
from __future__ import annotations

import argparse
import os
import pathlib
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

from artifact import default_model_path  # noqa: E402
from engine import Motor  # noqa: E402
from audio import SR  # taxa do domínio de áudio
from streaming import StreamingCTC  # noqa: E402

# Mesmo limiar do `calibrate.py` — acima disto a medição vira ruído de contenção, e o
# veredito de RNF-04 deixa de valer (`asr-evidence-discipline.md` § 5).
LIMIAR_LOAD = 1.0


def _rss_mb() -> float | None:
    """RSS do processo em MB, via /proc — sem depender de psutil."""
    try:
        with open("/proc/self/statm") as f:
            paginas = int(f.read().split()[1])
        return paginas * os.sysconf("SC_PAGE_SIZE") / 1e6
    except (OSError, IndexError, ValueError):
        return None


def _carregar_audio(d: pathlib.Path, limite: int = 40) -> np.ndarray:
    """Concatena áudios num sinal contínuo — uma ligação não vem em arquivos separados."""
    import soundfile as sf

    partes = []
    for w in sorted(d.glob("*.wav"))[:limite]:
        x, sr = sf.read(str(w), dtype="float32")
        if sr != SR:
            continue
        partes.append(x)
    if not partes:
        raise SystemExit(f"nenhum .wav a {SR} Hz em {d}")
    return np.concatenate(partes)


class _Janela:
    """Acumula as amostras de um minuto para comparar minuto a minuto."""

    load: float | None = None

    def __init__(self) -> None:
        self.audio_s = 0.0
        self.wall_s = 0.0
        self.lat: list[float] = []

    def add(self, audio_s: float, wall_s: float, lat_s: float) -> None:
        self.audio_s += audio_s
        self.wall_s += wall_s
        self.lat.append(lat_s)

    def rtfx(self) -> float:
        return self.audio_s / self.wall_s if self.wall_s else 0.0

    def p99_ms(self) -> float:
        if not self.lat:
            return 0.0
        o = sorted(self.lat)
        return o[min(len(o) - 1, int(round(0.99 * (len(o) - 1))))] * 1000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio-dir", type=pathlib.Path, required=True)
    ap.add_argument("--minutos", type=float, default=30.0)
    ap.add_argument("--canais", type=int, default=2, help="2 = mic + loopback (o caso real)")
    ap.add_argument("--hop", type=float, default=0.5)
    ap.add_argument("--window", type=float, default=6.0)
    ap.add_argument("--threads", type=int, default=min(8, max(2, (os.cpu_count() or 4) // 2)))
    ap.add_argument("--relatorio", type=pathlib.Path, default=None)
    a = ap.parse_args()

    audio = _carregar_audio(a.audio_dir)
    modelo = default_model_path()
    # Fábrica do shared kernel: este script mede o PRODUTO, então tem de usar a
    # mesma sessão que a produção. (`runtime_bench` e `bench_rtfx` mantêm config
    # explícita de propósito — neles a configuração é a variável sob teste.)
    motor = Motor.carregar(str(modelo), None, a.threads)
    sess, id2tok = motor.sessao, motor.id2tok
    motores = [StreamingCTC(sess, id2tok, hop_s=a.hop, window_s=a.window)
               for _ in range(a.canais)]

    passo = int(a.hop * SR)
    total_passos = int(a.minutos * 60 / a.hop)
    print(f"  modelo : {modelo}")
    print(f"  soak   : {a.minutos:g} min · {a.canais} canais · janela {a.window:g}s · "
          f"hop {a.hop:g}s · intra={a.threads} inter={max(2, a.threads // 2)}")
    print(f"  áudio  : {len(audio) / SR:.0f}s em loop\n")
    print(f"  {'min':>4} {'RTFx':>7} {'p99(ms)':>9} {'RSS(MB)':>9} {'frames':>8} {'commit':>7}")
    print("  " + "-" * 50)

    janelas: list[_Janela] = []
    atual = _Janela()
    t_ini = time.perf_counter()
    minuto = 0
    pos = 0
    for i in range(total_passos):
        alvo = t_ini + i * a.hop                      # ritmo de tempo real, não o mais rápido
        agora = time.perf_counter()
        if agora < alvo:
            time.sleep(alvo - agora)
        chunk = np.take(audio, range(pos, pos + passo), mode="wrap")
        pos = (pos + passo) % len(audio)
        for m in motores:
            t0 = time.perf_counter()
            m.update(chunk)
            dt = time.perf_counter() - t0
            atual.add(a.hop, dt, time.perf_counter() - alvo)
        m0 = motores[0]
        if (i + 1) * a.hop >= (minuto + 1) * 60:
            atual.load = os.getloadavg()[0]
            janelas.append(atual)
            print(f"  {minuto + 1:>4} {atual.rtfx():>7.2f} {atual.p99_ms():>9.0f} "
                  f"{(_rss_mb() or 0):>9.0f} {len(m0.cache.features()):>8} "
                  f"{len(m0.committed):>7}", flush=True)
            atual = _Janela()
            minuto += 1

    if not janelas:
        janelas = [atual]
    primeira, ultima = janelas[0], janelas[-1]
    razao = ultima.rtfx() / primeira.rtfx() if primeira.rtfx() else 0.0
    rtfx_min = min(j.rtfx() for j in janelas)

    # Carga: um soak numa máquina ocupada mede contenção, não estabilidade térmica. O
    # `calibrate.py` já avisava acima de load 1,0; esta ferramenta emitia "RNF-04: FALHA"
    # sem sequer olhar — um veredito que a § 5 da disciplina de evidência proíbe
    # (`asr-evidence-discipline.md`: "máquina sob carga não mede"). Medido em 2026-07-31:
    # com load 5-14 o RTFx variou 1,65-4,59 sem tendência, e os dois piores minutos
    # coincidiram com os picos de load — contenção, não térmico.
    cargas = [j.load for j in janelas if j.load is not None]
    load_mediana = statistics.median(cargas) if cargas else None
    contaminado = load_mediana is not None and load_mediana > LIMIAR_LOAD

    L = ["", "## Veredito", "",
         f"- RTFx minuto 1: **{primeira.rtfx():.2f}×** · minuto {len(janelas)}: "
         f"**{ultima.rtfx():.2f}×** · mínimo: {rtfx_min:.2f}×",
         f"- **RNF-04** (último ÷ primeiro ≥ 0,80): **{razao:.2f}** → "
         f"{'INDETERMINADO (carga)' if contaminado else 'PASSA' if razao >= 0.80 else 'FALHA'}"
         + ("" if len(janelas) >= 30 else
            f"  ⚠️ só {len(janelas)} min de soak; o critério pede 30"),
         f"- RTFx sustentado ≥ 3× em toda janela: "
         f"{'sim' if rtfx_min >= 3.0 else f'NÃO (mínimo {rtfx_min:.2f}×)'}",
         f"- p99 de latência: {statistics.median([j.p99_ms() for j in janelas]):.0f} ms "
         f"(mediana das janelas)",
         f"- RSS final: {(_rss_mb() or 0):.0f} MB",
         "",
         f"- load average mediano durante o soak: "
         f"{'não medido' if load_mediana is None else f'{load_mediana:.1f}'}",
         ""]
    if contaminado:
        L += ["> ⚠️ **VEREDITO DE RNF-04 INVÁLIDO — máquina sob carga** "
              f"(load mediano {load_mediana:.1f} > {LIMIAR_LOAD:g}). O que se mede aqui é "
              "contenção por CPU, não estabilidade térmica. Continuam VÁLIDOS (não dependem "
              "de tempo): ausência de vazamento de memória (curva de RSS) e o teto de estado "
              "do motor (coluna `commit`). Repita em máquina ociosa para concluir sobre RNF-04.",
              ""]
    L += ["> Sem carga concorrente declarada — RNF-05 não foi exercitado. Rode um softphone "
          "em paralelo para que o número valha para o cenário de produção."]
    saida = "\n".join(L)
    print(saida)
    if a.relatorio:
        a.relatorio.write_text(
            f"# Soak de {a.minutos:g} min — {a.canais} canais\n\n"
            f"modelo: `{modelo}`\n{saida}\n", encoding="utf-8")
        print(f"\n  relatório: {a.relatorio}")
    if contaminado:
        return 2   # indeterminado != reprovado — não deixe um CI ocupado 'falhar' o RNF
    return 0 if razao >= 0.80 and rtfx_min >= 3.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
