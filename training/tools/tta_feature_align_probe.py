#!/usr/bin/env python3
"""Probe do DISC-05: TTA forward-only por alinhamento de features (telefone→wideband).

Hipótese: sob channel shift telefônico (8 kHz + banda 300-3400 + G.711), uma transformação
afim GLOBAL por mel-bin que mapeia as estatísticas do domínio telefônico de volta às do
domínio wideband (que o modelo viu no treino) reduz o WER — forward-only, sem backprop,
sem tocar o grafo int8.

Mede 3 condições no MESMO test (FLEURS), no modelo int8 local, decode greedy CTC:
  1. wideband limpo         (teto — o que o modelo já faz bem)
  2. telefone CRU           (o gap de domínio)
  3. telefone ALINHADO      (o tratamento — alinhamento global de stats)

O alinhamento é GLOBAL (um transform por domínio, estimado do stream), NÃO per-utterance —
sem vazamento de oráculo. Reusa normalize_ptbr, word_edit_distance, paired_bootstrap e
apply_telephone_channel (Regra 9). CPU-only, sem GPU.

Uso: python3 training/tools/tta_feature_align_probe.py [--n 150] [--model <int8.onnx>]
"""
import argparse
import io
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pyarrow.parquet as pq
import soundfile as sf
from lhotse import Fbank, FbankConfig
from scipy.signal import resample_poly

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "training" / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "corpus"))
from eval_runtime_wer import normalize_ptbr, find_test_parquet  # noqa: E402
from wer_core import word_edit_distance  # noqa: E402
from bootstrap_wer_ci import paired_bootstrap  # noqa: E402
from telephone_channel import apply_telephone_channel  # noqa: E402

BLANK = 0
_FBANK = Fbank(FbankConfig(num_mel_bins=80))  # MESMO extrator do treino (prep_mls/prep_icefall)


def fbank16k(samples: np.ndarray) -> np.ndarray:
    """log-mel 80-bin (T,80) de áudio float 16 kHz — o extrator de treino."""
    import torch
    feats = _FBANK.extract(torch.from_numpy(samples.astype(np.float32)), sampling_rate=16000)
    return np.asarray(feats, dtype=np.float32)


def load_id2tok(path: Path) -> dict[int, str]:
    d = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            d[int(parts[1])] = parts[0]
    return d


def greedy(logp: np.ndarray, id2tok: dict[int, str]) -> str:
    ids = logp.argmax(axis=-1)
    out, prev = [], -1
    for i in ids:
        if i != BLANK and i != prev:
            out.append(int(i))
        prev = i
    return "".join(id2tok.get(i, "") for i in out).replace("▁", " ").strip()


def decode(sess: ort.InferenceSession, in_names, fbank: np.ndarray, id2tok) -> str:
    x = fbank[None].astype(np.float32)
    x_lens = np.array([fbank.shape[0]], dtype=np.int64)
    out = sess.run(None, {in_names[0]: x, in_names[1]: x_lens})
    return greedy(out[0][0], id2tok)


def wer(refs: list[list[str]], hyps: list[list[str]]) -> float:
    e = sum(word_edit_distance(r, h) for r, h in zip(refs, hyps))
    w = sum(len(r) for r in refs) or 1
    return 100.0 * e / w


def build_dataset(n: int) -> tuple[list[list[str]], list[np.ndarray], list[np.ndarray]]:
    """Extrai (refs, fbanks_wideband, fbanks_telefone) de N utterances do FLEURS test.

    Reutilizável entre probes (DISC-05 alinhamento, DISC-06 blank-penalty). Telefone =
    round-trip de deploy: 16k → 8k (banda 300-3400 + G.711) → 16k → mesmo fbank do treino.
    """
    refs, wb, tel = [], [], []
    pf = pq.ParquetFile(find_test_parquet())
    done = 0
    for batch in pf.iter_batches(batch_size=64, columns=["audio", "transcription"]):
        for row in batch.to_pylist():
            if done >= n:
                break
            data, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
            if data.ndim > 1:
                data = data[:, 0]
            if sr != 16000:
                g = np.gcd(sr, 16000)
                data = resample_poly(data, 16000 // g, sr // g)
            t8, _ = apply_telephone_channel(data.astype(np.float32), 16000)
            t16 = resample_poly(t8, 2, 1).astype(np.float32)
            refs.append(normalize_ptbr(row["transcription"]).split())
            wb.append(fbank16k(data))
            tel.append(fbank16k(t16))
            done += 1
        if done >= n:
            break
    return refs, wb, tel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--model", default=str(REPO / "training/results/onnx/model.int8.onnx"))
    ap.add_argument("--tokens", default=str(REPO / "training/results/onnx/tokens.txt"))
    args = ap.parse_args()
    id2tok = load_id2tok(Path(args.tokens))
    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    in_names = [i.name for i in sess.get_inputs()]
    refs, wb, tel = build_dataset(args.n)

    def stats(fbanks):
        allf = np.concatenate(fbanks, axis=0)
        return allf.mean(0), allf.std(0) + 1e-8

    mu_src, sd_src = stats(wb)
    mu_tel, sd_tel = stats(tel)

    # Passo 2: decode nas 3 condições
    h_wb = [decode(sess, in_names, f, id2tok).split() for f in wb]
    h_tel = [decode(sess, in_names, f, id2tok).split() for f in tel]
    h_al = [decode(sess, in_names, (f - mu_tel) / sd_tel * sd_src + mu_src, id2tok).split() for f in tel]

    print(f"[MEDIDO] probe DISC-05 — TTA forward-only por alinhamento de features (n={done})")
    print(f"  1. wideband limpo   WER = {wer(refs, h_wb):6.2f}%  (teto)")
    print(f"  2. telefone CRU     WER = {wer(refs, h_tel):6.2f}%  (gap de domínio)")
    print(f"  3. telefone ALINHADO WER = {wer(refs, h_al):6.2f}%  (tratamento)")

    rows = [(word_edit_distance(r, hc), word_edit_distance(r, ha), len(r))
            for r, hc, ha in zip(refs, h_tel, h_al)]
    b = paired_bootstrap(rows, n_boot=10000, seed=42)
    print(f"\n  cru→alinhado: Δ {b['abs_diff_pp']:.2f} p.p.  IC95% [{b['abs_ci95'][0]:.2f}, {b['abs_ci95'][1]:.2f}]"
          f"  (rel {b['rel_impr_pct']:.2f}%, P(melhora>0)={b['p_gt0_pct']:.1f}%)")
    verdict = "ALINHAMENTO AJUDA" if b["abs_diff_pp"] > 0 and b["abs_ci95"][0] > 0 else \
              "inconclusivo/nulo (IC inclui 0)" if b["abs_diff_pp"] > 0 else "ALINHAMENTO PIORA"
    print(f"  veredito: {verdict}")


if __name__ == "__main__":
    main()
