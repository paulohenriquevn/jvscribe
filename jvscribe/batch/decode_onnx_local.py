#!/usr/bin/env python3
"""Decode ONNX int8 sobre um manifest lhotse, medindo WER, CER e RTFx na CPU-alvo.

Este é o ambiente do produto (CPU do atendente), não a GPU de treino.

Uso:
    python3 jvscribe/batch/decode_onnx_local.py --test testdata/coraa/cv-pt_cuts_test.jsonl.gz
    python3 jvscribe/batch/decode_onnx_local.py --test <manifest> --limit 500 --threads 4

O modelo e o vocabulário saem do artefato canônico (`model_card.json`) quando não são passados
— codificar o nome do peso já entregou o modelo errado duas vezes neste projeto.

O WER usa a régua **canônica** do repositório. A versão anterior chamava `jiwer.wer` sobre
texto cru, o que era uma terceira régua: sem régua única, nenhum WER daqui é comparável com o
de outro script.
"""
from __future__ import annotations

import argparse
import gc
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

import ctc  # noqa: E402  — shared kernel: colapso CTC e detokenização
from artifact import default_model_path, default_sibling  # noqa: E402
from artifact import validar_par_modelo_vocabulario  # noqa: E402
from onnx_session import criar_sessao  # noqa: E402
from text import normalize_for_wer_compare  # noqa: E402


def carregar_tokens(path: str) -> dict[int, str]:
    """`{id: token}` do `tokens.txt`."""
    id2tok = {}
    with open(path, encoding="utf-8") as f:
        for linha in f:
            partes = linha.split()
            if len(partes) == 2:
                id2tok[int(partes[1])] = partes[0]
    return id2tok


def decodificar_lote(log_probs, lens, id2tok: dict[int, str]) -> list[str]:
    """Texto por linha do lote, delegando o colapso CTC ao shared kernel.

    Antes havia `greedy_ctc` + `ids_to_text` locais. O resultado era idêntico ao do kernel —
    verificado — mas duplicado: o kernel existe porque este mesmo colapso já apareceu 7× no
    repositório, com semânticas que divergiram.
    """
    return [ctc.greedy_text(log_probs[i], id2tok, int(lens[i])) for i in range(len(lens))]


def medir_wer_cer(refs: list[str], hyps: list[str]) -> tuple[float | None, float | None]:
    """WER e CER na régua canônica. `(None, None)` quando não há referência útil.

    Manifest sem ground-truth é o modo qualitativo do script, não um erro — e dividir por
    zero aqui derrubaria a medição depois de já ter rodado a inferência inteira.
    """
    import jiwer

    pares = [(normalize_for_wer_compare(r), normalize_for_wer_compare(h))
             for r, h in zip(refs, hyps) if r.strip()]
    if not pares:
        return None, None
    R, H = [p[0] for p in pares], [p[1] for p in pares]
    return jiwer.wer(R, H), jiwer.cer(R, H)


def main() -> int:
    from lhotse import CutSet

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=None, help="default: artefato canônico (model_card.json)")
    ap.add_argument("--tokens", default=None)
    ap.add_argument("--test", required=True, help="manifest lhotse (.jsonl.gz)")
    ap.add_argument("--limit", type=int, default=0, help="0 = todos")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()

    modelo = a.model or default_model_path()
    tokens = a.tokens or default_sibling("tokens.txt")
    # Fail-fast do par (modelo, vocabulário): trocar o tokens.txt produz português PLAUSÍVEL
    # e errado, sem erro nenhum (CLAUDE.md § O modelo, fato 3). Validar aqui é o que separa
    # "transcrição ruim inexplicável" de um erro que diz o que aconteceu.
    validar_par_modelo_vocabulario(pathlib.Path(modelo).parent, tokens_path=tokens)

    # `memoria_restrita`: a arena do ONNX cresce sem devolver, e manifests grandes estouravam
    # a memória. É o único lugar do projeto que abre mão dos ~6,7% que a arena ligada rende.
    sess = criar_sessao(modelo, a.threads, memoria_restrita=True)
    id2tok = carregar_tokens(tokens)

    cortes = list(CutSet.from_file(a.test))
    if a.limit:
        cortes = cortes[: a.limit]
    cortes.sort(key=lambda c: c.duration)   # batches uniformes → menos padding e menos pico
    print(f"[onnx] {len(cortes)} utts | modelo={modelo} | threads={a.threads} | arena=off",
          flush=True)

    refs, hyps, audio_s = [], [], 0.0
    t0 = time.perf_counter()
    for i in range(0, len(cortes), a.batch):
        lote = cortes[i : i + a.batch]
        feats = [c.load_features() for c in lote]
        lens = np.array([f.shape[0] for f in feats], dtype=np.int64)
        x = np.zeros((len(feats), int(lens.max()), 80), dtype=np.float32)
        for j, f in enumerate(feats):
            x[j, : f.shape[0]] = f
        log_probs, lp_len = sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": lens})
        for c, texto in zip(lote, decodificar_lote(log_probs, lp_len.astype(int), id2tok)):
            refs.append(c.supervisions[0].text)
            hyps.append(texto)
            audio_s += c.duration
        del feats, x, log_probs, lp_len
        if (i + a.batch) % 512 < a.batch:
            gc.collect()
            print(f"[onnx] {min(i + a.batch, len(cortes))}/{len(cortes)}", flush=True)

    elapsed = time.perf_counter() - t0
    wer, cer = medir_wer_cer(refs, hyps)

    print("=" * 56)
    print(f"[RESULT] utts={len(refs)}")
    if wer is None:
        print("[RESULT] modo QUALITATIVO (sem ground-truth) — hipóteses abaixo")
    else:
        print(f"[RESULT] WER = {100 * wer:.2f}%   CER = {100 * cer:.2f}%   "
              "(régua canônica, sem acento)")
    print(f"[RESULT] audio={audio_s / 3600:.2f}h  wall={elapsed:.1f}s  "
          f"RTFx = {audio_s / elapsed:.2f}×")
    print("=" * 56)

    if wer is None:
        for h in hyps:
            if h.strip():
                print(f"HYP: {h}")
    else:
        for r, h in list(zip(refs, hyps))[:3]:
            print(f"REF: {r[:90]}\nHYP: {h[:90]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
