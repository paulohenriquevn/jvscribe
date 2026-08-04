#!/usr/bin/env python3
"""E4 — beam search CTC: **custo antes de ganho**.

Protocolo: fase E4 do pré-registro do portão de confiança.

A ordem é invertida de propósito. `real_word_hyp` é **36,6%** do erro — o maior bloco, e o único
que nenhuma outra fase toca — mas se o beam não couber no RNF-07 (RTFx ≥ 6×), o ganho é
irrelevante. Mede-se o custo primeiro, e o custo pode matar a fase sozinho.

⚠️ **Este beam não tem modelo de linguagem.** Em CTC puro, beam sem LM rende quase nada — a
independência condicional entre frames faz o beam reencontrar o caminho greedy. O beam existe
aqui para **medir o custo**, que é o portão. Se o custo passar, o LM entra com `/deps-audit`
próprio (`pyctcdecode` + `kenlm` são os candidatos, e nenhum está instalado).

Medir o custo sem LM é um teste **de um lado só**, e válido: o LM só encarece. Se o beam nu já
não couber, com LM cabe menos.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
import ctc  # noqa: E402
from engine import Motor  # noqa: E402

NEG_INF = -float("inf")


def _soma_log(a: float, b: float) -> float:
    if a == NEG_INF:
        return b
    if b == NEG_INF:
        return a
    m = max(a, b)
    return m + math.log(math.exp(a - m) + math.exp(b - m))


def beam_prefixo(log_probs, largura: int, blank: int = ctc.BLANK, poda: int = 12) -> list[int]:
    """Beam search de prefixo CTC — a formulação canônica de Graves.

    Cada prefixo carrega duas probabilidades: terminar em blank (`pb`) e terminar em não-blank
    (`pnb`). É essa separação que faz o colapso ficar correto sob busca — sem ela, repetição
    adjacente e blank não se distinguem e o beam produz texto duplicado.

    `poda` limita os candidatos por frame aos `poda` tokens mais prováveis: sem isso o custo é
    `T × largura × V` com V=503, e o que se mede vira o laço em Python, não o algoritmo.
    """
    feixe: dict[tuple[int, ...], tuple[float, float]] = {(): (0.0, NEG_INF)}
    for quadro in log_probs:
        candidatos = np.argpartition(quadro, -poda)[-poda:]
        novo: dict[tuple[int, ...], list[float]] = defaultdict(lambda: [NEG_INF, NEG_INF])
        for prefixo, (pb, pnb) in feixe.items():
            total = _soma_log(pb, pnb)
            for tid in candidatos:
                tid = int(tid)
                p = float(quadro[tid])
                if tid == blank:
                    alvo = novo[prefixo]
                    alvo[0] = _soma_log(alvo[0], total + p)
                    continue
                if prefixo and tid == prefixo[-1]:
                    # repetição: só estende se veio de blank; senão engorda o mesmo prefixo
                    novo[prefixo][1] = _soma_log(novo[prefixo][1], pnb + p)
                    estendido = novo[prefixo + (tid,)]
                    estendido[1] = _soma_log(estendido[1], pb + p)
                else:
                    estendido = novo[prefixo + (tid,)]
                    estendido[1] = _soma_log(estendido[1], total + p)
        feixe = dict(
            sorted(
                ((k, (v[0], v[1])) for k, v in novo.items()),
                key=lambda kv: -_soma_log(*kv[1]),
            )[:largura]
        )
    melhor = max(feixe.items(), key=lambda kv: _soma_log(*kv[1]))[0]
    return list(melhor)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--larguras", type=int, nargs="+", default=[2, 4, 8])
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()

    import soundfile as sf
    from lhotse import Fbank, FbankConfig

    motor = Motor.carregar()
    fb = Fbank(FbankConfig(num_mel_bins=80))
    x, sr = sf.read("data/eval/fleurs/fleurs_one_16k.wav", dtype="float32")
    feats = np.asarray(fb.extract(x, sr), dtype=np.float32)
    dur = len(x) / sr
    ent = {"x": feats[None], "x_lens": np.array([feats.shape[0]], dtype=np.int64)}

    t0 = time.perf_counter()
    lp, _ = motor.sessao.run(["log_probs", "log_probs_len"], ent)
    ms_encoder = (time.perf_counter() - t0) * 1000
    quadro = lp[0]

    print(f"  áudio {dur:.1f}s · {quadro.shape[0]} frames · vocab {quadro.shape[1]}")
    print(f"  encoder: {ms_encoder:.0f} ms\n")
    print(f"  {'decode':<14} {'ms':>9} {'ms total':>10} {'RTFx':>8}  cabe (≥6×)")
    print("  " + "-" * 56)

    ts = [time.perf_counter()]
    for _ in range(a.reps):
        ctc.greedy_text(quadro, motor.id2tok)
    ms_greedy = (time.perf_counter() - ts[0]) * 1000 / a.reps
    total = ms_encoder + ms_greedy
    print(f"  {'greedy':<14} {ms_greedy:9.2f} {total:10.1f} {dur / (total / 1000):8.2f}×  ✅")

    for largura in a.larguras:
        t = time.perf_counter()
        for _ in range(a.reps):
            beam_prefixo(quadro, largura)
        ms = (time.perf_counter() - t) * 1000 / a.reps
        total = ms_encoder + ms
        rtfx = dur / (total / 1000)
        print(f"  {'beam ' + str(largura):<14} {ms:9.2f} {total:10.1f} {rtfx:8.2f}×  "
              f"{'✅' if rtfx >= 6 else '❌'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
