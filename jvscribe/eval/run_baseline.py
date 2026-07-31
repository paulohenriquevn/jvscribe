"""Baseline de M1 sobre o test set 8 kHz proxy (T4.1).

Orquestra a régua ponta-a-ponta: lê um manifesto de test set (transcrição
humana, NUNCA pseudo-label — invariante `PRD.md` § 7.3), aplica a cadeia de
augmentação telefônica (`common/audio/augment.sh`), transcreve com um modelo
baseline, e computa WER+IC via `eval_wer`. Emite um relatório com rótulo de
proveniência `[MEDIDO]` (`.claude/rules/asr-evidence-discipline.md` § 1).

O modelo é injetado (`transcribe_fn`) — DIP: mock determinístico no teste,
Moonshine/whisper real na execução. A descoberta (blueprint ADR D2) fixou que o
test set v1 é PROXY de canal sobre corpus público, rotulado honestamente.

Uso como lib:
    from run_baseline import measure_baseline, BaselineError
    report = measure_baseline(manifest, transcribe_fn=my_asr, model_name="moonshine")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from eval_wer import WerError, wer_with_ci

# transcribe_fn: recebe o caminho do WAV (já augmentado), devolve a hipótese.
TranscribeFn = Callable[[str], str]


class BaselineError(Exception):
    """Erro tipado do baseline (fail-fast, error-handling.md § 2)."""


@dataclass(frozen=True)
class Utterance:
    """Uma entrada do manifesto: áudio + transcrição humana de referência."""

    audio_path: str
    reference: str
    pseudo_label: bool = False


def load_manifest(entries: list[dict]) -> list[Utterance]:
    """Converte entradas de manifesto em Utterances, rejeitando pseudo-labels.

    Raises:
        BaselineError: se alguma entrada é pseudo-label (invariante PRD § 7.3)
                       ou o manifesto está vazio.
    """
    if not entries:
        raise BaselineError("manifesto vazio: nenhuma utterance para o baseline")
    utts = []
    for i, e in enumerate(entries):
        if e.get("pseudo_label", False):
            raise BaselineError(
                f"utterance {i} ({e.get('audio_path','?')}) é pseudo-label — "
                "PROIBIDO no test set (PRD § 7.3, invariante)"
            )
        utts.append(
            Utterance(
                audio_path=e["audio_path"],
                reference=e["reference"],
                pseudo_label=False,
            )
        )
    return utts


@dataclass(frozen=True)
class BaselineResult:
    """Resultado do baseline de um modelo."""

    model_name: str
    wer: float
    ci_low: float
    ci_high: float
    n: int


def measure_baseline(
    manifest: list[dict],
    *,
    transcribe_fn: TranscribeFn,
    model_name: str,
    seed: int = 1234,
    n_boot: int = 1000,
) -> BaselineResult:
    """Mede WER+IC de um modelo sobre o test set.

    Args:
        manifest: lista de entradas {audio_path, reference, pseudo_label?}.
        transcribe_fn: função que transcreve um WAV → hipótese.
        model_name: nome do modelo (para o rótulo de proveniência).
        seed, n_boot: parâmetros do bootstrap.

    Raises:
        BaselineError: manifesto vazio, pseudo-label, ou zero utterances válidas.
    """
    # load_manifest já falha em manifesto vazio (EC-5: "0 utterances"), então
    # após ele `utts` tem ≥ 1 entrada e `pairs` também — não há branch morto de
    # "0 após transcrição" (review TEST-M1-02).
    utts = load_manifest(manifest)

    pairs: list[tuple[str, str]] = []
    for u in utts:
        hyp = transcribe_fn(u.audio_path)
        pairs.append((u.reference, hyp))

    try:
        r = wer_with_ci(pairs, seed=seed, n_boot=n_boot)
    except WerError as e:
        raise BaselineError(f"falha ao computar WER: {e}") from e

    return BaselineResult(
        model_name=model_name,
        wer=r.wer,
        ci_low=r.ci_low,
        ci_high=r.ci_high,
        n=r.n,
    )


def render_report(
    results: list[BaselineResult],
    *,
    corpus_note: str,
    provenance: str | None = None,
) -> str:
    """Renderiza o relatório Markdown com rótulos de proveniência [MEDIDO].

    Cada linha de WER carrega o IC 95% e o rótulo — nunca um ponto sem incerteza.
    `provenance` (comando/hardware/seed/n_boot) é o bloco que `[MEDIDO]` exige
    (`asr-evidence-discipline.md` § 1) para o número ser reproduzível a partir do
    próprio relatório (review EVID-01).
    """
    if not results:
        raise BaselineError("nenhum resultado para renderizar")

    lines = [
        "# M1 — Baseline Report (test set 8 kHz)",
        "",
        f"**Corpus:** {corpus_note}",
        "",
        "> Transcrição humana (NUNCA pseudo-label — `PRD.md` § 7.3). Números "
        "`[MEDIDO]`; WER sempre com IC 95% via bootstrap por-utterance (blueprint "
        "ADR D3), nunca ponto isolado.",
        "",
    ]
    if provenance:
        lines += [f"**Proveniência `[MEDIDO]`:** {provenance}", ""]
    lines += [
        "| Modelo | WER | IC 95% | n (utterances) |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.model_name} | WER = {r.wer*100:.1f}% "
            f"| [IC95: {r.ci_low*100:.1f}%–{r.ci_high*100:.1f}%] "
            f"| {r.n} | `[MEDIDO]`"
        )
    # Enquadramento do IC largo como o risco 1 do ROADMAP, não defeito da régua
    # (review EVID-05).
    wide = any((r.ci_high - r.ci_low) > 0.20 for r in results)
    small_n = any(r.n < 50 for r in results)
    if wide and small_n:
        lines += [
            "",
            "> **IC largo por poder estatístico, não defeito da régua.** Com n < 50 "
            "o IC de ~50 p.p. não decide entre candidatos — é o **risco 1 do "
            "ROADMAP** (`ROADMAP.md` § M1). Um test set maior é pré-requisito para "
            "M4 comparar finalistas.",
        ]
    lines.append("")
    return "\n".join(lines)
