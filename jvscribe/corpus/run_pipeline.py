"""Orquestra o pipeline de corpus de M3 ponta-a-ponta sobre FLEURS pt_br real.

Fluxo (Integration Validation do plano m3-corpus):
  FLEURS pt_br (N clips) → 2 whisper sequenciais → CER par-a-par → τ calibrado →
  filtro por concordância (aplicado AO MANIFEST) → manifest Lhotse com telephone
  on-the-fly → evidência [MEDIDO].

Cada corrida grava a própria evidência em `wiki/medicoes/dados-brutos/`, com o nome derivado
da configuração que a define (`caminho_da_corrida`) — duas configurações diferentes nunca
competem pelo mesmo arquivo. Uso:
  python3 jvscribe/corpus/run_pipeline.py --n 20 --sizes small base
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

import jinja2
import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/

from common.metrics import escrever_relatorio  # noqa: E402
from corpus.agreement_filter import agree, calibrate_tau, pairwise_cer  # noqa: E402
from corpus.build_manifest import build_cutset, filter_cutset, load_telephone_audio  # noqa: E402
from corpus.pseudo_label import transcribe_pair  # noqa: E402

_BOOTSTRAP_SEED = 20260725  # fixo → IC reprodutível
PAR_DO_ADR3 = ("small", "medium")  # o par de transcritores que o ADR-3 especifica

# O corpo do relatório é PROSA — caveats, leitura honesta, separação hipótese/evidência. Sai
# do código porque ela tem CONDIÇÕES: o caveat H-1 só vale quando a corrida se desvia do par
# do ADR-3, e como f-string era emitido sempre — a corrida com o par certo produzia
# "usou small+medium, não o small+medium do ADR-3". Num template a condição é visível.
#
# `StrictUndefined` é o ponto que justifica o ambiente explícito: no default do Jinja, uma
# variável com nome errado renderiza VAZIO. Num documento de evidência isso é um número que
# some sem ninguém notar. Aqui levanta.
_AMBIENTE = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).resolve().parent / "templates"),
    undefined=jinja2.StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    autoescape=False,  # destino é Markdown, não HTML — escapar quebraria `&`, `<`, aspas
)

# `wiki/medicoes/*.md` é CONCLUSÃO — curada por humano, uma por assunto. `dados-brutos/` é
# EVIDÊNCIA de corrida, e a convenção de lá é nomear pela CONDIÇÃO que a produziu
# (`small-idle.json`, `medium-load.json` — ver `dados-brutos/index.md`).
# Ancorado no repositório, não no CWD: rodar de outro diretório escrevia no lugar errado.
_DADOS_BRUTOS = Path(__file__).resolve().parents[2] / "wiki" / "medicoes" / "dados-brutos"


def caminho_da_corrida(n: int, keep_fraction: float, sizes: tuple[str, str],
                       *, raiz: Path | None = None) -> Path:
    """Artefato desta corrida, nomeado pelos parâmetros que a **definem como experimento**.

    Um destino fixo faz corridas diferentes competirem pelo mesmo arquivo: `--n 200` e
    `--n 5` produzem experimentos DIFERENTES e o segundo apagava o primeiro. Foi por isso
    que a proteção contra sobrescrita precisou existir — ela trata o sintoma; o nome
    derivado da configuração remove a causa.

    O corolário é a parte que interessa em ML: a **mesma** configuração ainda colide de
    propósito, e aí a recusa é a resposta certa — você está prestes a substituir a evidência
    de um experimento idêntico. Repetir uma corrida tem de ser um ato explícito
    (`--force`), não um efeito colateral de rodar o script de novo.

    Fora do nome porque não são livres nesta receita: o corpus (FLEURS pt_br `test`), a
    métrica (CER direcional normalizado PT-BR) e a seed do bootstrap (`_BOOTSTRAP_SEED`).
    Se algum deles virar parâmetro, entra aqui — senão duas corridas incomparáveis voltam a
    dividir um nome.
    """
    return (raiz or _DADOS_BRUTOS) / (
        f"m3-cer-n{n}-keep{keep_fraction:.2f}-{sizes[0]}+{sizes[1]}.md"
    )


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
                 keep_fraction: float, cmd: str, destino: Path,
                 *, force: bool = False) -> None:
    vals = list(cers.values())
    n = len(vals)
    mean = statistics.mean(vals)
    median = statistics.median(vals)
    std = statistics.stdev(vals) if n > 1 else 0.0  # amostral (ddof=1), review L-3
    sem = std / (n ** 0.5) if n > 0 else 0.0
    ci_lo, ci_hi = mean - 1.96 * sem, mean + 1.96 * sem
    tau_lo, tau_hi = _bootstrap_tau_ci(vals, keep_fraction)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    contexto = {
        "agora": now, "cpu": _cpu_model(), "cmd": cmd,
        "n": n, "n_clips": n, "a": sizes[0], "b": sizes[1],
        # A prosa do H-1 depende disto — e a condição fica VISÍVEL no template.
        "usou_par_do_adr": tuple(sizes) == PAR_DO_ADR3,
        "media": mean, "desvio": std, "mediana": median,
        "minimo": min(vals), "maximo": max(vals),
        "sem": sem, "ic_lo": ci_lo, "ic_hi": ci_hi,
        "tau": tau, "tau_lo": tau_lo, "tau_hi": tau_hi,
        "keep_fraction": keep_fraction, "keep_pct": int(keep_fraction * 100),
        "n_cuts": n_cuts, "n_mantidos": len(kept), "sr_proof": sr_proof,
        "clips": [{"id": cid, "cer": cers[cid], "mantido": cid in kept}
                  for cid in sorted(cers)],
    }
    texto = _AMBIENTE.get_template("m3-cer-distribution.md.j2").render(contexto)

    try:
        escrever_relatorio(destino, texto, force=force)
    except FileExistsError as e:
        # A corrida custou N transcrições com dois whisper: perder o resultado por
        # causa da recusa seria trocar um dano por outro. Imprime e sai com 1.
        print("\n" + texto)
        raise SystemExit(
            f"\n⚠️  relatório NÃO gravado: {e}\n"
            "Mesma configuração já medida — repetir é ato explícito (`--force`)."
        ) from e


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--keep", type=float, default=0.8)
    ap.add_argument("--sizes", nargs=2, default=["small", "base"])
    ap.add_argument("--out", type=Path, default=None,
                    help="destino do relatório; por padrão deriva da configuração da corrida "
                         "em wiki/medicoes/dados-brutos/")
    ap.add_argument("--force", action="store_true",
                    help="autoriza substituir a evidência de uma corrida com a MESMA configuração")
    args = ap.parse_args()
    sizes = (args.sizes[0], args.sizes[1])
    destino = args.out or caminho_da_corrida(args.n, args.keep, sizes)
    cmd = f"python3 jvscribe/corpus/run_pipeline.py --n {args.n} --keep {args.keep} --sizes {sizes[0]} {sizes[1]}"

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

    write_report(cers, tau, kept, sizes, sr_proof, n_cuts, args.keep, cmd,
                 destino, force=args.force)
    print(f"[pipeline] evidência gravada em {destino}", flush=True)


if __name__ == "__main__":
    main()
