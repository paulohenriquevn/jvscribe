"""Conformidade do bundle `wiki/` com o Open Knowledge Format (OKF v0.1).

A wiki é onde o conhecimento do projeto vive, em formato
portátil — markdown com frontmatter YAML, um conceito por arquivo, links markdown normais.

Estes testes existem porque documentação sem guarda apodrece em silêncio. O README deste
projeto já teve **5 de 5 links internos** apontando para arquivos removidos, e a citação que
sustentava o número central estava entre eles.

Contrato OKF v0.1 verificado aqui:
- todo documento tem frontmatter YAML delimitado por `---`;
- todo documento declara `type` (o único campo obrigatório da spec);
- todo link interno resolve;
- todo diretório de conceitos tem `index.md` (progressive disclosure).
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WIKI = REPO / "wiki"

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
CAMPOS_OKF = {"type", "title", "description", "resource", "tags", "timestamp"}


def _docs() -> list[Path]:
    return sorted(WIKI.rglob("*.md"))


def _frontmatter(md: Path) -> str | None:
    t = md.read_text(encoding="utf-8")
    if not t.startswith("---\n"):
        return None
    partes = t.split("---\n", 2)
    return partes[1] if len(partes) >= 3 else None


pytestmark = pytest.mark.skipif(not WIKI.is_dir(), reason="bundle wiki/ ausente")


def test_o_bundle_nao_esta_vazio():
    assert len(_docs()) >= 10, "um bundle com menos de 10 conceitos não é uma base de conhecimento"


def test_todo_documento_tem_frontmatter():
    sem = [str(f.relative_to(REPO)) for f in _docs() if _frontmatter(f) is None]
    assert not sem, "documentos sem frontmatter YAML: " + ", ".join(sem)


def test_todo_documento_declara_type():
    """`type` é o ÚNICO campo que a spec OKF exige de todo conceito."""
    sem = [
        str(f.relative_to(REPO))
        for f in _docs()
        if not re.search(r"^type:\s*\S", _frontmatter(f) or "", re.M)
    ]
    assert not sem, "documentos sem o campo obrigatório `type`: " + ", ".join(sem)


def test_todo_link_interno_resolve():
    """Link quebrado é o modo de falha silencioso da documentação.

    Precedente: o README deste projeto teve 5 de 5 links internos apontando para arquivos
    removidos — incluindo a citação que sustentava o número central do projeto.
    """
    quebrados = []
    for f in _docs():
        for alvo in LINK.findall(f.read_text(encoding="utf-8")):
            if alvo.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if not (f.parent / alvo.split("#", 1)[0]).exists():
                quebrados.append(f"{f.relative_to(WIKI)} → {alvo}")
    assert not quebrados, "links internos quebrados: " + "; ".join(quebrados)


def test_todo_diretorio_de_conceitos_tem_index():
    """Progressive disclosure: um agente navega a hierarquia pelos `index.md`.

    Sem eles, descobrir o conteúdo exige listar o diretório — que é justamente o que o formato
    quer evitar.
    """
    sem = [
        str(d.relative_to(WIKI))
        for d in WIKI.iterdir()
        if d.is_dir() and not (d / "index.md").exists()
    ]
    assert not sem, "diretórios sem index.md: " + ", ".join(sem)


def test_a_raiz_tem_index_e_log():
    """`index.md` é a porta de entrada; `log.md` é o histórico cronológico (ambos reservados na spec)."""
    assert (WIKI / "index.md").exists(), "bundle sem index.md na raiz"
    assert (WIKI / "log.md").exists(), "bundle sem log.md na raiz"


def test_campos_do_frontmatter_ficam_no_vocabulario_da_spec():
    """Campo fora da spec vira ilha: nenhum consumidor OKF sabe o que fazer com ele.

    A spec deixa o content model livre, mas o **surface de interoperabilidade** é fechado —
    é o que permite bundles de produtores diferentes serem lidos por consumidores diferentes.
    """
    fora = []
    for f in _docs():
        for linha in (_frontmatter(f) or "").splitlines():
            m = re.match(r"^([a-z_]+):", linha)
            if m and m.group(1) not in CAMPOS_OKF:
                fora.append(f"{f.relative_to(WIKI)}: `{m.group(1)}`")
    assert not fora, "campos fora do vocabulário OKF v0.1: " + "; ".join(fora)


def test_nenhum_documento_e_so_frontmatter():
    """Negativo: um conceito sem corpo é um stub que finge cobertura."""
    vazios = []
    for f in _docs():
        corpo = f.read_text(encoding="utf-8").split("---\n", 2)[-1].strip()
        if len(corpo) < 200:
            vazios.append(f"{f.relative_to(WIKI)} ({len(corpo)} chars)")
    assert not vazios, "conceitos sem corpo substantivo: " + "; ".join(vazios)
