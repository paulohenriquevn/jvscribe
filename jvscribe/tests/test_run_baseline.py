"""Testes do baseline (M1 — T4.1). Mock-based e determinísticos."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_baseline import (  # noqa: E402
    BaselineError,
    measure_baseline,
    render_report,
)


def _perfect_asr(reference_by_path: dict[str, str]):
    """Mock: transcreve exatamente a referência (WER 0) — determinístico."""
    return lambda path: reference_by_path[path]


def test_baseline_report_has_ci_and_provenance():
    manifest = [
        {"audio_path": "a.wav", "reference": "bom dia"},
        {"audio_path": "b.wav", "reference": "boa tarde"},
    ]
    # ASR mock com 1 erro em b.wav.
    def asr(path):
        return {"a.wav": "bom dia", "b.wav": "boa noite"}[path]

    result = measure_baseline(
        manifest, transcribe_fn=asr, model_name="mock-asr", seed=1, n_boot=200
    )
    report = render_report([result], corpus_note="mock (teste)")
    # Asserções sobre INTENÇÃO, não sobre o literal do formato. As anteriores exigiam
    # "IC95" e "WER =" — artefatos de quando cada célula repetia o nome da grandeza. Ao
    # nomear as colunas no cabeçalho, o texto mudou e a informação não; a guarda reprovava
    # a melhoria. Quem confere o RENDER (onde o defeito real morava) é
    # `test_relatorio_baseline.py`.
    assert "IC 95%" in report, "relatório deve declarar a coluna de incerteza"
    assert f"{result.ci_low * 100:.1f}%" in report, "limite inferior do IC ausente"
    assert f"{result.ci_high * 100:.1f}%" in report, "limite superior do IC ausente"
    assert "[MEDIDO]" in report, "relatório deve conter rótulo de proveniência"
    assert f"{result.wer * 100:.1f}%" in report, "o WER medido não aparece"


def test_testset_rejects_pseudolabel():
    # Negative: manifesto com pseudo-label é rejeitado (invariante do projeto).
    manifest = [
        {"audio_path": "a.wav", "reference": "ok", "pseudo_label": True},
    ]
    with pytest.raises(BaselineError, match="pseudo-label"):
        measure_baseline(
            manifest, transcribe_fn=lambda p: "ok", model_name="m", seed=1
        )


def test_baseline_empty_manifest_is_error():
    # EC-5: manifesto vazio (= 0 utterances mensuráveis) → erro claro, sem divisão
    # por zero. match= fixa a condição específica (testing.md § 4.1).
    with pytest.raises(BaselineError, match="manifesto vazio"):
        measure_baseline([], transcribe_fn=lambda p: "", model_name="m", seed=1)


def test_baseline_perfect_asr_is_zero_wer():
    manifest = [
        {"audio_path": "a.wav", "reference": "um dois tres"},
        {"audio_path": "b.wav", "reference": "quatro cinco"},
    ]
    ref_by_path = {"a.wav": "um dois tres", "b.wav": "quatro cinco"}
    result = measure_baseline(
        manifest,
        transcribe_fn=_perfect_asr(ref_by_path),
        model_name="oracle",
        seed=1,
        n_boot=100,
    )
    assert result.wer == 0.0
    assert result.n == 2
