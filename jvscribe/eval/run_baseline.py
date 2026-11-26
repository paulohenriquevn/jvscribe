"""Baseline de M1 sobre o test set 8 kHz proxy (T4.1).

Orquestra a régua ponta-a-ponta: lê um manifesto de test set (transcrição
humana, NUNCA pseudo-label — invariante do projeto), aplica a cadeia de
augmentação telefônica (`common/audio/augment.sh`), transcreve com um modelo
baseline, e computa WER+IC via `eval_wer`. Emite um relatório com rótulo de
proveniência `[MEDIDO]` (disciplina de evidência).

O modelo é injetado (`transcribe_fn`) — DIP: mock determinístico no teste,
Moonshine/whisper real na execução. A descoberta (blueprint ADR D2) fixou que o
test set v1 é PROXY de canal sobre corpus público, rotulado honestamente.

Uso como lib:
    from run_baseline import measure_baseline, BaselineError
    report = measure_baseline(manifest, transcribe_fn=my_asr, model_name="moonshine")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from eval_wer import WerError, wer_with_ci
from report import ambiente as ambiente_de_relatorio

_AMBIENTE = ambiente_de_relatorio(Path(__file__).resolve().parent / "templates")

# Limiares do caveat de poder estatístico. Nomeados porque a condição é uma REGRA — enterrada
# como literal num `if`, ninguém sabia que 20 p.p. e 50 utterances eram a fronteira.
IC_LARGO = 0.20                 # largura do IC95 acima da qual ele não separa candidatos
N_MINIMO_PARA_DECIDIR = 50      # abaixo disto o IC é largo por poder, não por defeito da régua

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
        BaselineError: se alguma entrada é pseudo-label (invariante do projeto)
                       ou o manifesto está vazio.
    """
    if not entries:
        raise BaselineError("manifesto vazio: nenhuma utterance para o baseline")
    utts = []
    for i, e in enumerate(entries):
        if e.get("pseudo_label", False):
            raise BaselineError(
                f"utterance {i} ({e.get('audio_path','?')}) é pseudo-label — "
                "PROIBIDO no test set (invariante do projeto)"
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

    # O corpo saiu para `templates/baseline.md.j2`. Além da prosa ficar editável sem tocar
    # Python, a migração corrigiu um defeito que só a RENDERIZAÇÃO expunha: a tabela tinha 4
    # cabeçalhos e 5 células, e a spec do GFM ignora a excedente — o `[MEDIDO]` sumia.
    return _AMBIENTE.get_template("baseline.md.j2").render({
        "corpus_note": corpus_note,
        "provenance": provenance,
        "resultados": results,
        "n_minimo": N_MINIMO_PARA_DECIDIR,
        # Prosa condicional: exige as DUAS condições. IC largo com n grande é outra conversa
        # (variância real do corpus), e n pequeno com IC estreito não precisa de ressalva.
        "ic_largo_com_amostra_pequena": (
            any((r.ci_high - r.ci_low) > IC_LARGO for r in results)
            and any(r.n < N_MINIMO_PARA_DECIDIR for r in results)
        ),
    })
