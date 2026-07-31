#!/usr/bin/env python3
"""Probe da hipótese central do DISC-06: adaptar o DECODER ajuda onde a feature falhou?

Sob channel shift telefônico o CTC sobre-emite blank (deleções). Um blank penalty β
(subtrai β do logit de blank antes do argmax) é a alavanca de decoder-space forward-only:
recupera deleções, muda o argmax do greedy, custo O(1), não toca pesos nem features.

Varre β no test wideband E telefone e mede WER. Se o melhor β no telefone bater o β=0
(cru) SEM piorar o wideband, a hipótese do DISC-06 (adaptar o decoder > adaptar a feature)
ganha um primeiro número — em contraste com o −24,6pp do alinhamento de features (DISC-05).

Reusa `build_dataset` + helpers do DISC-05 (Regra 9). CPU-only, sem GPU.
Uso: python3 jvscribe/probes/blank_penalty_probe.py [--n 150]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort

REPO = Path(__file__).resolve().parent.parent.parent
# Standalone: o `jvscribe/conftest.py` só roda sob pytest. Apontava para `jvscribe/scripts`,
# pasta que deixou de existir — o probe quebrava em ModuleNotFoundError ao ser executado.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "probes"))
from tta_feature_align_probe import BLANK, build_dataset, load_id2tok, wer  # noqa: E402
from metrics import paired_bootstrap, word_edit_distance  # noqa: E402


def greedy_penalized(logp: np.ndarray, id2tok: dict[int, str], beta: float) -> str:
    """Greedy CTC com penalidade β no logit de blank (β=0 → greedy padrão).

    ⚠️ Reimplementa o colapso de propósito, e não usa o shared kernel (`common/ctc.py`): a
    penalidade é aplicada ao logit de blank **antes** do argmax, o que muda o caminho
    escolhido. Delegar ao kernel mediria o greedy padrão — ou seja, nada do que esta sonda
    existe para investigar.
    """
    lp = logp.copy()
    lp[:, BLANK] -= beta
    ids = lp.argmax(axis=-1)
    out, prev = [], -1
    for i in ids:
        if i != BLANK and i != prev:
            out.append(int(i))
        prev = i
    return "".join(id2tok.get(i, "") for i in out).replace("▁", " ").strip()


def decode_all(sess, in_names, fbanks, id2tok, beta):
    hyps = []
    for f in fbanks:
        x = f[None].astype(np.float32)
        xl = np.array([f.shape[0]], dtype=np.int64)
        logp = sess.run(None, {in_names[0]: x, in_names[1]: xl})[0][0]
        hyps.append(greedy_penalized(logp, id2tok, beta).split())
    return hyps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--model", default=str(REPO / "models/m4-legacy-onnx/model.int8.onnx"))
    ap.add_argument("--tokens", default=str(REPO / "models/m4-legacy-onnx/tokens.txt"))
    args = ap.parse_args()
    id2tok = load_id2tok(Path(args.tokens))
    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    in_names = [i.name for i in sess.get_inputs()]
    refs, wb, tel = build_dataset(args.n)

    betas = [0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0]
    print(f"[MEDIDO] probe DISC-06 — blank penalty (decoder-space), n={args.n}")
    print(f"  {'β':>4} | {'WER wideband':>12} | {'WER telefone':>12}")
    tel_by_beta = {}
    best = (None, 1e9)
    for b in betas:
        w_wb = wer(refs, decode_all(sess, in_names, wb, id2tok, b))
        h_tel = decode_all(sess, in_names, tel, id2tok, b)
        w_tel = wer(refs, h_tel)
        tel_by_beta[b] = h_tel
        if w_tel < best[1]:
            best = (b, w_tel)
        print(f"  {b:>4} | {w_wb:>11.2f}% | {w_tel:>11.2f}%")

    b0, bb = tel_by_beta[0.0], tel_by_beta[best[0]]
    rows = [(word_edit_distance(r, h0), word_edit_distance(r, hb), len(r))
            for r, h0, hb in zip(refs, b0, bb)]
    res = paired_bootstrap(rows, n_boot=10000, seed=42)
    print(f"\n  melhor β no telefone = {best[0]} (WER {best[1]:.2f}%) vs β=0 cru")
    print(f"  ganho: Δ {res['abs_diff_pp']:.2f} p.p.  IC95% [{res['abs_ci95'][0]:.2f}, {res['abs_ci95'][1]:.2f}]"
          f"  (rel {res['rel_impr_pct']:.2f}%, P(melhora>0)={res['p_gt0_pct']:.1f}%)")
    v = "DECODER-SPACE AJUDA" if res["abs_diff_pp"] > 0 and res["abs_ci95"][0] > 0 else \
        "nulo/inconclusivo (IC inclui 0)" if res["abs_diff_pp"] >= 0 else "PIORA"
    print(f"  veredito: {v}  (contraste: alinhamento de features do DISC-05 = −24,6pp)")


if __name__ == "__main__":
    main()
