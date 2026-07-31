"""O artefato de uma corrida é nomeado pela configuração que a define.

O destino era fixo (`wiki/medicoes/m3-cer-distribution.md`), e isso produziu dois defeitos
distintos que a mesma correção resolve:

1. **Corridas incomparáveis competiam pelo mesmo arquivo.** `--n 200` e `--n 5` são
   experimentos diferentes; o segundo apagava a evidência do primeiro em silêncio. A proteção
   contra sobrescrita trata o sintoma — o nome derivado da configuração remove a causa.

2. **O script escrevia no lugar da conclusão curada.** `wiki/medicoes/*.md` é escrito por
   humano; `dados-brutos/` é evidência de máquina, nomeada pela condição que a produziu
   (`small-idle.json`, `medium-load.json` — ver `dados-brutos/index.md`).

O corolário é o que importa em ML e é o que o último teste guarda: a **mesma** configuração
ainda colide de propósito. Repetir um experimento tem de ser um ato explícito, não um efeito
colateral de rodar o script de novo.
"""
from __future__ import annotations

from pathlib import Path

from corpus.run_pipeline import caminho_da_corrida

PKG = Path(__file__).resolve().parents[1]


def test_configuracoes_diferentes_nao_competem_pelo_mesmo_arquivo():
    """Cada eixo livre da receita separa o artefato — nenhum é decorativo no nome."""
    base = caminho_da_corrida(20, 0.8, ("small", "base"))
    variacoes = {
        "n": caminho_da_corrida(200, 0.8, ("small", "base")),
        "keep": caminho_da_corrida(20, 0.9, ("small", "base")),
        "transcritores": caminho_da_corrida(20, 0.8, ("small", "medium")),
    }
    colidem = [eixo for eixo, p in variacoes.items() if p == base]
    assert not colidem, (
        f"mudar {colidem} não muda o nome do artefato — duas corridas incomparáveis vão "
        "dividir um arquivo, e a segunda apaga a primeira"
    )
    assert len(set(variacoes.values())) == 3, "duas variações distintas colapsaram no mesmo nome"


def test_a_mesma_configuracao_da_o_mesmo_caminho():
    """Determinístico de propósito: é o que faz a recusa de sobrescrita ser a resposta certa.

    Se o nome carregasse timestamp, cada repetição criaria um arquivo novo e re-medir a MESMA
    configuração deixaria de ser um ato explícito — vira acúmulo silencioso de corridas
    idênticas, e nenhuma delas é a autoritativa.
    """
    a = caminho_da_corrida(20, 0.8, ("small", "base"))
    b = caminho_da_corrida(20, 0.8, ("small", "base"))
    assert a == b


def test_o_destino_e_ancorado_no_repositorio_e_nao_no_cwd():
    """`wiki/medicoes/dados-brutos/` — evidência de máquina, nunca a conclusão curada.

    O caminho antigo era relativo: rodar de outro diretório escrevia no lugar errado (ou
    falhava). E apontava para `wiki/medicoes/*.md`, que é onde vive o texto escrito por humano.
    """
    p = caminho_da_corrida(20, 0.8, ("small", "base"))
    assert p.is_absolute(), f"caminho relativo depende do CWD: {p}"
    assert p.parent == PKG.parent / "wiki" / "medicoes" / "dados-brutos", p.parent
    assert p.parent.name == "dados-brutos", (
        "artefato de corrida não pode nascer em wiki/medicoes/ — lá é conclusão curada"
    )


def test_a_raiz_e_injetavel_para_o_teste_nao_escrever_na_wiki():
    """Sem isto, exercitar a gravação exigiria escrever dentro da evidência publicada."""
    p = caminho_da_corrida(5, 0.5, ("tiny", "base"), raiz=Path("/tmp/x"))
    assert p.parent == Path("/tmp/x")
    assert "n5" in p.name and "keep0.50" in p.name and "tiny+base" in p.name
