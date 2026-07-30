#!/usr/bin/env python3
"""Eval de ACURÁCIA do runtime Rust — WER através do caminho de produção.

Responde "qual a qualidade do runtime?": extrai N utterances do FLEURS pt_br
test (cache local HF), roda CADA UMA pelo **runtime Rust** (`macaw-cli transcribe`,
i.e. wav -> macaw_audio::kaldi_fbank -> AsrEngine::transcribe), e computa o WER
real (edit-distance de palavras) contra a referência normalizada com a MESMA
`normalize_ptbr` do treino. Compara com o WER do decode Python do icefall
(29,97% no FLEURS test completo) — a equivalência que importa: o runtime Rust
degrada a acurácia vs o decode de treino?

Sem dependência nova: WER por Levenshtein de palavras (stdlib). `[MEDIDO]`.

Uso:
    python3 training/tools/eval_runtime_wer.py --n 50
"""
from __future__ import annotations

import argparse
import glob
import io
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

REPO = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO / "training" / "results" / "onnx"
CLI = REPO / "target" / "release" / "macaw-cli"


def normalize_ptbr(text: str) -> str:
    """Idêntica a training/prep_icefall.py:49 (a normalização dos alvos de treino)."""
    text = unicodedata.normalize("NFC", (text or "").lower().strip())
    text = re.sub(r"[^\w\sáàâãéêíóôõúçü]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


from wer_core import word_edit_distance  # Levenshtein puro, reusado (Regra 9 / DRY)


def find_test_parquet() -> Path:
    cands = list(
        Path.home().glob(
            ".cache/huggingface/hub/datasets--google--fleurs/snapshots/*/"
            "parquet-data/pt_br/test-*.parquet"
        )
    )
    if not cands:
        raise SystemExit("parquet de teste FLEURS pt_br não encontrado no cache HF local")
    return sorted(cands)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="nº de utterances (default 50)")
    args = ap.parse_args()

    if not CLI.exists():
        raise SystemExit(f"CLI ausente: {CLI} — rode `cargo build -p macaw-cli --release`")
    if not (MODEL_DIR / "model.int8.onnx").exists():
        raise SystemExit(f"modelo ausente em {MODEL_DIR}")

    pf = pq.ParquetFile(find_test_parquet())
    tmp = REPO / "training" / "results" / "onnx" / "_eval_wavs"
    tmp.mkdir(parents=True, exist_ok=True)

    tot_err, tot_words, done = 0, 0, 0
    tot_cerr, tot_chars = 0, 0  # CER: edit-distance por CARACTERE (informativo em PT-BR)
    print(f"[eval] runtime Rust (macaw-cli transcribe) sobre {args.n} utterances FLEURS test\n")
    for batch in pf.iter_batches(batch_size=64, columns=["audio", "transcription"]):
        rows = batch.to_pylist()
        for row in rows:
            if done >= args.n:
                break
            audio = row["audio"]
            # O parquet guarda o áudio como WAV FLOAT [-1,1]; ler com dtype="int16"
            # direto zera as amostras. Ler float e escalar explicitamente p/ int16.
            data, sr = sf.read(io.BytesIO(audio["bytes"]))
            if data.ndim > 1:
                data = data[:, 0]
            data16 = (np.clip(data, -1.0, 1.0) * 32767.0).astype("int16")
            wav = tmp / f"u{done:03d}.wav"
            sf.write(wav, data16, sr, subtype="PCM_16")

            ref = normalize_ptbr(row["transcription"]).split()
            # Robustez: um timeout transitório (contenção de CPU) NÃO pode derrubar o
            # eval inteiro. Conta a utterance como toda-deleção (hyp vazia) e segue.
            try:
                out = subprocess.run(
                    [str(CLI), "transcribe", str(wav)], capture_output=True, text=True, timeout=120
                )
                hyp = normalize_ptbr(out.stdout).split()
            except subprocess.TimeoutExpired:
                print(f"  [TIMEOUT] u{done:03d} — contado como falha, seguindo", file=sys.stderr)
                hyp = []
            err = word_edit_distance(ref, hyp)
            tot_err += err
            tot_words += len(ref)
            # CER: mesmo Levenshtein, mas sobre a sequência de caracteres (sem espaços).
            ref_c, hyp_c = list("".join(ref)), list("".join(hyp))
            tot_cerr += word_edit_distance(ref_c, hyp_c)
            tot_chars += len(ref_c)
            done += 1
            if done <= 5 or done % 10 == 0:
                print(f"  [{done:3d}] WER={100*tot_err/max(tot_words,1):5.2f}% "
                      f"CER={100*tot_cerr/max(tot_chars,1):5.2f}%  "
                      f"ref='{' '.join(ref[:8])}...' hyp='{' '.join(hyp[:8])}...'")
        if done >= args.n:
            break

    wer = 100.0 * tot_err / max(tot_words, 1)
    cer = 100.0 * tot_cerr / max(tot_chars, 1)
    print(f"\n[MEDIDO] Runtime Rust WER = {wer:.2f}%  ({tot_err}/{tot_words} palavras)")
    print(f"[MEDIDO] Runtime Rust CER = {cer:.2f}%  ({tot_cerr}/{tot_chars} caracteres), n={done} utterances")
    print(f"[REF]    Decode Python (icefall) WER = 29,97% (FLEURS test completo, 21.471 palavras)")
    print(f"[NOTA]   n={done} é subconjunto → IC mais largo que o número Python. "
          f"O que importa: o runtime Rust NÃO deve degradar vs o decode de treino.")


if __name__ == "__main__":
    main()
