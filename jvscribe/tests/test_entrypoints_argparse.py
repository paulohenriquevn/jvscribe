"""Nenhum entrypoint lê `sys.argv` na mão — a interface é descoberta por `--help`.

Este defeito apareceu **três vezes** no repositório, e as três com o mesmo sintoma cruel:
pedir ajuda produzia um erro que não é sobre ajuda.

    $ python3 jvscribe/eval/baseline_minds14.py --help
    ValueError: invalid literal for int() with base 10: '--help'

De `int()` ninguém deduz que os argumentos eram `[n_utterances] [modelo]`, posicionais e
documentados só no docstring — que, nos dois baselines, ainda apontava para um caminho
(`scripts/`) e um arquivo de saída que não existem desde a reorganização. A interface real
não estava em lugar nenhum.

| onde | como falhava |
|---|---|
| `audit/tagarela_noise_audit.py` | parseava `sys.argv` em NÍVEL DE MÓDULO — importar já lia |
| `eval/baseline_fleurs_ptbr.py` | `int(sys.argv[1])` dentro do `main()` |
| `eval/baseline_minds14.py` | idem |

A guarda é estrutural (AST) e não por subprocess: `--help` em 37 entrypoints custaria minutos
de suíte, e o que importa é a causa — ler `sys.argv` direto — não o sintoma.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]


def _entrypoints() -> list[Path]:
    fora = []
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts or f.parent.name == "tests":
            continue
        if '__name__ == "__main__"' in f.read_text(encoding="utf-8", errors="replace"):
            fora.append(f)
    return fora


def test_ha_entrypoints_para_vigiar():
    """Se a descoberta zerar, os testes abaixo passam sem olhar nada."""
    assert len(_entrypoints()) >= 30


def test_nenhum_entrypoint_le_sys_argv_direto():
    culpados = []
    for f in _entrypoints():
        try:
            arvore = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for n in ast.walk(arvore):
            if (isinstance(n, ast.Attribute) and n.attr == "argv"
                    and isinstance(n.value, ast.Name) and n.value.id == "sys"):
                culpados.append(f"{f.relative_to(PKG)}:{n.lineno}")
    assert not culpados, (
        "entrypoint lê `sys.argv` direto — use `argparse`, senão `--help` não existe e a "
        "interface fica indescobrível:\n  " + "\n  ".join(sorted(set(culpados)))
    )


# Houve aqui uma segunda guarda — "entrypoint que menciona `--flag` tem de construir parser".
# Ela acusou `finetune/prep_phoneme_head.py`, e o achado era FALSO: as flags que ele contém
# (`--use-ctc`, `--phoneme-loss-scale`) são strings que o patcher INJETA no `train.py` do
# icefall; o script em si não recebe argumento nenhum.
#
# Não dá para distinguir por texto "flag que este script aceita" de "flag que este script
# escreve em outro arquivo" — a heurística olha estrutura onde precisaria de intenção. Guarda
# que acusa inocente é pior que guarda ausente: ensina a ignorar a falha. A regra acima
# (`sys.argv` direto) cobre as três ocorrências reais do defeito, e essa é verificável.
