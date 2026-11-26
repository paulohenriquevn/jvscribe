"""O rótulo `[MEDIDO]` sumia da tabela renderizada.

`asr-evidence-discipline.md` § 1: *"Todo número carrega rótulo de proveniência. Sem rótulo, o
número não existe."* A tabela de `run_baseline.render_report` declarava **4** colunas no
cabeçalho e emitia **5** células por linha — a quinta era justamente o `` `[MEDIDO]` ``.

Pela spec do GFM, célula excedente é **ignorada**. `[MEDIDO]` 2026-07-31 com o renderizador
`markdown`: o rótulo não aparece no `<table>`. Quem lê o `.md` cru vê o rótulo; quem lê o
relatório renderizado — na wiki, no GitHub — vê uma tabela de WER **sem proveniência nenhuma**.

O defeito é invisível na fonte: o texto está lá. Só a renderização o revela.
"""
from __future__ import annotations

import pytest

from run_baseline import BaselineResult, render_report

UM = BaselineResult(model_name="whisper-small", wer=0.096, ci_low=0.04, ci_high=0.16, n=12)


def _tabela_html(md: str) -> str:
    markdown = pytest.importorskip("markdown")
    html = markdown.markdown(md, extensions=["tables"])
    return html[html.index("<table"):html.index("</table>") + 8]


def test_o_rotulo_de_proveniencia_sobrevive_a_renderizacao():
    tabela = _tabela_html(render_report([UM], corpus_note="teste"))
    assert "MEDIDO" in tabela, (
        "o rótulo de proveniência foi descartado pelo renderizador — a tabela publica WER "
        "sem dizer de onde veio (asr-evidence-discipline § 1)"
    )


def test_cabecalho_e_linhas_tem_o_mesmo_numero_de_celulas():
    """A causa: 4 cabeçalhos, 5 células. Guardar a forma impede a regressão silenciosa."""
    linhas = [ln for ln in render_report([UM], corpus_note="t").splitlines()
              if ln.startswith("|") and "---" not in ln]
    larguras = {ln.count("|") for ln in linhas}
    assert len(larguras) == 1, f"linhas com contagens diferentes de `|`: {larguras}"


def test_cada_wer_carrega_seu_intervalo():
    """Ponto sem incerteza é proibido (falácia § 3 #12) — nunca um WER sozinho.

    O intervalo agora é uma COLUNA nomeada no cabeçalho, em vez de repetir "IC95:" em cada
    célula. A checagem é sobre a informação chegar junto do número, não sobre o literal.
    """
    tabela = _tabela_html(render_report([UM], corpus_note="t"))
    assert "IC 95%" in tabela, "a coluna de incerteza sumiu do cabeçalho"
    assert "9.6%" in tabela and "4.0%" in tabela and "16.0%" in tabela


def test_sem_resultado_recusa_em_vez_de_emitir_tabela_vazia():
    from run_baseline import BaselineError

    with pytest.raises(BaselineError):
        render_report([], corpus_note="t")


def test_o_caveat_de_ic_largo_so_aparece_quando_ele_e_largo():
    """Prosa condicional — a mesma classe do caveat H-1 que se contradizia no corpus."""
    estreito = BaselineResult(model_name="m", wer=0.10, ci_low=0.09, ci_high=0.11, n=500)
    # `UM` tem IC de 12 p.p. — abaixo do limiar de 20 p.p.; escrevi o teste supondo que
    # bastava ser "pequeno" e ele falhou. O caveat exige as DUAS condições: IC largo E n < 50.
    largo = BaselineResult(model_name="m", wer=0.50, ci_low=0.20, ci_high=0.80, n=12)
    assert "risco 1 do" not in render_report([estreito], corpus_note="t")
    assert "risco 1 do" not in render_report([UM], corpus_note="t"), "12 p.p. não é largo"
    assert "risco 1 do" in render_report([largo], corpus_note="t")
