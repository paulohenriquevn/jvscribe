"""Nenhum `sys.path.insert` do pacote pode apontar para um diretório que não existe.

Uma entrada morta em `sys.path` **não levanta erro** — o Python simplesmente a ignora. Por
isso o defeito é silencioso: sob pytest o `jvscribe/conftest.py` cobre todas as pipelines e a
suíte fica verde, enquanto o mesmo script executado standalone quebra em
`ModuleNotFoundError`. Foi exatamente o que a reorganização de pastas produziu — `scripts/` e
`jvscribe/scripts/` deixaram de existir e 14 entradas continuaram apontando para elas, com
`jvscribe/probes/tta_feature_align_probe.py` e `blank_penalty_probe.py` quebrados no modo de
uso deles (linha de comando) sem que nenhum teste falhasse.

Guarda estrutural: varre a AST em vez do texto, e ordena os literais pela POSIÇÃO no código —
`ast.walk` é BFS e inverte `PKG / "jvscribe" / "common"` em `common/jvscribe`.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parent

# Argumentos de runtime: o caminho é montado a partir de algo que o usuário passa na linha de
# comando (um clone do icefall), então não tem como existir no repositório.
FRAGMENTOS_DE_RUNTIME = {"egs/commonvoice/ASR/zipformer"}


def _fragmentos_de_sys_path(arquivo: Path) -> list[tuple[int, str]]:
    """Extrai (linha, fragmento) de cada `sys.path.insert` — literais em ordem de código."""
    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    achados = []
    for no in ast.walk(arvore):
        if not (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "insert"
            and isinstance(no.func.value, ast.Attribute)
            and no.func.value.attr == "path"
        ):
            continue
        alvo = no.args[1] if len(no.args) > 1 else no
        literais = sorted(
            (x for x in ast.walk(alvo) if isinstance(x, ast.Constant) and isinstance(x.value, str)),
            key=lambda x: (x.lineno, x.col_offset),
        )
        fragmento = "/".join(x.value for x in literais)
        if fragmento:
            achados.append((no.lineno, fragmento))
    return achados


def _fontes():
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" not in f.parts:
            yield f


def test_nenhuma_entrada_de_sys_path_aponta_para_diretorio_inexistente():
    mortas = []
    for f in _fontes():
        for linha, frag in _fragmentos_de_sys_path(f):
            if frag in FRAGMENTOS_DE_RUNTIME:
                continue
            if frag.startswith("/"):
                existe = Path(frag).exists()
            else:
                existe = any((base / frag).exists() for base in (REPO, PKG, f.parent, f.parent.parent))
            if not existe:
                mortas.append(f"{f.relative_to(PKG)}:{linha} -> {frag!r}")
    assert not mortas, (
        "sys.path aponta para diretório inexistente (silencioso: o Python ignora, o script "
        "quebra só standalone):\n  " + "\n  ".join(mortas)
    )


def _entrypoints() -> list[str]:
    """Todo módulo com `if __name__ == "__main__"` — descoberto, não listado à mão.

    A primeira versão desta guarda enumerava os dois probes que eu já sabia quebrados. Ela
    passou verde enquanto `eval/baseline_fleurs_ptbr.py` — que produziu o baseline de M1 —
    quebrava standalone por uma entrada de path AUSENTE (não morta: ausente, o caso inverso,
    que nenhuma varredura de caminho inexistente encontra).
    """
    achados = []
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts or f.parent.name == "tests":
            continue
        if '__name__ == "__main__"' in f.read_text(encoding="utf-8", errors="replace"):
            achados.append(str(f.relative_to(PKG)))
    return achados


@pytest.mark.parametrize("script", _entrypoints())
def test_todo_entrypoint_importa_standalone_fora_do_pytest(script):
    """O `conftest.py` só roda sob pytest — estes scripts são executados na linha de comando.

    Um teste que os importe *dentro* da suíte herdaria o path do conftest e passaria mesmo com
    o path quebrado. Por isso o subprocesso: é o único jeito de reproduzir o modo de uso real.

    Só `ModuleNotFoundError` reprova. Faltar `--help`, exigir argumento, ou faltar uma
    dependência pesada não é defeito de fiação — é o script funcionando.
    """
    r = subprocess.run(
        [sys.executable, str(PKG / script), "--help"],
        capture_output=True, text=True, timeout=300, cwd=REPO,
    )
    faltando = [
        l for l in r.stderr.splitlines()
        if "ModuleNotFoundError" in l
        # dependências externas opcionais não são problema de fiação do repositório
        and not any(dep in l for dep in ("torch", "lhotse", "k2", "icefall", "sentencepiece",
                                          "onnxruntime", "jiwer", "faster_whisper", "datasets"))
    ]
    assert not faltando, f"{script} não importa standalone:\n  " + "\n  ".join(faltando)
