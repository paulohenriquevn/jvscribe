"""O relatório de corrida não pode se contradizer sobre a própria configuração.

O caveat H-1 é **prosa condicional** — só faz sentido quando a corrida se desvia do par de
transcritores que o ADR-3 especifica (`small`+`medium`). Escrito como f-string no meio do
código, ele era emitido **sempre**, com os valores interpolados. Rodar exatamente o par do ADR
produzia:

    esta run usou `small`+`medium`, não o `small`+`medium` do ADR-3. `base` é mais próximo…

A frase se nega, e ainda discute um modelo (`base`) que não participou da corrida. É o defeito
que só aparece quando alguém finalmente roda a configuração certa — e aí o documento de
evidência afirma que ela não foi usada.

A causa não é estética. Prosa com condição embutida numa f-string **esconde a condição**: nada
no código diz "esta frase só vale se o par for outro". Num template a condição é visível
(`{% if %}`) e revisável.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from corpus.run_pipeline import write_report

MEDICAO = dict(cers={"c0": 0.05, "c1": 0.31}, tau=0.2, kept={"c0"},
               sr_proof=8000, n_cuts=1, keep_fraction=0.8, cmd="pytest")
PAR_DO_ADR = ("small", "medium")


def _relatorio(tmp_path: Path, sizes: tuple[str, str]) -> str:
    destino = tmp_path / "corrida.md"
    write_report(**MEDICAO, sizes=sizes, destino=destino)
    return destino.read_text(encoding="utf-8")


def test_nao_nega_o_par_que_a_propria_corrida_usou(tmp_path):
    """Rodar `small`+`medium` não pode gerar "não o `small`+`medium` do ADR-3"."""
    texto = _relatorio(tmp_path, PAR_DO_ADR)
    assert "não o `small`+`medium` do ADR-3" not in texto, (
        "a corrida USOU o par do ADR-3 e o relatório afirma que não usou — "
        "caveat condicional emitido incondicionalmente"
    )


def test_nao_discute_modelo_que_nao_participou_da_corrida(tmp_path):
    """`base` aparecia na análise de uma corrida `small`+`medium`."""
    texto = _relatorio(tmp_path, PAR_DO_ADR)
    corpo = texto[texto.index("Leitura honesta"):]
    assert "`base`" not in corpo, (
        "o caveat cita um transcritor que não rodou — texto fixo, não derivado da corrida"
    )


def test_o_desvio_do_adr_continua_sendo_declarado(tmp_path):
    """A guarda contra a contradição não pode virar silêncio sobre o desvio real.

    Corrigir "não se contradiz" apagando o caveat seria trocar um defeito por outro pior:
    a corrida `small`+`base` **é** um desvio do ADR-3 e o leitor precisa saber.
    """
    texto = _relatorio(tmp_path, ("small", "base"))
    assert "ADR-3" in texto and "small`+`base" in texto, (
        "corrida fora do par especificado tem de declarar o desvio"
    )


@pytest.mark.parametrize("sizes", [PAR_DO_ADR, ("small", "base"), ("tiny", "large-v3")])
def test_o_par_da_corrida_aparece_no_relatorio(tmp_path, sizes):
    """Qualquer par: o relatório nomeia quem transcreveu. Proveniência é obrigatória (§ 1)."""
    texto = _relatorio(tmp_path, sizes)
    assert f"`{sizes[0]}` + `{sizes[1]}`" in texto or f"`{sizes[0]}`+`{sizes[1]}`" in texto


def test_variavel_ausente_no_template_levanta_em_vez_de_render_vazio():
    """No default do Jinja, nome errado vira string vazia — num documento de evidência, um
    número que some sem ninguém notar. `StrictUndefined` transforma isso em erro.

    A guarda existe porque a saída natural, ao ver `UndefinedError`, é trocar o ambiente pelo
    default e "resolver" — o que devolve exatamente o modo de falha silencioso.

    Testa o helper do kernel (`common/report.ambiente`), não o ambiente de um consumidor:
    a invariante tem de valer para **todos**, e `test_dominios` garante que ninguém constrói
    o ambiente por fora.
    """
    import jinja2

    from common.report import ambiente

    env = ambiente(Path(__file__).parent)
    assert env.undefined is jinja2.StrictUndefined
    with pytest.raises(jinja2.UndefinedError):
        env.from_string("τ = {{ tau_com_nome_errado }}").render(tau=0.2)
