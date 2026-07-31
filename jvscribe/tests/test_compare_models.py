"""Testes da régua de comparação entre modelos.

Existe porque "qual modelo é melhor" foi decidido por NOME mais de uma vez neste projeto —
"final", "leve", "SOTA". A ferramenta só tem valor se a régua estiver certa: WER errado leva
a apagar o modelo errado, e `models/` é gitignored (não volta).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "eval"))
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

from compare_models import _bootstrap_ic, _carregar, _wer_cer  # noqa: E402


def _fixture(tmp_path, pares):
    refs = tmp_path / "refs.tsv"
    hyps = tmp_path / "hyps"
    hyps.mkdir()
    with refs.open("w", encoding="utf-8") as f:
        for i, (r, h) in enumerate(pares):
            f.write(f"u{i}\t{r}\n")
            (hyps / f"u{i}.txt").write_text(h, encoding="utf-8")
    return refs, hyps


def test_transcricao_identica_da_wer_zero(tmp_path):
    refs, hyps = _fixture(tmp_path, [("o gato subiu", "o gato subiu")])
    wer, cer, _, n = _wer_cer(_carregar(refs, hyps))
    assert wer == 0.0 and cer == 0.0 and n == 1


def test_uma_palavra_errada_em_quatro_da_25_por_cento(tmp_path):
    refs, hyps = _fixture(tmp_path, [("o gato subiu telhado", "o gato desceu telhado")])
    wer, _, palavras, _ = _wer_cer(_carregar(refs, hyps))
    assert palavras == 4
    assert wer == pytest.approx(25.0)


def test_acento_nao_conta_como_erro(tmp_path):
    """A régua de COMPARAÇÃO remove acento — senão mede ortografia, não reconhecimento."""
    refs, hyps = _fixture(tmp_path, [("coração e atenção", "coracao e atencao")])
    wer, _, _, _ = _wer_cer(_carregar(refs, hyps))
    assert wer == 0.0


def test_so_pareia_ids_presentes_nos_dois_lados(tmp_path):
    """Hipótese ausente não pode entrar como acerto nem como erro — tem de sumir da conta."""
    refs, hyps = _fixture(tmp_path, [("um dois", "um dois"), ("tres quatro", "tres quatro")])
    (hyps / "u1.txt").unlink()
    pares = _carregar(refs, hyps)
    assert len(pares) == 1, "utterance sem hipótese deveria ser excluída do pareamento"


def test_bootstrap_devolve_intervalo_que_contem_a_estimativa(tmp_path):
    pares = [("a b c d", "a b c x")] * 20
    refs, hyps = _fixture(tmp_path, pares)
    carregados = _carregar(refs, hyps)
    wer, _, _, _ = _wer_cer(carregados)
    lo, hi = _bootstrap_ic(carregados, n=200)
    assert lo <= wer <= hi, f"IC [{lo}, {hi}] não contém o WER pontual {wer}"


def test_bootstrap_e_deterministico(tmp_path):
    """Seed fixa — senão a mesma comparação dá vereditos diferentes a cada execução."""
    refs, hyps = _fixture(tmp_path, [("a b c", "a b x")] * 10)
    p = _carregar(refs, hyps)
    assert _bootstrap_ic(p, n=100) == _bootstrap_ic(p, n=100)
