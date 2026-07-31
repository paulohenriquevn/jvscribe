#!/usr/bin/env python3
"""Eval de ACURÁCIA do runtime Rust — WER através do caminho de produção.

⚠️ **O `main()` deste módulo não roda mais neste repositório.** O runtime Rust foi removido
em 2026-07-30 (`feat!: remove o runtime Rust; jvscribe passa a ser Python-only`) e existe só
no histórico do git. O script fica porque é a **proveniência** do WER de runtime publicado
(29,92%, n=470) e porque seus helpers continuam em uso: `normalize_ptbr` e
`find_test_parquet` são importados por `tools/tta_feature_align_probe.py` e pelos testes.

O que ele fazia: extrai N utterances do FLEURS pt_br test (cache local HF), roda CADA UMA
pelo runtime (wav → kaldi_fbank → transcribe) e computa o WER real contra a referência
normalizada com a MESMA régua do treino. Compara com o decode Python do icefall (29,97% no
FLEURS test completo) — a equivalência que importa: o runtime degrada a acurácia?

Uso (histórico):
    python3 jvscribe/tools/eval_runtime_wer.py --n 50
"""
from __future__ import annotations

import argparse
import io
import pathlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "target" / "release" / "macaw-cli"   # binário do runtime removido — ver docstring

from wer_core import word_edit_distance  # Levenshtein puro, reusado (Regra 9 / DRY)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
from artifact import default_model_path  # noqa: E402  — resolvedor canônico de artefato
# Este módulo MEDE WER → régua de COMPARAÇÃO (remove acento). Não confundir com
# `finetune/prep_icefall.py`, que prepara o CORPUS DE TREINO e por isso usa
# `normalize_train_target` (preserva acento — o modelo precisa aprender a acentuar).
#
# ⚠️ Aqui rodava a régua de treino. Numa frase em que só o acento difere isso dá WER 62,5%
# onde a régua canônica dá 0% `[MEDIDO]` — o WER de runtime publicado (29,92%) saiu daí e
# NÃO é comparável com os números medidos pela canônica.
from text import normalize_for_wer_compare as normalize_ptbr  # noqa: E402


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
        # Falha CLARA: mandar rodar `cargo build` seria mandar rodar um comando impossível —
        # não há mais crate neste repositório (error-handling.md § 2, "fail clear").
        raise SystemExit(
            f"runtime Rust ausente ({CLI}). Ele foi REMOVIDO deste repositório em 2026-07-30 "
            f"(commit 266253f, 'jvscribe passa a ser Python-only') e não pode ser reconstruído "
            f"aqui — `cargo build` não tem o que compilar. Para reproduzir a medição, faça "
            f"checkout do commit anterior à remoção. Para medir WER hoje, use "
            f"`jvscribe/batch/eval_public_hf.py` (decode Python, mesma régua)."
        )
    modelo = pathlib.Path(default_model_path())
    if not modelo.exists():
        raise SystemExit(f"modelo ausente: {modelo} (defina JVSCRIBE_MODEL_DIR)")

    pf = pq.ParquetFile(find_test_parquet())
    # Era `jvscribe/results/onnx/_eval_wavs` — pasta removida junto com `results/`.
    tmp = REPO / "data" / "eval" / "_eval_wavs"
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
    print("[REF]    Decode Python (icefall) WER = 29,97% (FLEURS test completo, 21.471 palavras)")
    print(f"[NOTA]   n={done} é subconjunto → IC mais largo que o número Python. "
          f"O que importa: o runtime Rust NÃO deve degradar vs o decode de treino.")


if __name__ == "__main__":
    main()
