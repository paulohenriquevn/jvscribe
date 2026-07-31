#!/usr/bin/env python3
"""Mede os eixos de otimização do runtime — com repetição e dispersão, não uma corrida só.

Existe porque a primeira varredura deste projeto reportou 158,8 ms e 169,1 ms para DUAS
configurações idênticas (`lvl default` e `lvl=ALL`, sendo `ORT_ENABLE_ALL` o default do ONNX
Runtime). Uma diferença de 35 ms entre configurações iguais é ruído maior que vários dos
efeitos medidos — concluir dali seria escolher por acaso.

Cada configuração roda `--reps` vezes intercaladas (round-robin), para que uma flutuação de
carga não caia toda sobre um candidato. Reporta a **mediana** e o **delta pareado com IC95%**
(bootstrap, `common/stats.py::comparar_pareado`); o veredito de "melhor" só sai quando o
**IC95% do delta não cruza zero**.

⚠️ Este parágrafo dizia "reporta mediana e IQR; o veredito sai quando o IQR não se sobrepõe".
Não era o que o código fazia — `_iqr` existia e nunca foi chamada. O método real é mais forte
(o pareamento remove a variância comum entre configurações, que a sobreposição de IQR ignora),
mas numa ferramenta cujo propósito É rigor de método, descrever o método errado é o defeito
mais caro possível: quem lesse o docstring citaria a técnica errada num artefato de decisão.

Uso:
    python3 jvscribe/tools/runtime_bench.py --audio <wav> [--janela 6] [--reps 15]
"""
from __future__ import annotations

import argparse
import pathlib
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "realtime"))

from artifact import default_model_path  # noqa: E402
from stats import comparar_pareado  # noqa: E402

SR = 16000


def montar_configs(ort):
    """(nome, session_options, batch) — o baseline é sempre o primeiro."""
    L = ort.GraphOptimizationLevel

    def so(intra=4, inter=None, arena=False, lvl=None):
        o = ort.SessionOptions()
        o.intra_op_num_threads = intra
        if inter is not None:
            o.inter_op_num_threads = inter
        o.enable_cpu_mem_arena = arena
        if lvl is not None:
            o.graph_optimization_level = lvl
        return o

    return [
        ("baseline (intra=4, arena OFF)", so(), 1),
        ("arena ON", so(arena=True), 1),
        ("arena ON + inter=4", so(inter=4, arena=True), 1),
        ("arena ON + inter=4 + intra=8", so(intra=8, inter=4, arena=True), 1),
        ("arena ON + inter=4 + intra=8 + batch2", so(intra=8, inter=4, arena=True), 2),
        ("graph opt BASIC (arena ON)", so(arena=True, lvl=L.ORT_ENABLE_BASIC), 1),
    ]


def medir(sessoes, entradas, reps: int) -> dict[str, list[float]]:
    """Round-robin entre configurações: flutuação de carga se espalha, não vicia um candidato."""
    amostras: dict[str, list[float]] = {nome: [] for nome, _, _ in sessoes}
    for _ in range(reps):
        for nome, sess, batch in sessoes:
            x, xl = entradas[batch]
            t0 = time.perf_counter()
            sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
            amostras[nome].append((time.perf_counter() - t0) * 1000 / batch)
    return amostras


def relatar(amostras: dict[str, list[float]], baseline: str) -> int:
    b = amostras[baseline]
    b_med = statistics.median(b)
    print(f"\n  {'configuração':<40} {'mediana':>9}  {'delta pareado (IC95%)':>26}  veredito")
    print("  " + "-" * 100)
    for nome, v in sorted(amostras.items(), key=lambda kv: statistics.median(kv[1])):
        med = statistics.median(v)
        if nome == baseline:
            print(f"  {nome:<40} {med:7.1f} ms  {'—':>26}  baseline")
            continue
        # Pareado pelo kernel compartilhado: `melhor=None` quando o IC cruza zero — a recusa
        # explícita a declarar vencedor sem separação (ver jvscribe/common/stats.py).
        c = comparar_pareado(b, v, rotulo_a="baseline", rotulo_b=nome, unidade="ms")
        lo, hi = c.ic95
        pct = 100 * c.delta_medio / b_med
        vered = ("MELHOR — IC não cruza zero" if c.melhor == nome else
                 "PIOR — IC não cruza zero" if c.conclusivo else
                 "inconclusivo — IC cruza zero")
        print(f"  {nome:<40} {med:7.1f} ms  [{lo:+7.1f}, {hi:+7.1f}] ms {pct:+6.1f}%  {vered}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", type=pathlib.Path, required=True)
    ap.add_argument("--janela", type=float, default=6.0)
    ap.add_argument("--reps", type=int, default=15)
    a = ap.parse_args()

    import onnxruntime as ort
    import soundfile as sf
    from lhotse import Fbank, FbankConfig

    audio, sr = sf.read(str(a.audio), dtype="float32")
    if sr != SR:
        raise SystemExit(f"esperado {SR} Hz, veio {sr} Hz")
    n = int(a.janela * SR)
    buf = np.tile(audio, int(np.ceil(n / len(audio))))[:n]
    feats = np.asarray(Fbank(FbankConfig(num_mel_bins=80)).extract(buf, SR), dtype=np.float32)
    x1 = feats[None]
    entradas = {
        1: (x1, np.array([x1.shape[1]], dtype=np.int64)),
        2: (np.repeat(x1, 2, axis=0), np.array([x1.shape[1]] * 2, dtype=np.int64)),
    }

    modelo = default_model_path()
    print(f"  modelo : {modelo}")
    print(f"  janela : {a.janela:g}s ({x1.shape[1]} frames) · reps: {a.reps} · round-robin")

    configs = montar_configs(ort)
    sessoes = [(nome, ort.InferenceSession(modelo, so, providers=["CPUExecutionProvider"]), b)
               for nome, so, b in configs]
    for _, sess, b in sessoes:                       # aquecimento fora da medição
        x, xl = entradas[b]
        sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})

    return relatar(medir(sessoes, entradas, a.reps), configs[0][0])


if __name__ == "__main__":
    raise SystemExit(main())
