"""Resolução do artefato de modelo canônico — um resolvedor para todos os entrypoints.

Existe porque cada script resolvia o modelo por conta própria com um default literal, e
defaults duplicados divergem. Em 2026-07-30 o artefato foi renomeado para o padrão SOTA:
`batch_transcribe.py` continuou funcionando (lia o model card) e `mic_transcribe.py` quebrou
(tinha `m5_avg.int8.onnx` fixo no código).

⚠️ O `model_card.json` é a AUTORIDADE sobre qual peso é o canônico — nunca o nome do arquivo.
Dois pesos deste projeto coabitaram o mesmo diretório com WER 15,99% e 17,32%; escolher pela
ordem alfabética entregava o pior em silêncio, sem erro algum.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Ordem de fallback quando o model card está ausente ou ilegível. Nomes históricos incluídos
# para que artefatos antigos ainda resolvam.
NOMES_CONHECIDOS = ("model.int8.onnx", "m5_avg.int8.onnx")


def _dirs_candidatos() -> list[Path]:
    """`MACAW_MODEL_DIR` > `models/current` > diretório de trabalho."""
    dirs = []
    base = os.environ.get("MACAW_MODEL_DIR")
    if base:
        dirs.append(Path(base))
    repo = Path(__file__).resolve().parents[2]
    dirs += [repo / "models" / "current", Path.cwd()]
    return dirs


def _model_file_do_card(d: Path) -> str | None:
    """Lê `model_file` do model card. Card ausente/ilegível devolve None (degrada, não quebra)."""
    card = d / "model_card.json"
    if not card.exists():
        return None
    try:
        return json.loads(card.read_text(encoding="utf-8")).get("model_file")
    except (json.JSONDecodeError, OSError):
        return None


def default_model_path() -> str:
    """Caminho do modelo canônico. Devolve nome relativo quando nada resolve (comportamento legado)."""
    for d in _dirs_candidatos():
        declarado = _model_file_do_card(d)
        if declarado and (d / declarado).exists():
            return str(d / declarado)
        for nome in NOMES_CONHECIDOS:
            if (d / nome).exists():
                return str(d / nome)
    return NOMES_CONHECIDOS[0]


def default_sibling(nome: str) -> str:
    """Arquivo irmão do modelo canônico (ex.: `tokens.txt`), ou o nome cru se não existir."""
    irmao = Path(default_model_path()).parent / nome
    return str(irmao) if irmao.exists() else nome
