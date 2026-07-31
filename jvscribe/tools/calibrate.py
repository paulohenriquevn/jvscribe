#!/usr/bin/env python3
"""Calibra o runtime para ESTA máquina e emite a configuração — rode ao trocar de hardware.

Nem toda otimização deste projeto é portável. As **algorítmicas** são (cache incremental de
fbank, dreno da captura, backpressure); a **calibração** não:

| parâmetro | portável? | por quê |
|---|---|---|
| `intra_op_num_threads` | não | sai da topologia (P-cores vs E-cores) |
| janela de decode | não | sai da ocupação de CPU desta máquina |
| arena / `inter_op` | provavelmente | é config de runtime, não de hardware |

A janela de 6 s do default não é constante do produto: a de 10 s pedia **104,9% da CPU** neste
i7. Num CPU mais fraco, 6 s também satura; num mais forte, dá para usar mais contexto e ganhar
acurácia. Herdar a constante é pior que medir.

Uso:
    python3 jvscribe/tools/calibrate.py --audio <wav> [--canais 2] [--hop 0.5] [--reps 7]
    python3 jvscribe/tools/calibrate.py --audio <wav> --json config.json

⚠️ Rode com a máquina **ociosa**. Sob carga a medição não separa — comprovado: a mesma
configuração deu RTFx 3,51× / 2,90× / 2,82× / 2,50× com a máquina em load 3–4.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

from artifact import default_model_path  # noqa: E402
from calibracao import TETO_OCUPACAO, janela_maxima, ocupacao  # noqa: E402
from cpu_topology import detectar  # noqa: E402
from onnx_session import criar_sessao  # noqa: E402

SR = 16000
JANELAS = (2.0, 4.0, 6.0, 8.0, 10.0, 12.0)


def _carga_media(base: float) -> float:
    try:
        import os

        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return -1.0


def medir_curva(sess, fb, audio: np.ndarray, reps: int) -> dict[float, float]:
    """`{janela_s: ms mediano de decode}` — mediana para a cauda não dominar."""
    curva: dict[float, float] = {}
    for W in JANELAS:
        n = int(W * SR)
        buf = np.tile(audio, int(np.ceil(n / len(audio))))[:n]
        feats = np.asarray(fb.extract(buf, SR), dtype=np.float32)
        x = feats[None]
        xl = np.array([x.shape[1]], dtype=np.int64)
        for _ in range(2):                                    # aquecimento fora da medição
            sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter()
            sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
            ts.append((time.perf_counter() - t0) * 1000)
        curva[W] = statistics.median(ts)
        print(f"    janela {W:5.1f}s ({x.shape[1]:4d} frames)  {curva[W]:7.1f} ms", flush=True)
    return curva


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", type=pathlib.Path, required=True)
    ap.add_argument("--canais", type=int, default=2, help="2 = mic + loopback (o caso real)")
    ap.add_argument("--hop", type=float, default=0.5)
    ap.add_argument("--reps", type=int, default=7)
    ap.add_argument("--teto", type=float, default=TETO_OCUPACAO)
    ap.add_argument("--json", type=pathlib.Path, default=None)
    a = ap.parse_args()

    import soundfile as sf
    from lhotse import Fbank, FbankConfig

    carga = _carga_media(0)
    topo = detectar()
    modelo = default_model_path()

    print(f"  modelo  : {modelo}")
    print(f"  CPU     : {topo.total} lógicos"
          + (f", híbrida (rápidos {topo.afinidade_taskset()} @ {topo.mhz_max} MHz)"
             if topo.hibrida else " (homogênea)"))
    print(f"  threads : intra={topo.threads_recomendadas} (da topologia)")
    if carga > 1.0:
        print(f"  ⚠️ load average {carga:.1f} — a medição vai ser ruidosa. Rode com a máquina ociosa.")
    print()

    audio, sr = sf.read(str(a.audio), dtype="float32")
    if sr != SR:
        raise SystemExit(f"esperado {SR} Hz, veio {sr} Hz")

    # Fábrica do shared kernel: este script mede o PRODUTO, então tem de usar a
    # mesma sessão que a produção. (`runtime_bench` e `bench_rtfx` mantêm config
    # explícita de propósito — neles a configuração é a variável sob teste.)
    sess = criar_sessao(modelo, topo.threads_recomendadas)
    fb = Fbank(FbankConfig(num_mel_bins=80))

    print(f"  curva de custo ({a.reps} repetições por ponto):")
    curva = medir_curva(sess, fb, audio, a.reps)

    print(f"\n  ocupação com {a.canais} canais a cada {a.hop:g}s (teto {100 * a.teto:.0f}%):")
    for W, ms in sorted(curva.items()):
        occ = ocupacao(ms, a.canais, a.hop)
        print(f"    {W:5.1f}s  {100 * occ:6.1f}%  {'cabe' if occ <= a.teto else 'SATURA'}")

    janela = janela_maxima(curva, a.canais, a.hop, a.teto)
    print()
    if janela is None:
        print("  ❌ NENHUMA janela cabe no orçamento nesta máquina com esta configuração.")
        print("     Opções: menos canais, hop maior, ou hardware com mais folga.")
    else:
        print(f"  ✅ janela recomendada: {janela:g}s "
              f"({100 * ocupacao(curva[janela], a.canais, a.hop):.1f}% de ocupação)")
        print(f"\n  python3 jvscribe/realtime/live_transcribe.py "
              f"--window {janela:g} --hop {a.hop:g} --threads {topo.threads_recomendadas}")

    cfg = {
        "medido_em": "máquina local",
        "load_average_no_inicio": carga,
        "cpu": topo.como_dict(),
        "modelo": modelo,
        "canais": a.canais,
        "hop_s": a.hop,
        "teto_ocupacao": a.teto,
        "curva_ms": curva,
        "janela_recomendada_s": janela,
        "threads_recomendadas": topo.threads_recomendadas,
    }
    if a.json:
        a.json.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  configuração: {a.json}")
    return 0 if janela is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
