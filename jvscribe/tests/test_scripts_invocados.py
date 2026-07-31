"""Script invocado por `subprocess` tem de existir — e os dois shells de medição têm de rodar.

Complementa `test_sys_path_vivo.py`. Aquela guarda cobre `sys.path`; esta cobre a OUTRA porta
pela qual um caminho morre em silêncio: um caminho montado com `os.path.join` e entregue ao
`subprocess`. Foi por ela que `eval/baseline_fleurs_ptbr.py` — o módulo que produziu o baseline
de M1 — ficou quebrado apontando para `jvscribe/scripts/`, pasta extinta na reorganização.

O modo de falha é o mesmo dos probes: nada falha até alguém rodar de verdade.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parent


def _constantes_de_caminho_de_script(arquivo: Path) -> list[tuple[int, str]]:
    """Atribuições de módulo cujo valor é um `os.path.join(...)` terminando em `.sh`/`.py`."""
    achados = []
    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    except SyntaxError:
        return achados
    for no in arvore.body:
        if not isinstance(no, ast.Assign):
            continue
        chamada = no.value
        if not (isinstance(chamada, ast.Call) and isinstance(chamada.func, ast.Attribute)
                and chamada.func.attr == "join"):
            continue
        lits = [a.value for a in chamada.args
                if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if lits and lits[-1].endswith((".sh", ".py")):
            achados.append((no.lineno, "/".join(lits)))
    return achados


def test_todo_script_invocado_por_subprocess_existe():
    mortos = []
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        for linha, frag in _constantes_de_caminho_de_script(f):
            if not any((base / frag).exists() for base in (REPO, PKG, f.parent, f.parent.parent)):
                mortos.append(f"{f.relative_to(PKG)}:{linha} -> {frag!r}")
    assert not mortos, (
        "caminho de script montado e entregue ao subprocess não existe:\n  " + "\n  ".join(mortos)
    )


# ── As duas implementações da cadeia telefônica ──────────────────────────────────────────
#
# `corpus/telephone_augment.sh` (sox) e `corpus/telephone_channel.py` (audioop) implementam a
# MESMA degradação: 16k→8k, banda 300-3400, G.711 A-law round-trip. A duplicação é deliberada
# e documentada (o shell não arrasta numpy; o Python não arrasta sox/subprocess), mas até aqui
# NADA provava que as duas concordam — e o baseline de M1 saiu do shell enquanto todo o resto
# usa o Python. Duas réguas para o mesmo canal é o defeito que este repositório já pagou três
# vezes no texto; aqui seria no áudio.
#
# ⚠️ Comparar amostra a amostra dá correlação ≈ -0,06 e sugere divergência total. É ARMADILHA:
# os filtros têm atraso de grupo diferente (51 amostras / 6,38 ms `[MEDIDO]`). Alinhado, a
# correlação é 0,9978. Por isso a asserção alinha antes de comparar.
CORRELACAO_MINIMA = 0.99


def _tem_sox() -> bool:
    import shutil
    return shutil.which("sox") is not None


@pytest.mark.skipif(not _tem_sox(), reason="sox ausente — a cadeia em shell precisa dele")
def test_as_duas_cadeias_telefonicas_produzem_o_mesmo_canal():
    import numpy as np
    import soundfile as sf

    sys.path.insert(0, str(PKG / "corpus"))
    from telephone_channel import apply_telephone_channel

    sr = 16000
    t = np.arange(sr) / sr
    x = (0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 1800 * t)).astype(np.float32)

    with tempfile.TemporaryDirectory() as d:
        entrada, saida = f"{d}/in.wav", f"{d}/out.wav"
        sf.write(entrada, x, sr)
        r = subprocess.run(
            ["bash", str(PKG / "corpus" / "telephone_augment.sh"), entrada, saida],
            capture_output=True, text=True, timeout=120,
        )
        assert r.returncode == 0, f"cadeia em shell falhou: {r.stderr}"
        y_sh, sr_sh = sf.read(saida)

    y_py, sr_py = apply_telephone_channel(x, sr)
    assert sr_sh == sr_py == 8000, f"taxas divergem: shell={sr_sh} python={sr_py}"

    n = min(len(y_sh), len(y_py))
    a, b = y_sh[:n] - y_sh[:n].mean(), y_py[:n] - y_py[:n].mean()
    atraso = int(np.correlate(a, b, "full").argmax() - (n - 1))
    if atraso > 0:
        a, b = a[atraso:], b[: n - atraso]
    elif atraso < 0:
        a, b = a[:n + atraso], b[-atraso:]
    corr = float(np.corrcoef(a, b)[0, 1])
    assert corr >= CORRELACAO_MINIMA, (
        f"as duas cadeias telefônicas divergiram (correlação alinhada {corr:.4f}, "
        f"atraso {atraso} amostras) — o baseline de M1 usou o shell e o resto usa o Python"
    )
