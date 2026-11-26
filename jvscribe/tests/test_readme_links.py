"""T4.3 (M9) — todo link interno do README tem de resolver.

O README é a porta de entrada: é o primeiro arquivo que qualquer engenheiro abre. Medido em
2026-07-30: 5 de 5 links internos apontavam para arquivos removidos em `c7c67b9` — incluindo
a citação que sustentava o número central do projeto. Um README cuja tabela "Como navegar"
aponta 100% para o vazio destrói a confiança antes de o leitor chegar no código.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _internal_links(md: Path) -> list[str]:
    out = []
    for target in LINK.findall(md.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        out.append(target.split("#", 1)[0])
    return [t for t in out if t]


def test_todos_os_links_internos_do_readme_resolvem():
    quebrados = [t for t in _internal_links(REPO / "README.md") if not (REPO / t).exists()]
    assert not quebrados, "links quebrados no README: " + ", ".join(quebrados)
