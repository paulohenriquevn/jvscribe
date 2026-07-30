"""WER com intervalo de confiança 95% via bootstrap (M1 — T3.1).

Calcula WER reusando `jiwer` (Não-Reinvente — `.claude/rules/parsimony-ladder.md`
rung 4; mesma lib de `moonshine/scripts/eval-librispeech.py:57`), normaliza com o
normalizador PT-BR próprio, e reporta o IC 95% reamostrando as utterances com
reposição (blueprint ADR D3).

O IC ataca o risco 1 do ROADMAP (20 min de áudio → IC largo): a régua SEMPRE
reporta a incerteza, nunca um ponto isolado (falácia § 3 #12).

Determinístico: seed fixa → resultado reprodutível (`.claude/rules/testing.md` § 6).

Uso como lib:
    from eval_wer import wer_with_ci
    r = wer_with_ci([("a b c", "a b c"), ...], seed=1234)
    # r -> WerResult(wer=..., ci_low=..., ci_high=..., n=...)
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import jiwer

from text_normalize_ptbr import normalize_for_wer_compare as normalize_ptbr


class WerError(Exception):
    """Erro tipado do cálculo de WER (fail-fast, error-handling.md § 2)."""


@dataclass(frozen=True)
class WerResult:
    """Resultado de WER com IC. Percentuais em [0, ...]; n = nº de utterances."""

    wer: float
    ci_low: float
    ci_high: float
    n: int


def _corpus_wer(pairs: list[tuple[str, str]]) -> float:
    """WER agregado corpus-wide sobre pares (ref, hyp) já normalizados.

    Usa jiwer.process_words para obter ins/del/sub e divide pelo total de
    palavras de referência (definição canônica de WER).
    """
    refs = [r for r, _ in pairs]
    hyps = [h for _, h in pairs]
    # Fail-fast na fronteira (error-handling.md § 2): referência vazia é input
    # inválido. Validamos ANTES de jiwer para emitir o erro TIPADO do domínio,
    # não o ValueError genérico da lib.
    if any(len(r.strip()) == 0 for r in refs):
        raise WerError("referência vazia: toda utterance precisa de texto de referência")
    total_ref_words = sum(len(r.split()) for r in refs)
    if total_ref_words == 0:
        raise WerError("referência vazia: total de palavras de referência é zero")
    out = jiwer.process_words(refs, hyps)
    errors = out.insertions + out.deletions + out.substitutions
    return errors / total_ref_words


def wer_with_ci(
    pairs: list[tuple[str, str]],
    *,
    seed: int = 1234,
    n_boot: int = 1000,
    normalize: bool = True,
) -> WerResult:
    """WER + IC 95% por bootstrap por-utterance.

    Args:
        pairs: lista de (referência, hipótese) por-utterance.
        seed: semente do RNG (reprodutibilidade).
        n_boot: nº de reamostragens bootstrap.
        normalize: aplica o normalizador PT-BR antes (default True).

    Returns:
        WerResult com wer pontual e IC 95% (percentis 2,5–97,5).

    Raises:
        WerError: se `pairs` vazio ou referência total vazia.
    """
    if not pairs:
        raise WerError("nenhuma utterance para avaliar (lista vazia)")

    if normalize:
        pairs = [(normalize_ptbr(r), normalize_ptbr(h)) for r, h in pairs]

    point = _corpus_wer(pairs)

    # Bootstrap: reamostra as utterances com reposição, recomputa WER.
    rng = random.Random(seed)
    n = len(pairs)
    boot: list[float] = []
    for _ in range(n_boot):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        try:
            boot.append(_corpus_wer(sample))
        except WerError:
            # Reamostragem degenerada (todas refs vazias) — ignora essa iteração.
            continue

    boot.sort()
    if not boot:
        # N=1 com ref não-vazia mas todas as reamostragens degeneraram: IC = ponto.
        return WerResult(wer=point, ci_low=point, ci_high=point, n=n)

    lo = boot[int(0.025 * (len(boot) - 1))]
    hi = boot[int(0.975 * (len(boot) - 1))]
    return WerResult(wer=point, ci_low=lo, ci_high=hi, n=n)
