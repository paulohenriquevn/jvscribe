"""Baseline pt-BR de M1 sobre FLEURS pt_br → cadeia telefônica 8 kHz (T4.1, completo).

Fecha os DoDs que ficaram parciais no primeiro baseline:
- **pt-BR** (não pt-PT): FLEURS pt_br (Google, CC-BY) é português BRASILEIRO, fala
  lida com transcrição HUMANA (NÃO pseudo-label; PRD § 7.3).
- **cadeia de augmentação ponta-a-ponta** (CV-2): FLEURS é 16 kHz limpo → aplica
  `telephone_augment.sh` (16k→8k + banda 300-3400 + G.711 a-law) para gerar o test
  set 8 kHz proxy — exatamente o desenho original do plano (Fase 4 depende da Fase 2).
- **3 modelos** (CV-1): whisper small + medium + large-v3 via faster-whisper.

Robustez: parquet direto do HF (evita `datasets`/`torchcodec`); ctranslate2
single-thread (`cpu_threads=1`, evita deadlock de futex).

Uso: python3 scripts/baseline_fleurs_ptbr.py [n_utterances] [modelos-csv]
Emite jvscribe/results/m1-baseline-report.md (multi-modelo).
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import pyarrow.parquet as pq  # noqa: E402
import soundfile as sf  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from run_baseline import measure_baseline, render_report  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUGMENT = os.path.join(REPO, "scripts", "telephone_augment.sh")


def _augment(src: str, out: str) -> None:
    r = subprocess.run(["bash", AUGMENT, src, out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"augmentação falhou: {r.stderr.strip()}")


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    models = (sys.argv[2].split(",") if len(sys.argv) > 2 else ["small", "medium", "large-v3"])

    from faster_whisper import WhisperModel

    print(f"baixando FLEURS pt_br test (parquet direto, {n} utterances)…", flush=True)
    pqt = hf_hub_download(
        "google/fleurs", "pt_br/test/0000.parquet",
        repo_type="dataset", revision="refs/convert/parquet",
    )
    rows = pq.read_table(pqt).to_pylist()

    # Materializa N utterances 16 kHz e aplica a cadeia telefônica 8 kHz (Fase 2).
    tmp = tempfile.mkdtemp(prefix="m1_fleurs_ptbr_")
    manifest: list[dict] = []
    for row in rows:
        if len(manifest) >= n:
            break
        ref = (row.get("transcription") or row.get("raw_transcription") or "").strip()
        if not ref:
            continue
        idx = len(manifest)
        data, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
        src = os.path.join(tmp, f"f{idx}_16k.wav")
        aug = os.path.join(tmp, f"f{idx}_8k.wav")
        sf.write(src, data, sr)
        _augment(src, aug)  # cadeia telefônica ponta-a-ponta (CV-2)
        manifest.append({"audio_path": aug, "reference": ref})
    print(f"test set 8 kHz proxy pronto: {len(manifest)} utterances (FLEURS pt_br → a-law)", flush=True)

    seed, n_boot = 2026, 2000
    results = []
    for model_size in models:
        print(f"carregando faster-whisper '{model_size}' (CPU int8, 1 thread)…", flush=True)
        model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=1)
        hyp_by_path = {}
        for i, entry in enumerate(manifest):
            segs, _ = model.transcribe(entry["audio_path"], language="pt", beam_size=1)
            hyp_by_path[entry["audio_path"]] = " ".join(s.text for s in segs).strip()
        del model
        r = measure_baseline(
            manifest,
            transcribe_fn=lambda p: hyp_by_path[p],
            model_name=f"faster-whisper-{model_size} (int8, CPU)",
            seed=seed, n_boot=n_boot,
        )
        results.append(r)
        print(f"  {model_size}: WER {r.wer*100:.1f}% [IC95 {r.ci_low*100:.1f}-{r.ci_high*100:.1f}]", flush=True)

    report = render_report(
        results,
        corpus_note=(
            f"FLEURS pt_br (Google, CC-BY) — português BRASILEIRO, fala lida com "
            f"transcrição humana, {results[0].n} utterances. **16 kHz limpo degradado "
            f"para 8 kHz pela cadeia `telephone_augment.sh`** (resample + banda 300-3400 "
            f"+ G.711 a-law round-trip) — test set 8 kHz proxy, exercita a Fase 2 ponta-a-"
            f"ponta. Caveat (falácia § 3 #6): fala LIDA (não conversa de call center 1:1 "
            f"com crosstalk); o domínio real espontâneo depende de corpus consentido "
            f"(LGPD, fora de escopo)."
        ),
        provenance=(
            f"comando `python3 scripts/baseline_fleurs_ptbr.py {n} {','.join(models)}`; "
            f"faster-whisper int8 CPU cpu_threads=1 beam_size=1 language=pt; "
            f"dataset google/fleurs pt_br test (parquet); augmentação telephone_augment.sh; "
            f"bootstrap seed={seed}, n_boot={n_boot}; hardware = máquina de referência do "
            f"dev (NÃO o piso da frota BYOD, Q-01)."
        ),
    )
    out_path = os.path.join(REPO, "jvscribe", "results", "m1-baseline-report.md")
    with open(out_path, "w") as f:
        f.write(report + "\n")
    print("\n" + report)
    print(f"\nrelatório salvo em {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
