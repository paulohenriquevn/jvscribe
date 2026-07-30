#!/usr/bin/env python3
"""Gera o `model_card.json` de um diretório de artefato de modelo (M9/T1.3).

O card é a declaração humana de proveniência do artefato: qual modelo, qual vocabulário,
qual WER medido, quando. Ele **não** é a fonte da verdade para validação de dimensão — essa
vem do próprio grafo ONNX (ver `crates/macaw-asr/src/lib.rs`, `AsrEngine::output_vocab_dim`).

⛔ INVARIANTE: este script **nunca move, renomeia ou remove** arquivo algum. Ele só escreve
`model_card.json` no diretório informado. Modelo treinado é o artefato mais caro e menos
recuperável do projeto — horas de GPU paga sobre um corpus que pode não ser reproduzível.

Uso:
    python3 jvscribe/common/make_model_card.py <dir-do-artefato> [--wer 35.53 --wer-source arquivo.md]
    python3 jvscribe/common/make_model_card.py jvscribe/results/onnx
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from pathlib import Path

MODEL_CARD_NAME = "model_card.json"
DEFAULT_MODEL_FILE = "model.int8.onnx"
DEFAULT_TOKENS_FILE = "tokens.txt"


def _is_disambig(token: str) -> bool:
    """Símbolo de desambiguação do lexicon FST do icefall (`#0`, `#1`, …).

    Existe no `tokens.txt` para construir o `L.fst` e **nunca é emitido pelo modelo**.
    [MEDIDO] 2026-07-30: o export do runtime tem 2 deles (502 linhas / 500 classes); o de
    avaliação tem 3 (503 / 500). Contar linhas seria errado por construção.

    Espelha `Vocab::is_disambig` em `crates/macaw-asr/src/lib.rs`.
    """
    return len(token) > 1 and token[0] == "#" and token[1:].isdigit()


def _real_tokens(tokens_path: Path) -> list[tuple[int, str]]:
    """Devolve `[(id, token)]` dos tokens emitíveis, na ordem do arquivo.

    O id é o índice da linha (não o número na segunda coluna) — mesma convenção do
    `Vocab::load` em Rust, que indexa `tokens[id]` pela ordem de leitura.
    """
    out: list[tuple[int, str]] = []
    idx = 0
    for line in tokens_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        token = line.rsplit(" ", 1)[0] if " " in line else line
        if not _is_disambig(token):
            out.append((idx, token))
        idx += 1
    return out


def vocab_real_len(tokens_path: Path) -> int:
    """Nº de tokens emitíveis — a grandeza comparável com a dimensão de saída do modelo."""
    return len(_real_tokens(tokens_path))


def vocab_fingerprint(tokens_path: Path) -> str:
    """SHA-256 sobre `id\\ttoken\\n` dos tokens emitíveis — identidade, não cardinalidade.

    [MEDIDO] os dois artefatos em disco têm 500 tokens reais cada e 492 dos 500 ids mapeiam
    tokens diferentes. Cardinalidade não os distingue; este fingerprint sim.

    DEVE reproduzir bit a bit `Vocab::fingerprint()` do Rust — há teste de conformidade
    cross-language em `jvscribe/tests/test_make_model_card.py`.
    """
    h = hashlib.sha256()
    for idx, token in _real_tokens(tokens_path):
        h.update(str(idx).encode("utf-8"))
        h.update(b"\t")
        h.update(token.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 de um arquivo, em blocos (o modelo pode ter centenas de MB)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_card(
    artifact_dir: Path,
    *,
    model_file: str = DEFAULT_MODEL_FILE,
    tokens_file: str = DEFAULT_TOKENS_FILE,
    generated_at: str | None = None,
    wer: float | None = None,
    wer_source: str | None = None,
) -> dict:
    """Monta o card. Falha alto se um artefato obrigatório não existir."""
    model_path = artifact_dir / model_file
    tokens_path = artifact_dir / tokens_file
    if not model_path.exists():
        raise FileNotFoundError(f"modelo não encontrado: {model_path}")
    if not tokens_path.exists():
        raise FileNotFoundError(f"vocabulário não encontrado: {tokens_path}")

    card = {
        "schema": "macaw-model-card/1",
        "model_file": model_file,
        "model_sha256": file_sha256(model_path),
        "tokens_file": tokens_file,
        "vocab_real_len": vocab_real_len(tokens_path),
        "vocab_fingerprint": vocab_fingerprint(tokens_path),
        "generated_at": generated_at
        or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if wer is not None:
        card["wer_measured"] = wer
        card["wer_source"] = wer_source or "não declarado"
    return card


def write_card(artifact_dir: Path, card: dict) -> Path:
    """Escreve o `model_card.json`. Só cria/sobrescreve ESTE arquivo — nada mais é tocado."""
    out = artifact_dir / MODEL_CARD_NAME
    out.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact_dir", type=Path)
    ap.add_argument("--model-file", default=DEFAULT_MODEL_FILE)
    ap.add_argument("--tokens-file", default=DEFAULT_TOKENS_FILE)
    ap.add_argument("--wer", type=float, default=None)
    ap.add_argument("--wer-source", default=None)
    a = ap.parse_args()

    card = build_card(
        a.artifact_dir,
        model_file=a.model_file,
        tokens_file=a.tokens_file,
        wer=a.wer,
        wer_source=a.wer_source,
    )
    out = write_card(a.artifact_dir, card)
    print(f"escrito: {out}")
    print(f"  vocab_real_len   : {card['vocab_real_len']}")
    print(f"  vocab_fingerprint: {card['vocab_fingerprint']}")
    print(f"  model_sha256     : {card['model_sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
