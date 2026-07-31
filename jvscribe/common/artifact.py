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
import warnings
from pathlib import Path

# Ordem de fallback quando o model card está ausente ou ilegível. Nomes históricos incluídos
# para que artefatos antigos ainda resolvam.
NOMES_CONHECIDOS = ("model.int8.onnx", "m5_avg.int8.onnx")


VAR_MODEL_DIR = "JVSCRIBE_MODEL_DIR"
# ⚠️ O valor abaixo é o nome ANTIGO de propósito — uma varredura de renomeação já passou por
# aqui e o trocou pelo novo, fazendo as duas constantes apontarem para a mesma variável e a
# compatibilidade virar no-op em silêncio.
VAR_MODEL_DIR_OBSOLETA = "MACAW_MODEL_DIR"   # remover após 2026-12-31


def _dir_do_ambiente() -> str | None:
    """Lê a variável de ambiente, aceitando o nome antigo com `DeprecationWarning`.

    Renomear sem rede seria pior que o nome errado: quem tem a variável antiga exportada
    cairia em SILÊNCIO para `models/current` — o mesmo modo de falha que já entregou o modelo
    errado neste projeto. E compatibilidade silenciosa vira permanente, então ela avisa.

    Usa `warnings` em vez de um flag de módulo: a primeira versão guardava "já avisei" num
    global, e isso criou **dependência de ordem** entre testes — o segundo a rodar não via o
    aviso. O `warnings` deduplica sozinho, sem estado mutável nosso.
    """
    novo = os.environ.get(VAR_MODEL_DIR)
    if novo:
        return novo
    antigo = os.environ.get(VAR_MODEL_DIR_OBSOLETA)
    if antigo:
        warnings.warn(
            f"{VAR_MODEL_DIR_OBSOLETA} está obsoleta — o produto se chama jvscribe. "
            f"Use {VAR_MODEL_DIR}.",
            DeprecationWarning,
            stacklevel=3,
        )
    return antigo


def _dirs_candidatos() -> list[Path]:
    """`JVSCRIBE_MODEL_DIR` > `models/current` > diretório de trabalho."""
    dirs = []
    base = _dir_do_ambiente()
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


class ParVocabularioInvalido(RuntimeError):
    """O `tokens.txt` não é o do modelo — erro tipado (error-handling.md § 2).

    Merece um tipo próprio porque é o ÚNICO defeito deste projeto cuja saída é plausível: o
    ASR devolve português correto e errado ao mesmo tempo. Quem captura genericamente não
    distingue isto de um arquivo faltando, e é justamente a distinção que importa.
    """


def validar_par_modelo_vocabulario(
    diretorio: str | Path, tokens_path: str | Path | None = None
) -> bool:
    """Confere `tokens.txt` contra o `vocab_fingerprint` do `model_card.json`.

    `tokens_path` cobre o `--tokens` dos entrypoints: sem ele, validaríamos o tokens declarado
    no card enquanto o processo carrega OUTRO arquivo — aprovando exatamente o caso em que o
    erro é mais provável (alguém apontou o vocabulário à mão).

    Devolve `True` quando validou e conferiu, `False` quando não havia card para comparar
    (artefato legado — não inventa aprovação). Levanta `ParVocabularioInvalido` quando há card
    e o par NÃO confere.

    ⚠️ A comparação é por FINGERPRINT, nunca por contagem. `[MEDIDO]`: os dois artefatos deste
    projeto têm 500 tokens emitíveis cada e 492 dos 500 ids mapeiam tokens diferentes — a
    cardinalidade não os distingue. Ver `CLAUDE.md § O modelo`, fato 3.
    """
    d = Path(diretorio)
    card = d / "model_card.json"
    if not card.exists():
        return False   # legado: sem card não há autoridade a consultar
    try:
        dados = json.loads(card.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ParVocabularioInvalido(f"model_card.json ilegível em {d}: {e}") from e

    esperado = dados.get("vocab_fingerprint")
    if not esperado:
        raise ParVocabularioInvalido(
            f"{card} não declara `vocab_fingerprint` — regenere com "
            f"`python3 jvscribe/common/make_model_card.py {d}`. Sem ele não há como provar "
            f"que o tokens.txt é o deste modelo, e a saída de um par errado é PLAUSÍVEL."
        )

    tokens = Path(tokens_path) if tokens_path else d / dados.get("tokens_file", "tokens.txt")
    if not tokens.exists():
        raise ParVocabularioInvalido(f"tokens declarado no card não existe: {tokens}")

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from make_model_card import vocab_fingerprint   # Regra 9: já existe, não reimplementar

    obtido = vocab_fingerprint(tokens)
    if obtido != esperado:
        raise ParVocabularioInvalido(
            f"o vocabulário NÃO é o deste modelo.\n"
            f"  fingerprint esperado (model_card.json): {esperado}\n"
            f"  fingerprint obtido   ({tokens.name}): {obtido}\n"
            f"A contagem de tokens pode coincidir e ainda assim o par estar errado — foi o que "
            f"aconteceu neste projeto. Transcrever assim produz português plausível e errado."
        )
    return True
