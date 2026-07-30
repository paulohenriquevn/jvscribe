"""Orquestra o pipeline de corpus de M3 ponta-a-ponta sobre FLEURS pt_br real.

Fluxo (Integration Validation do plano m3-corpus):
  FLEURS pt_br (N clips) → 2 whisper sequenciais → CER par-a-par → τ calibrado →
  filtro por concordância (aplicado AO MANIFEST) → manifest Lhotse com telephone
  on-the-fly → evidência [MEDIDO].

Grava `knowledge-base/corpus/m3-cer-distribution.md`. Uso:
  python3 training/corpus/run_pipeline.py --n 20 --sizes small base
"""

from __future__ import annotations

import argparse
import datetime
import glob
import io
import os
import statistics
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/

from corpus.agreement_filter import agree, calibrate_tau, pairwise_cer  # noqa: E402
from corpus.build_manifest import build_cutset, filter_cutset, load_telephone_audio  # noqa: E402
from corpus.pseudo_label import transcribe_pair  # noqa: E402

REPORT = "knowledge-base/corpus/m3-cer-distribution.md"
_BOOTSTRAP_SEED = 20260725  # fixo → IC reprodutível


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "CPU desconhecida"


def load_fleurs_wavs(n: int, out_dir: str) -> dict[str, str]:
    """Escreve N clips de FLEURS pt_br (test) como WAV 16 kHz. Parquet direto (sem torchcodec)."""
    pattern = str(
        Path.home()
        / ".cache/huggingface/hub/datasets--google--fleurs/snapshots/*/pt_br/test/0000.parquet"
    )
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError("FLEURS pt_br parquet não encontrado no cache HF")
    col = pq.read_table(matches[0]).column("audio").to_pylist()
    paths: dict[str, str] = {}
    for i, a in enumerate(col):
        if len(paths) >= n:
            break
        raw = a.get("bytes")
        if not raw:
            continue
        arr, sr = sf.read(io.BytesIO(raw), dtype="float32")
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        if sr != 16000:
            import librosa

            arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
        cid = f"fleurs_{i:03d}"
        path = os.path.join(out_dir, f"{cid}.wav")
        sf.write(path, arr, 16000)
        paths[cid] = path
    return paths


def _bootstrap_tau_ci(cers: list[float], keep_fraction: float,
                      iters: int = 2000) -> tuple[float, float]:
    """IC95% de τ (percentil da distribuição) por bootstrap com reposição (seed fixa)."""
    rng = np.random.default_rng(_BOOTSTRAP_SEED)
    arr = np.asarray(cers, dtype=float)
    taus = [
        float(np.percentile(rng.choice(arr, size=len(arr), replace=True),
                            keep_fraction * 100.0, method="lower"))
        for _ in range(iters)
    ]
    return float(np.percentile(taus, 2.5)), float(np.percentile(taus, 97.5))


