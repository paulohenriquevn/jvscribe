"""A tabela de vereditos não pode contradizer o caveat que está logo abaixo dela.

`live_transcribe` já declara `INDETERMINADO` em prosa quando a máquina está sob carga — foi a
correção D4 do live test. Mas a TABELA continuava estampando **❌** em RNF-01/02/03 na mesma
corrida. Quem bate o olho num relatório lê a tabela, não o parágrafo: a conclusão que sai é
"o produto reprovou o requisito de latência", quando o que houve foi uma medição inválida.

Reprovar e não-medir são resultados diferentes. Um manda consertar o produto; o outro manda
repetir a medição numa máquina ociosa. Trocar um pelo outro é a falácia § 3 #5 do contrato de
evidência — só que impressa em vermelho.

O recorte de quais critérios ficam indeterminados NÃO é escolha nova: `MetricasRNF` já separa
`veredito()` (RNF-01/02/03 — dependem de tempo, logo de contenção) de `veredito_condicoes()`
(RNF-04/05 — dependem da condição da corrida: duração e carga declarada). Duração continua
verdadeira sob carga; p99 não.
"""
from __future__ import annotations

import pytest

from realtime import live_transcribe as lt


@pytest.fixture()
def medicao_que_reprova():
    """RTFx 1,0× · p99 900 ms · backlog em 100% — os três critérios de tempo falham."""
    m = lt.MetricasRNF()
    for _ in range(5):
        m.registrar(audio_s=1.0, wall_s=1.0, latencia_s=0.9, backlog=1)
    return m


def _linhas_da_tabela(texto: str) -> dict[str, str]:
    return {
        linha.split("|")[1].strip(): linha
        for linha in texto.splitlines()
        if linha.startswith("| RNF-")
    }


def test_sob_carga_os_criterios_de_tempo_nao_saem_como_reprovados(
    medicao_que_reprova, monkeypatch
):
    monkeypatch.setattr(lt, "_carga_media", lambda: lt.LIMIAR_LOAD + 8.0)
    texto = lt.render_relatorio(medicao_que_reprova, lt.Transcricao(), carga=False, modelo="x")

    linhas = _linhas_da_tabela(texto)
    for rnf in ("RNF-01", "RNF-02", "RNF-03"):
        assert "❌" not in linhas[rnf], (
            f"{rnf} marcado como REPROVADO numa medição que o próprio relatório declara "
            f"indeterminada:\n  {linhas[rnf]}"
        )


def test_sob_carga_a_condicao_da_corrida_continua_sendo_julgada(
    medicao_que_reprova, monkeypatch
):
    """RNF-04/05 não dependem de contenção — apagá-los seria perder informação verdadeira.

    A duração da corrida é a duração da corrida, com a máquina ocupada ou não.
    """
    monkeypatch.setattr(lt, "_carga_media", lambda: lt.LIMIAR_LOAD + 8.0)
    linhas = _linhas_da_tabela(
        lt.render_relatorio(medicao_que_reprova, lt.Transcricao(), carga=False, modelo="x")
    )
    assert "❌" in linhas["RNF-04"], "corrida curta continua reprovando RNF-04 sob carga"


def test_com_maquina_ociosa_o_veredito_de_tempo_volta_a_valer(
    medicao_que_reprova, monkeypatch
):
    """A guarda não pode virar desculpa universal: ociosa, ❌ é ❌."""
    monkeypatch.setattr(lt, "_carga_media", lambda: 0.1)
    linhas = _linhas_da_tabela(
        lt.render_relatorio(medicao_que_reprova, lt.Transcricao(), carga=False, modelo="x")
    )
    for rnf in ("RNF-01", "RNF-02", "RNF-03"):
        assert "❌" in linhas[rnf], f"{rnf} deixou de reprovar numa medição válida"


def test_load_indisponivel_e_tratado_como_nao_medido(medicao_que_reprova, monkeypatch):
    """Sem `load average` não dá para atestar máquina ociosa — logo não dá para reprovar.

    Afirmar ❌ aqui seria concluir a partir de uma condição desconhecida.
    """
    monkeypatch.setattr(lt, "_carga_media", lambda: None)
    linhas = _linhas_da_tabela(
        lt.render_relatorio(medicao_que_reprova, lt.Transcricao(), carga=False, modelo="x")
    )
    assert "❌" not in linhas["RNF-02"]
