"""Testes do bootstrap pareado de WER (M4 fase 3) — determinístico (seed fixo).

Protege o cálculo que sustenta a conclusão da ablação: um bug no pareamento ou na
reamostragem produziria um IC errado num artefato de decisão.
"""

import pytest

from bootstrap_wer_ci import paired_bootstrap, per_utterance_errors  # noqa: E402


def test_ponto_e_ic_de_caso_conhecido_e_deterministico():
    # baseline erra 4 palavras em 10; candidato erra 2 em 10 → 40%→20%, melhora rel 50%.
    rows = [(2, 1, 5), (2, 1, 5)]  # (werr_base, werr_cand, n_ref) por utterance
    r = paired_bootstrap(rows, n_boot=1000, seed=42)
    assert r["wer_base"] == pytest.approx(40.0)
    assert r["wer_cand"] == pytest.approx(20.0)
    assert r["abs_diff_pp"] == pytest.approx(20.0)
    assert r["rel_impr_pct"] == pytest.approx(50.0)
    # seed fixo → resultado idêntico entre execuções (determinismo, testing.md § 6)
    assert paired_bootstrap(rows, n_boot=1000, seed=42) == r
    # probabilidades emitidas pelo próprio script (proveniência fechada, review M4):
    # melhora relativa é sempre 50% neste caso → P(>0)=P(>=3%)=100%.
    assert r["p_gt0_pct"] == pytest.approx(100.0)
    assert r["p_ge_thr_pct"] == pytest.approx(100.0)
    assert r["dod_threshold"] == 3.0


def test_falha_alto_com_rows_vazio():
    # Caso negativo: sem utterances pareadas NÃO pode virar IC [0,0] silencioso.
    with pytest.raises(ValueError, match="nenhuma utterance"):
        paired_bootstrap([])


def test_per_utterance_falha_alto_em_test_sets_diferentes():
    # Caso negativo: utterances distintas entre os dois recogs → pareamento inválido.
    base = "u1:\tref=['a']\nu1:\thyp=['a']\n"
    cand = "u2:\tref=['a']\nu2:\thyp=['a']\n"
    with pytest.raises(ValueError, match="utterances"):
        per_utterance_errors(base, cand)


def test_per_utterance_falha_alto_quando_referencia_difere():
    # Mesma utterance mas refs diferentes → não é o mesmo alvo, comparação sem sentido.
    base = "u1:\tref=['casa']\nu1:\thyp=['casa']\n"
    cand = "u1:\tref=['carro']\nu1:\thyp=['carro']\n"
    with pytest.raises(ValueError, match="referência difere"):
        per_utterance_errors(base, cand)