def write_report(cers: dict[str, float], tau: float, kept: set[str],
                 sizes: tuple[str, str], sr_proof: int, n_cuts: int,
                 keep_fraction: float, cmd: str) -> None:
    vals = list(cers.values())
    n = len(vals)
    mean = statistics.mean(vals)
    median = statistics.median(vals)
    std = statistics.stdev(vals) if n > 1 else 0.0  # amostral (ddof=1), review L-3
    sem = std / (n ** 0.5) if n > 0 else 0.0
    ci_lo, ci_hi = mean - 1.96 * sem, mean + 1.96 * sem
    tau_lo, tau_hi = _bootstrap_tau_ci(vals, keep_fraction)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    lines = [
        "# M3 — Distribuição de CER par-a-par (evidência [MEDIDO])",
        "",
        f"**Data:** {now} · **Hardware:** {_cpu_model()} (int8, CPU, cpu_threads=1)",
        f"**Comando exato:** `{cmd}` — **1 run, n={n} clips** de FLEURS pt_br (não repetições)",
        f"**Transcritores:** faster-whisper `{sizes[0]}` + `{sizes[1]}` (sequenciais — RAM-safe)",
        "**Métrica:** CER **direcional** de hyp₂ contra hyp₁ (modelo #1 como referência),",
        "ambas normalizadas PT-BR. Não é simétrica; ordena por magnitude de discordância.",
        "",
        "## Estatística da distribuição `[MEDIDO]`",
        "",
        f"- **spread** entre clips: média {mean:.3f} ± {std:.3f} (σ amostral) · mediana {median:.3f} · min {min(vals):.3f} · max {max(vals):.3f} (n={n})",
        f"- **incerteza** da média (≠ spread): SEM {sem:.3f} → IC95% ≈ [{ci_lo:.3f}, {ci_hi:.3f}]",
        f"- **τ calibrado** (percentil-{int(keep_fraction*100)} empírico): **{tau:.3f}** · IC95% bootstrap [{tau_lo:.3f}, {tau_hi:.3f}] (2000 reamostragens, seed fixa)",
        f"- **manifest filtrado**: {n_cuts} cuts mantidos == {len(kept)} aprovados pelo filtro (review B-1: o filtro É aplicado ao manifest)",
        f"- prova on-the-fly: `load_telephone_audio` do 1º cut retorna sr = **{sr_proof} Hz** (augmentação em RAM, sem WAV em disco)",
        "",
        "## CER por clip",
        "",
        "| clip | CER(h1→h2) | mantido? |",
        "|---|---|---|",
    ]
    for cid in sorted(cers):
        lines.append(f"| {cid} | {cers[cid]:.3f} | {'✅' if cid in kept else '❌ descartado'} |")
    lines += [
        "",
        "## Leitura honesta (caveats do review)",
        "",
        f"- **H-1 (par de transcritores):** esta run usou `{sizes[0]}`+`{sizes[1]}`, não o `small`+`medium` do ADR-3. `base` é mais próximo de `small` que `medium` → dois modelos adjacentes correlacionam erros **ainda mais**; a distribuição estreita (média {mean:.3f}) é parcialmente artefato do par, não sinal de qualidade. small+medium fica para quando houver RAM/tempo.",
        "- **M-2 (fração mantida é tautológica):** manter ~80% aqui é por construção (`keep_fraction=0.8` calibra τ na MESMA amostra). Não é evidência de qualidade dos pseudo-labels; medir qualidade exige um conjunto com referência humana (M4/fine-tune), que não existe neste piloto.",
        "- **M-3 (fonte-piloto):** os clips vêm do split `test` do **FLEURS** — usado aqui como **fonte-piloto de conveniência**, NÃO o test set de call-center do produto (`PRD § 7.3`). Nenhum pseudo-label toca a suíte de avaliação; o invariante § 3 #10 é respeitado por convenção do operador (o split train/test do produto é materializado fora deste módulo).",
        "- **Caveat ADR-3 (correlação):** os 2 whisper são da mesma família → correlacionam erros; a concordância superestima confiança. Um 2º transcritor de arquitetura distinta (parakeet) melhora o sinal (backlog).",
        "- **Escopo estatístico:** n=20 é piloto; o IC de τ (percentil de 20 pontos) é largo (ver acima). Re-calibrar em corpus maior em M4 — este τ não é verdade final, é o operacional do piloto.",
    ]
    Path(REPORT).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--keep", type=float, default=0.8)
    ap.add_argument("--sizes", nargs=2, default=["small", "base"])
    args = ap.parse_args()
    sizes = (args.sizes[0], args.sizes[1])
    cmd = f"python3 training/corpus/run_pipeline.py --n {args.n} --keep {args.keep} --sizes {sizes[0]} {sizes[1]}"

    import tempfile

    out_dir = tempfile.mkdtemp(prefix="m3_corpus_")
    print(f"[pipeline] carregando {args.n} clips FLEURS pt_br → {out_dir}", flush=True)
    paths = load_fleurs_wavs(args.n, out_dir)
    print(f"[pipeline] {len(paths)} WAVs; transcrevendo com {sizes} (sequencial)...", flush=True)

    pairs = transcribe_pair(paths, sizes=sizes)
    cers = {cid: pairwise_cer(h1, h2) for cid, (h1, h2) in pairs.items()}
    tau = calibrate_tau(list(cers.values()), keep_fraction=args.keep)
    # o filtro por concordância decide quais segmentos entram no pool (review M2: usa agree())
    kept = {cid for cid in paths if agree(pairs[cid][0], pairs[cid][1], tau)}
    print(f"[pipeline] τ={tau:.3f}; mantidos {len(kept)}/{len(cers)}", flush=True)

    # manifest Lhotse com telephone on-the-fly, FILTRADO pelo predicado de concordância (B-1)
    full = build_cutset(out_dir, {cid: pairs[cid][0] for cid in paths})
    cutset = filter_cutset(full, kept)
    n_cuts = len(cutset)
    if n_cuts == 0:
        raise RuntimeError("pipeline: manifest vazio após o filtro — nada a treinar (fail-fast)")
    if n_cuts != len(kept):
        raise RuntimeError(f"pipeline: manifest ({n_cuts}) != aprovados ({len(kept)}) — filtro inconsistente")
    _audio, sr_proof = load_telephone_audio(list(cutset)[0])
    print(f"[pipeline] manifest FILTRADO: {n_cuts} cuts; telephone on-the-fly → {sr_proof} Hz", flush=True)

    write_report(cers, tau, kept, sizes, sr_proof, n_cuts, args.keep, cmd)
    print(f"[pipeline] evidência gravada em {REPORT}", flush=True)


if __name__ == "__main__":
    main()
