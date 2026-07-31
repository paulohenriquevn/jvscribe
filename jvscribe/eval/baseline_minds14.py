"""Baseline real de M1 sobre minds14 pt-PT (fala telefônica 8 kHz real) — T4.1.

minds14 (PolyAI, CC-BY-4.0) é **fala telefônica bancária real 8 kHz** com
transcrição HUMANA (NÃO pseudo-label; PRD § 7.3 respeitado). É um domínio
**próximo** do produto — telefonia bancária 8 kHz — com dois gaps explícitos
(review EVID-04): (a) é **pt-PT** europeu, não pt-BR; (b) são consultas de locutor
único, não call center 1:1 com crosstalk/AGC. Caveat honesto (blueprint ADR D2,
falácia § 3 #6). O test set pt-BR definitivo depende de corpus consentido (fora de
escopo LGPD).

Robustez: baixa o parquet auto-convertido do HF direto (evita o `datasets` 5.0,
que exige `torchcodec`) e roda faster-whisper single-thread (`cpu_threads=1`,
evita um deadlock de futex do threading default). Aplica a cadeia de augmentação
telefônica (a-law round-trip) sobre o áudio já-8 kHz, exercitando a régua inteira.

Uso: python3 scripts/baseline_minds14.py [n_utterances] [modelo]

Emite wiki/medicoes/m1-baseline-report.md.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import pyarrow.parquet as pq  # noqa: E402
import soundfile as sf  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
# `text` vive em `jvscribe/common`. Sob pytest o `conftest.py` cobre; standalone — o modo de
# uso deste script — quebrava em ModuleNotFoundError sem que nada na suíte falhasse.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common"))
from run_baseline import measure_baseline, render_report  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    model_size = sys.argv[2] if len(sys.argv) > 2 else "base"

    from faster_whisper import WhisperModel

    print("baixando minds14 pt-PT (parquet direto)…", flush=True)
    pqt = hf_hub_download(
        "PolyAI/minds14",
        "pt-PT/train/0000.parquet",
        repo_type="dataset",
        revision="refs/convert/parquet",
    )
    rows = pq.read_table(pqt).to_pylist()

    print(f"carregando faster-whisper '{model_size}' (CPU, int8, 1 thread)…", flush=True)
    model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=1)

    tmp = tempfile.mkdtemp(prefix="m1_minds14_")
    manifest: list[dict] = []
    hyp_by_path: dict[str, str] = {}
    for row in rows:
        if len(manifest) >= n:
            break
        ref = (row.get("transcription") or "").strip()
        if not ref:
            continue
        idx = len(manifest)
        data, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
        # minds14 JÁ é 8 kHz telefônico nativo — mede-se no canal real, sem
        # augmentação sintética por cima (que seria dupla degradação e inflaria o
        # WER). A cadeia de augmentação é validada à parte por T2.1 (tons 16 kHz).
        src = os.path.join(tmp, f"m{idx}_8k.wav")
        sf.write(src, data, sr)
        segments, _ = model.transcribe(src, language="pt", beam_size=1)
        hyp = " ".join(s.text for s in segments).strip()
        manifest.append({"audio_path": src, "reference": ref})
        hyp_by_path[src] = hyp
        print(f"  [{idx + 1}/{n}] ref='{ref[:45]}…' hyp='{hyp[:45]}…'", flush=True)

    if not manifest:
        print("ERRO: nenhuma utterance obtida do minds14", file=sys.stderr)
        return 1

    seed, n_boot = 2026, 2000
    result = measure_baseline(
        manifest,
        transcribe_fn=lambda p: hyp_by_path[p],
        model_name=f"faster-whisper-{model_size} (int8, CPU)",
        seed=seed,
        n_boot=n_boot,
    )
    report = render_report(
        [result],
        corpus_note=(
            f"minds14 pt-PT (PolyAI, CC-BY-4.0) — fala telefônica bancária REAL 8 kHz "
            f"nativa, {result.n} utterances, transcrição humana. Medido no canal nativo "
            f"(sem augmentação sintética — a cadeia a-law é validada à parte por T2.1). "
            f"Caveats honestos (falácia § 3 #6): (a) pt-PT europeu, NÃO pt-BR — o test "
            f"set pt-BR definitivo depende de corpus consentido (LGPD, fora de escopo); "
            f"(b) minds14 tem code-switching (algumas refs em inglês), o que infla o WER "
            f"de um modelo transcrevendo com language=pt; (c) faster-whisper-base é fraco "
            f"— é piso, não teto (large-v3 faria muito melhor)."
        ),
        provenance=(
            f"comando `python3 scripts/baseline_minds14.py {n} {model_size}`; "
            f"modelo faster-whisper-{model_size} int8 CPU cpu_threads=1 beam_size=1; "
            f"dataset PolyAI/minds14 pt-PT (parquet refs/convert/parquet); "
            f"bootstrap seed={seed}, n_boot={n_boot}; hardware = máquina de referência "
            f"do dev (NÃO o piso da frota BYOD, Q-01)."
        ),
    )
    # `jvscribe/results/` foi removida; e o destino da wiki é evidência publicada.
    out_path = os.environ.get(
        "JVSCRIBE_REPORT",
        os.path.join(REPO, "wiki", "medicoes", "m1-baseline-minds14.md"),
    )
    _FORCE = os.environ.get("JVSCRIBE_REPORT_FORCE") == "1"
    if os.path.exists(out_path) and not _FORCE:
        print(f"\n⚠️  {out_path} já existe (evidência publicada). "
              f"Defina JVSCRIBE_REPORT_FORCE=1 ou JVSCRIBE_REPORT=<outro>.")
        print("\n" + report)
        return 1
    with open(out_path, "w") as f:
        f.write(report + "\n")
    print("\n" + report)
    print(f"\nrelatório salvo em {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
