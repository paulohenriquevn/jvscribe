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

import argparse
import datetime as _dt
import hashlib
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
            f"`python3 jvscribe/common/artifact.py {d}`. Sem ele não há como provar "
            f"que o tokens.txt é o deste modelo, e a saída de um par errado é PLAUSÍVEL."
        )

    tokens = Path(tokens_path) if tokens_path else d / dados.get("tokens_file", "tokens.txt")
    if not tokens.exists():
        raise ParVocabularioInvalido(f"tokens declarado no card não existe: {tokens}")

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


# ── o CARD: a declaração humana de proveniência do artefato ──────────────────────────
#
# Vinha de `make_model_card.py`. Os dois módulos eram um domínio só partido em dois: este
# arquivo RESOLVE qual artefato é o canônico, aquele DESCREVE o artefato — e `artifact` já
# importava `vocab_fingerprint` de lá para validar o par (modelo, vocabulário). Unificados
# em 2026-07-31.

MODEL_CARD_NAME = "model_card.json"
SCHEMA = "jvscribe-model-card/1"
# O schema mudou de NOME, não de formato — "jvscribe" era o nome antigo do produto. Cards já
# gerados (inclusive o publicado no HuggingFace) trazem o nome antigo, e recusá-los quebraria
# a leitura de um artefato válido.
SCHEMAS_ACEITOS = frozenset({SCHEMA, "jvscribe-model-card/1"})
DEFAULT_MODEL_FILE = "model.int8.onnx"
DEFAULT_TOKENS_FILE = "tokens.txt"


def _is_disambig(token: str) -> bool:
    """Símbolo de desambiguação do lexicon FST do icefall (`#0`, `#1`, …).

    Existe no `tokens.txt` para construir o `L.fst` e **nunca é emitido pelo modelo**.
    [MEDIDO] 2026-07-30: o export do runtime tem 2 deles (502 linhas / 500 classes); o de
    avaliação tem 3 (503 / 500). Contar linhas seria errado por construção.

    A regra veio do `Vocab::is_disambig` do runtime Rust (removido do repositório em
    2026-07-30); esta é hoje a única implementação.
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
        "schema": SCHEMA,
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


def main(argv: list[str] | None = None) -> int:
    """VERIFICA por padrão; escreve só com `--write`.

    O card guarda `model_sha256` e `vocab_fingerprint` para **detectar** peso trocado. Enquanto
    o CLI regravava por padrão, rodá-lo — a coisa natural a fazer, "deixa eu regenerar o card"
    — recomputava os dois a partir do que estivesse em disco e abençoava o peso novo: a
    ferramenta que existe para detectar adulteração a lavava quando invocada por reflexo.
    Escrever passa a exigir intenção; olhar deixa de ter efeito colateral.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact_dir", type=Path)
    ap.add_argument("--write", action="store_true",
                    help="regenera o model_card.json (padrão: apenas verifica)")
    ap.add_argument("--model-file", default=DEFAULT_MODEL_FILE)
    ap.add_argument("--tokens-file", default=DEFAULT_TOKENS_FILE)
    ap.add_argument("--wer", type=float, default=None)
    ap.add_argument("--wer-source", default=None)
    a = ap.parse_args(argv)

    card = build_card(
        a.artifact_dir,
        model_file=a.model_file,
        tokens_file=a.tokens_file,
        wer=a.wer,
        wer_source=a.wer_source,
    )
    resumo = (
        f"  vocab_real_len   : {card['vocab_real_len']}\n"
        f"  vocab_fingerprint: {card['vocab_fingerprint']}\n"
        f"  model_sha256     : {card['model_sha256'][:16]}…"
    )

    if a.write:
        print(f"escrito: {write_card(a.artifact_dir, card)}\n{resumo}")
        return 0

    atual_path = a.artifact_dir / MODEL_CARD_NAME
    if not atual_path.exists():
        print(f"card ausente: {atual_path}\n{resumo}\n"
              f"→ `--write` para criá-lo.")
        return 1
    atual = json.loads(atual_path.read_text(encoding="utf-8"))
    # `generated_at` muda a cada corrida por construção — compará-lo acusaria divergência
    # em todo card íntegro, e uma guarda que sempre acusa ensina a ignorá-la.
    divergentes = [
        k for k in ("model_sha256", "vocab_fingerprint", "vocab_real_len", "model_file")
        if atual.get(k) != card.get(k)
    ]
    if divergentes:
        print(f"DIVERGÊNCIA entre o artefato em disco e {MODEL_CARD_NAME}: {divergentes}")
        for k in divergentes:
            print(f"  {k}:\n    card={atual.get(k)}\n    disco={card.get(k)}")
        print("\nO card NÃO foi alterado. Se o peso mudou de propósito, regenere com `--write`;\n"
              "se não mudou, o artefato em disco não é o que a medição publicada usou.")
        return 1
    print(f"OK: {atual_path} confere com o artefato em disco\n{resumo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
