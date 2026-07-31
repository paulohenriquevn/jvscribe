#!/usr/bin/env python3
"""Mede WER do modelo M5 (ONNX) em áudio real de call center 8 kHz — DoD#3 REAL.

Genérico (áudio + transcrição por argumento) para ser versionável; o DADO (call
center) fica LOCAL por LGPD. Segmenta pela transcrição humana timestampada (blocos
de ~30s), normaliza ref/hyp, computa WER agregado via jiwer. Caveats honestos: 9 min
→ IC largo; 2 interlocutores no mesmo mono; granularidade de 30s; PII mascarada conta
como erro. Direciona, não conclui (asr-evidence-discipline § 3 #12).
"""
import argparse, pathlib, re, sys
import numpy as np
import soundfile as sf
from lhotse import Fbank, FbankConfig
import jiwer

# Régua única de WER (`common/text_normalize_ptbr`) — ver o docstring de `normalize()`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
from text import normalize_for_wer_compare  # noqa: E402
# `load_tokens` era uma das SEIS implementações do mesmo parser de `tokens.txt` no
# repositório. Todas equivalentes `[MEDIDO]` — mas só a do kernel recusa vocabulário
# vazio, e um vocabulário vazio decodifica para string vazia sem erro nenhum.
from engine import carregar_tokens as load_tokens  # noqa: E402,F401
from engine import Motor, argumentos_de_modelo  # noqa: E402

from audio import SR  # noqa: E402 — declaração única do domínio de áudio
TS_RE = re.compile(r'^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$')


def parse_transcript(path):
    blocks, cur_ts, cur = [], None, []
    def flush():
        if cur_ts is not None:
            blocks.append((cur_ts, " ".join(cur).strip()))
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if not s or s == "⚠️":
            continue
        m = TS_RE.match(s)
        if m:
            flush()
            a, b, c = m.groups()
            cur_ts = (int(a) * 60 + int(b)) if c is None else (int(a) * 3600 + int(b) * 60 + int(c))
            cur = []
        else:
            cur.append(s)
    flush()
    return blocks


def normalize(t):
    """Limpeza específica de transcrição de call center, DEPOIS a régua canônica de WER.

    ⚠️ Isto era uma régua PRÓPRIA e ela **preservava acento** — enquanto
    `normalize_for_wer_compare` (a régua de todo WER do projeto) **remove**. Ou seja: o WER de
    call center medido antes desta correção não é comparável com o de FLEURS, ainda que os
    dois estejam publicados lado a lado. É o mesmo modo de falha do `eval_public_hf.py`
    (16,14% vs 15,99%), documentado em `tests/test_regua_unica.py`.

    O que é legítimo aqui e a canônica não faz: máscaras de PII (`___`) e o marcador `⚠️` do
    anotador. Isso é PRÉ-processamento de domínio — vem antes, e a régua canônica fecha.
    """
    t = t.replace("⚠️", " ")
    t = re.sub(r"_+", " ", t)                          # máscaras de PII
    return normalize_for_wer_compare(t)


def greedy(lp, id2tok):
    """Delega ao shared kernel (M9/T3.1) — equivalência medida antes da migração."""
    import pathlib
    import sys

    # Mesmo motivo do insert em batch_transcribe: este script tem de rodar standalone, e o
    # `conftest.py` só expõe `common/` para os testes.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
    import ctc

    return ctc.greedy_text(lp[0], id2tok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--transcript", required=True)
    argumentos_de_modelo(ap, threads=False)
    a = ap.parse_args()

    # Sessão pela fábrica medida do kernel (arena LIGADA — a desligada custava −6,7%
    # [IC95% −18,3; −3,9] ms) e par (modelo, vocabulário) validado antes de transcrever.
    motor = Motor.carregar(a.model, a.tokens)
    sess, id2tok = motor.sessao, motor.id2tok
    fb = Fbank(FbankConfig(num_mel_bins=80))
    audio, sr = sf.read(a.wav)
    assert sr == SR, sr
    if audio.ndim > 1:
        audio = audio[:, 0]

    blocks = parse_transcript(a.transcript)
    refs, hyps = [], []
    for i, (start, ref) in enumerate(blocks):
        end = blocks[i + 1][0] if i + 1 < len(blocks) else len(audio) / SR
        seg = audio[int(start * SR):int(end * SR)].astype(np.float32)
        if len(seg) < SR // 2:
            continue
        feats = fb.extract(seg, SR)
        x = feats[None].astype(np.float32)
        xl = np.array([feats.shape[0]], dtype=np.int64)
        lp, _ = sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
        rn, hn = normalize(ref), normalize(greedy(lp, id2tok))
        if not rn:
            continue
        refs.append(rn); hyps.append(hn)
        print(f"[{i:02d}] {start:>4}s ref={rn[:75]!r}")
        print(f"          hyp={hn[:75]!r}")

    wer = jiwer.wer(refs, hyps)
    nwords = len(" ".join(refs).split())
    print(f"\n=== WER real call center 8 kHz = {wer*100:.2f}%  "
          f"({len(refs)} segmentos, {nwords} palavras de referência) ===")
    print("CAVEAT: 9 min → IC largo; 2 interlocutores no mono; granularidade 30s. Direciona, não conclui.")


if __name__ == "__main__":
    main()
