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

Uso: python3 jvscribe/eval/baseline_fleurs_ptbr.py --n 12 --models small medium large-v3
Emite `wiki/medicoes/m1-baseline.md` — e RECUSA sobrescrevê-lo (é evidência publicada).
`JVSCRIBE_REPORT` redireciona; `JVSCRIBE_REPORT_FORCE=1` autoriza a substituição.
"""

from __future__ import annotations

import argparse
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
# `common/` também: `run_baseline` → `eval_wer` → `text`. Sob pytest o
# `jvscribe/conftest.py` cobria e a suíte ficava verde; standalone — o modo de uso deste
# script — quebrava em ModuleNotFoundError.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common"))
from metrics import escrever_relatorio  # noqa: E402
from run_baseline import measure_baseline, render_report  # noqa: E402

# `dirname(dirname(__file__))` de `jvscribe/eval/…` é `jvscribe/`, não a raiz do repositório —
# o nome `REPO` era enganoso e o caminho montado (`jvscribe/scripts/`) não existe desde a
# reorganização. Resultado: este módulo, que produziu o baseline de M1, quebrava ao augmentar.
PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUGMENT = os.path.join(PKG, "common", "audio", "augment.sh")


def _augment(src: str, out: str) -> None:
    if not os.path.isfile(AUGMENT):
        # Falha ANTES do subprocess: `bash` num caminho inexistente devolve 127 com uma
        # mensagem que não diz o que configurar (error-handling.md § 2).
        raise FileNotFoundError(f"cadeia de augmentação ausente: {AUGMENT}")
    r = subprocess.run(["bash", AUGMENT, src, out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"augmentação falhou: {r.stderr.strip()}")


def main() -> int:
    # Era posicional (`sys.argv[1]`, `sys.argv[2]`) e sem `--help`: pedir ajuda dava
    # `ValueError: invalid literal for int() with base 10: '--help'`, de onde ninguém deduz a
    # interface. Terceira ocorrência do mesmo defeito no repositório — guardado por
    # `tests/test_entrypoints_argparse.py`.
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=12, help="utterances do FLEURS pt_br test")
    ap.add_argument("--models", nargs="+", default=["small", "medium", "large-v3"],
                    help="tamanhos do faster-whisper a medir")
    args = ap.parse_args()
    n, models = args.n, args.models

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
        for entry in manifest:
            segs, _ = model.transcribe(entry["audio_path"], language="pt", beam_size=1)
            hyp_by_path[entry["audio_path"]] = " ".join(s.text for s in segs).strip()
        del model
        r = measure_baseline(
            manifest,
            # `hyp_by_path` ligado como default: sem isso o lambda fecha sobre a
            # variável do laço externo e passa a depender de o uso ser síncrono.
            transcribe_fn=lambda p, _m=hyp_by_path: _m[p],
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
            f"comando `python3 jvscribe/eval/baseline_fleurs_ptbr.py --n {n} --models {' '.join(models)}`; "
            f"faster-whisper int8 CPU cpu_threads=1 beam_size=1 language=pt; "
            f"dataset google/fleurs pt_br test (parquet); augmentação telephone_augment.sh; "
            f"bootstrap seed={seed}, n_boot={n_boot}; hardware = máquina de referência do "
            f"dev (NÃO o piso da frota BYOD, Q-01)."
        ),
    )
    # `REPO` não existe (a constante virou `PKG` ao corrigir o caminho da augmentação) e
    # `jvscribe/results/` foi removida — este `os.path.join` era NameError garantido, depois
    # de transcrever N utterances com três modelos. O destino agora é onde as medições vivem.
    # `escrever_relatorio` RECUSA sobrescrever: este script já apagou o baseline real de M1
    # (12 utterances, 3 modelos) numa corrida de teste com n=2. Ver common/metrics.py.
    out_path = os.environ.get(
        "JVSCRIBE_REPORT",
        os.path.join(os.path.dirname(PKG), "wiki", "medicoes", "m1-baseline.md"),
    )
    force = os.environ.get("JVSCRIBE_REPORT_FORCE") == "1"
    print("\n" + report)
    try:
        escrever_relatorio(out_path, report, force=force)
        print(f"\nrelatório salvo em {out_path}")
    except FileExistsError as e:
        print(f"\n⚠️  relatório NÃO gravado: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
