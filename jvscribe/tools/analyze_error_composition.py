#!/usr/bin/env python3
"""Composição do erro do ASR: quanto é ATACÁVEL por "corrigir palavra fora do léxico"?

Testa empiricamente a ideia (Paulo, 2026-07-26): "se a palavra existe em PT-BR não
mexe; se não existe, corrige". Classifica cada erro de substituição do runtime contra
um dicionário PT-BR (hashmap = /usr/share/dict/brazilian ∪ hunspell), medindo:

  - non_word_hyp  : hyp ∉ dict E ref ∈ dict  → ATACÁVEL pelo léxico (o alvo do método)
  - real_word_hyp : hyp ∈ dict E ref ∈ dict  → INATACÁVEL (hyp passa no filtro; erro sobrevive)
  - rare_ref      : ref ∉ dict               → nome próprio/rare (alvo de BIASING, não de léxico)
  - false_flag    : palavra CORRETA porém ∉ dict → risco de CORROMPER (o método a "corrige" sem precisar)

Alinhamento por difflib (stdlib). Transcrição pelo runtime real (macaw-cli). `[MEDIDO]`.

Uso: ORT_DYLIB_PATH=.../libonnxruntime.so python3 jvscribe/tools/analyze_error_composition.py --n 100
"""
from __future__ import annotations

import argparse
import difflib
import io
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

REPO = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO / "jvscribe" / "results" / "onnx"
CLI = REPO / "target" / "release" / "macaw-cli"


def normalize_ptbr(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").lower().strip())
    text = re.sub(r"[^\w\sáàâãéêíóôõúçü]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def load_lexicon() -> set[str]:
    """O 'hashmap de todas as palavras PT-BR' — wordlists do sistema, normalizadas."""
    words: set[str] = set()
    for p in ["/usr/share/dict/brazilian", "/usr/share/dict/portuguese"]:
        fp = Path(p)
        if fp.exists():
            for enc in ("utf-8", "latin-1"):
                try:
                    for line in fp.read_text(encoding=enc).splitlines():
                        w = normalize_ptbr(line)
                        if w:
                            words.add(w)
                    break
                except UnicodeDecodeError:
                    continue
    return words


def find_test_parquet() -> Path:
    cands = list(Path.home().glob(
        ".cache/huggingface/hub/datasets--google--fleurs/snapshots/*/parquet-data/pt_br/test-*.parquet"))
    if not cands:
        raise SystemExit("parquet FLEURS pt_br não encontrado")
    return sorted(cands)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()

    lex = load_lexicon()
    if len(lex) < 10000:
        raise SystemExit(f"léxico suspeito ({len(lex)} palavras) — cheque /usr/share/dict")
    print(f"[léxico] {len(lex)} palavras PT-BR carregadas\n")

    pf = pq.ParquetFile(find_test_parquet())
    tmp = MODEL_DIR / "_eval_wavs"
    tmp.mkdir(parents=True, exist_ok=True)

    c = Counter()          # contadores de classes
    correct_total = 0
    correct_oov = 0        # palavras certas que NÃO estão no dict (falso-flag em potencial)
    subs = 0
    examples: dict[str, list] = {"non_word_hyp": [], "real_word_hyp": [], "false_flag": []}
    done = 0

    for batch in pf.iter_batches(batch_size=64, columns=["audio", "transcription"]):
        for row in batch.to_pylist():
            if done >= args.n:
                break
            a = row["audio"]
            data, sr = sf.read(io.BytesIO(a["bytes"]))
            if data.ndim > 1:
                data = data[:, 0]
            d16 = (np.clip(data, -1, 1) * 32767).astype("int16")
            wav = tmp / f"a{done:03d}.wav"
            sf.write(wav, d16, sr, subtype="PCM_16")

            ref = normalize_ptbr(row["transcription"]).split()
            try:
                out = subprocess.run([str(CLI), "transcribe", str(wav)],
                                     capture_output=True, text=True, timeout=120)
                hyp = normalize_ptbr(out.stdout).split()
            except subprocess.TimeoutExpired:
                done += 1
                continue

            sm = difflib.SequenceMatcher(a=ref, b=hyp, autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    for w in ref[i1:i2]:
                        correct_total += 1
                        if w not in lex:
                            correct_oov += 1
                            if len(examples["false_flag"]) < 8:
                                examples["false_flag"].append(w)
                elif tag == "replace":
                    # alinha par-a-par o bloco substituído (aprox: zip)
                    for rw, hw in zip(ref[i1:i2], hyp[j1:j2]):
                        subs += 1
                        r_in, h_in = rw in lex, hw in lex
                        if not r_in:
                            c["rare_ref"] += 1
                        elif not h_in:  # ref é palavra, hyp não → atacável
                            c["non_word_hyp"] += 1
                            if len(examples["non_word_hyp"]) < 8:
                                examples["non_word_hyp"].append(f"{rw}→{hw}")
                        else:           # ambos palavras → real-word, inatacável
                            c["real_word_hyp"] += 1
                            if len(examples["real_word_hyp"]) < 8:
                                examples["real_word_hyp"].append(f"{rw}→{hw}")
            done += 1
        if done >= args.n:
            break

    print(f"[MEDIDO] n={done} utterances | substituições={subs} | palavras corretas={correct_total}\n")
    print("=== Composição das SUBSTITUIÇÕES (o erro que uma correção poderia pegar) ===")
    for k in ("non_word_hyp", "real_word_hyp", "rare_ref"):
        pct = 100 * c[k] / max(subs, 1)
        print(f"  {k:14s}: {c[k]:4d}  ({pct:5.1f}%)")
    print(f"\n  → ATACÁVEL por léxico (non_word_hyp, ref é palavra real): "
          f"{100*c['non_word_hyp']/max(subs,1):.1f}% das substituições")
    print(f"  → INATACÁVEL (real_word_hyp, hyp passa no filtro): "
          f"{100*c['real_word_hyp']/max(subs,1):.1f}%")
    print(f"  → BIASING (rare_ref, nome próprio/OOV): "
          f"{100*c['rare_ref']/max(subs,1):.1f}%")
    print(f"\n=== RISCO de CORROMPER palavra correta (false-flag) ===")
    print(f"  palavras corretas fora do dict: {correct_oov}/{correct_total} "
          f"({100*correct_oov/max(correct_total,1):.2f}%) — o método 'corrigiria' estas SEM precisar")
    print(f"\nExemplos non_word_hyp (atacável): {examples['non_word_hyp']}")
    print(f"Exemplos real_word_hyp (inatacável): {examples['real_word_hyp']}")
    print(f"Exemplos false_flag (corretas ∉ dict): {examples['false_flag']}")


if __name__ == "__main__":
    main()
