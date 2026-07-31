"""Nenhum módulo de produção pode capturar exceção larga demais.

`error-handling.md § 2`: "NUNCA engula exceções. Se não sabe tratar, deixe subir." Um
`except Exception` não silencia só o erro que você previu — silencia também o defeito de
programação que você não previu, e o programa segue com o comportamento errado.

Duas ocorrências reais deste repositório, ambas no caminho de DADOS, ambas invisíveis:

  `corpus/codec_pool.py`      qualquer defeito trocava o codec aplicado ao dado de treino
                              pelo fallback ffmpeg, em silêncio
  `finetune/prep_tagarela.py` `TypeError`/`ValueError` eram contados como "áudio corrompido"
                              e o item descartado do corpus de treino

Nos dois casos o efeito só apareceria como WER pior semanas depois, sem nada no log. Esta
guarda substitui a versão escopada por arquivo — a classe é do pacote inteiro.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
LARGAS = {"Exception", "BaseException"}

# Um `except` largo é aceitável quando o objetivo É reagir a qualquer falha e o handler NÃO
# esconde nada: relança, ou registra e encerra. Nenhum caso hoje; a lista existe para que a
# exceção futura venha com justificativa escrita, não com um silenciamento.
ISENTOS: dict[str, str] = {}


def _handlers_largos(arquivo: Path) -> list[tuple[int, str]]:
    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ExceptHandler):
            continue
        if no.type is None:
            achados.append((no.lineno, "except nu"))
        elif isinstance(no.type, ast.Name) and no.type.id in LARGAS:
            achados.append((no.lineno, f"except {no.type.id}"))
        elif isinstance(no.type, ast.Tuple) and any(
            isinstance(e, ast.Name) and e.id in LARGAS for e in no.type.elts
        ):
            achados.append((no.lineno, "except (…, Exception)"))
    return achados


def _producao():
    for d in ("common", "corpus", "finetune", "batch", "realtime", "eval", "tools"):
        for f in sorted((PKG / d).glob("*.py")):
            if f.name not in ISENTOS:
                yield f


def test_nenhum_modulo_de_producao_captura_excecao_larga():
    culpados = [
        f"{f.parent.name}/{f.name}:{linha} ({tipo})"
        for f in _producao()
        for linha, tipo in _handlers_largos(f)
    ]
    assert not culpados, (
        "captura larga demais — engole defeito de programação junto com a falha esperada:\n  "
        + "\n  ".join(culpados)
        + "\nEstreite ao erro real, ou declare em ISENTOS com a justificativa."
    )


def test_nenhum_handler_de_producao_e_um_pass_sem_alternativa():
    """`except X: pass` só é honesto quando há um valor de fallback EXPLÍCITO depois.

    `corpus/run_pipeline.py::_cpu_model` é o caso legítimo: captura `OSError` estreito e cai
    num `return "CPU desconhecida"` — sentinela visível, para um rótulo cosmético. O que a
    guarda proíbe é o `pass` que deixa o fluxo seguir como se nada tivesse falhado.
    """
    suspeitos = []
    for f in _producao():
        try:
            arvore = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for fn in ast.walk(arvore):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            tem_pass = any(
                isinstance(h, ast.ExceptHandler) and len(h.body) == 1
                and isinstance(h.body[0], ast.Pass)
                for h in ast.walk(fn)
            )
            if not tem_pass:
                continue
            # legítimo se a função termina devolvendo/levantando algo explícito
            ultimo = fn.body[-1] if fn.body else None
            if not isinstance(ultimo, (ast.Return, ast.Raise)):
                suspeitos.append(f"{f.parent.name}/{f.name}::{fn.name}")
    assert not suspeitos, (
        "`except: pass` sem fallback explícito no fim da função: " + ", ".join(suspeitos)
    )
