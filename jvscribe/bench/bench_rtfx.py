"""Fase 5 — mede RTFx do modelo CTC ONNX na CPU-alvo (i7-1355U).

RTFx = duração_do_áudio ÷ tempo_de_parede (terminologia fixada no blueprint de M1).
Mede sustentado (descarta warmup), single-thread por default (conservador vs RNF-06
≤2 P-cores — ASR pega uma fração do orçamento). A LATÊNCIA p99 casa com RNF-02.

Nota honesta: isto mede a inferência OFFLINE do encoder+CTC (batch, áudio inteiro).
RTFx streaming real (chunk a chunk, com cache) é outro número — fase separada. Mas o
throughput offline é o piso de viabilidade: se não fecha aqui, não fecha streaming.

Uso: python3 bench_rtfx.py [modelo] [--threads 1]   # sem modelo: o artefato canônico
"""

from __future__ import annotations

import argparse
import statistics
import time

import pathlib
import sys

import numpy as np
import onnxruntime as ort

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
from engine import resolver  # noqa: E402


def session_options(threads: int) -> ort.SessionOptions:
    """Config de sessão CPU: intra=threads (orçamento de núcleos), inter=1, opt total."""
    if threads < 1:
        raise ValueError(f"threads deve ser ≥ 1, recebido {threads}")
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return so


def make_session(path: str, threads: int) -> ort.InferenceSession:
    return ort.InferenceSession(path, sess_options=session_options(threads),
                                providers=["CPUExecutionProvider"])


def main():
    ap = argparse.ArgumentParser()
    # Opcional, com default no artefato canônico: exigir o caminho força o operador a
    # escolher um peso, que pode não ser o que o `model_card.json` declara.
    ap.add_argument("model", nargs="?", default=None)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--soak-min", type=float, default=0.0,
                    help="se >0: roda continuamente N min a 10s de áudio, logando RTFx por janela (RNF-04 soak térmico)")
    args = ap.parse_args()

    # Sessão montada à mão de propósito: a configuração É a variável sob teste. O que não
    # se dispensa é validar o par — `resolver` faz isso e devolve os caminhos.
    modelo, _tokens = resolver(args.model, None)
    modelo = str(modelo)
    sess = make_session(modelo, args.threads)
    inputs = {i.name: i for i in sess.get_inputs()}
    print("=== ONNX I/O ===")
    for i in sess.get_inputs():
        print(f"  in : {i.name} {i.shape} {i.type}")
    for o in sess.get_outputs():
        print(f"  out: {o.name} {o.shape} {o.type}")
    print(f"=== RTFx @ {args.threads} thread(s) · modelo: {modelo} ===")

    # fbank 80-dim, 100 frames/s. Valores não afetam o tempo (compute data-independent).
    FPS = 100
    names = list(inputs)

    if args.soak_min > 0:
        # RNF-04: 10s de áudio em loop por N min; RTFx por janela de ~30s revela throttle.
        audio_s = 10.0
        T = int(audio_s * FPS)
        feed = {names[0]: np.random.randn(1, T, 80).astype(np.float32)}
        if len(names) > 1:
            feed[names[1]] = np.array([T], dtype=np.int64)
        for _ in range(args.warmup):
            sess.run(None, feed)
        print(f"=== SOAK {args.soak_min:.0f} min @ {args.threads} thread(s), áudio {audio_s:.0f}s ===")
        t_end = time.perf_counter() + args.soak_min * 60
        win_start = time.perf_counter()
        win_walls = []
        rtfxs = []
        while time.perf_counter() < t_end:
            t0 = time.perf_counter()
            sess.run(None, feed)
            win_walls.append(time.perf_counter() - t0)
            if time.perf_counter() - win_start >= 30:
                mean = statistics.mean(win_walls)
                rtfx = audio_s / mean
                rtfxs.append(rtfx)
                mm, ss = divmod(int(time.perf_counter() - (t_end - args.soak_min * 60)), 60)
                print(f"  t+{mm:02d}:{ss:02d} | RTFx {rtfx:6.1f}× | wall méd {mean*1000:6.1f}ms | n={len(win_walls)}")
                win_start = time.perf_counter(); win_walls = []
        if rtfxs:
            drop = (rtfxs[0] - min(rtfxs)) / rtfxs[0] * 100
            print(f"=== soak: RTFx primeiro={rtfxs[0]:.1f}× min={min(rtfxs):.1f}× "
                  f"queda={drop:.1f}% (RNF-04 exige sustentado ≥80% do pico) ===")
        return

    for audio_s in (5.0, 10.0, 20.0, 30.0):
        T = int(audio_s * FPS)
        feats = np.random.randn(1, T, 80).astype(np.float32)
        lens = np.array([T], dtype=np.int64)
        # nomes de input do icefall ctc onnx: x, x_lens (fallback: primeiros 2)
        names = list(inputs)
        feed = {names[0]: feats}
        if len(names) > 1:
            feed[names[1]] = lens
        for _ in range(args.warmup):
            sess.run(None, feed)
        walls = []
        for _ in range(args.iters):
            t0 = time.perf_counter()
            sess.run(None, feed)
            walls.append(time.perf_counter() - t0)
        walls.sort()
        mean = statistics.mean(walls)
        p50 = walls[len(walls) // 2]
        p95 = walls[min(len(walls) - 1, int(0.95 * len(walls)))]
        p99 = walls[min(len(walls) - 1, int(0.99 * len(walls)))]
        rtfx = audio_s / mean
        print(f"  áudio {audio_s:4.0f}s | RTFx {rtfx:6.1f}× | wall méd {mean*1000:6.1f}ms "
              f"p50 {p50*1000:6.1f} p95 {p95*1000:6.1f} p99 {p99*1000:6.1f}ms")


if __name__ == "__main__":
    main()
