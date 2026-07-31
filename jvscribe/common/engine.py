"""Carregar o motor de inferência — **uma sequência, um lugar**.

Todo entrypoint que transcreve faz os mesmos cinco passos, nesta ordem:

    resolver o modelo → resolver o tokens → VALIDAR o par → criar a sessão → carregar o vocab

Estava replicado em **treze** entrypoints, cada um com uma variação. E a consequência não foi
estética: o passo de VALIDAÇÃO existia em apenas 4 dos 13. Os outros nove carregavam um par
(modelo, vocabulário) sem conferir se eles combinam — exatamente o defeito que a validação foi
escrita para impedir, sobrevivendo porque a sequência estava fragmentada.

`CLAUDE.md § O modelo`, fato 3: os dois artefatos deste projeto têm 500 tokens emitíveis cada e
**492 dos 500 ids mapeiam tokens diferentes**. Trocar o `tokens.txt` produz português plausível
e errado, sem erro nenhum. Por isso o passo não pode ser opcional nem depender de alguém
lembrar.

## Uso

```python
from engine import Motor, argumentos_de_modelo

ap = argparse.ArgumentParser()
argumentos_de_modelo(ap)              # --model / --tokens / --threads, com os defaults certos
a = ap.parse_args()
motor = Motor.carregar(a.model, a.tokens, a.threads)
lp, _ = motor.sessao.run(...)
texto = ctc.greedy_text(lp[0], motor.id2tok)
```

Quem precisa só de parte da sequência (`bench/runtime_bench.py` monta sessões próprias, porque
a configuração de sessão **é** a variável sob teste) usa `Motor.validar_par` sozinho — o que
não se admite é pular a validação.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from artifact import default_model_path, default_sibling, validar_par_modelo_vocabulario
from onnx_session import criar_sessao

TOKENS_PADRAO = "tokens.txt"


def argumentos_de_modelo(ap: argparse.ArgumentParser, *, threads: bool = True) -> None:
    """Adiciona `--model`, `--tokens` e `--threads` com os defaults canônicos.

    Os três eram declarados à mão em 8 entrypoints. Declarar aqui garante que o default de
    `--model` seja SEMPRE o resolvedor de artefato — e não um nome de arquivo literal, que já
    entregou o modelo de 17,32% em vez do de 15,99%, em silêncio.
    """
    ap.add_argument("--model", default=None,
                    help="default: o artefato canônico declarado no model_card.json")
    ap.add_argument("--tokens", default=None, help=f"default: {TOKENS_PADRAO} ao lado do modelo")
    if threads:
        ap.add_argument("--threads", type=int, default=None,
                        help="default: derivado da topologia da CPU")


def resolver(model: str | None, tokens: str | None) -> tuple[Path, Path]:
    """(modelo, tokens) resolvidos e **validados como par**.

    Levanta `ParVocabularioInvalido` quando o vocabulário não é o do modelo. Falhar aqui é o
    ponto: a alternativa é transcrever português plausível e errado.
    """
    modelo = Path(model or default_model_path())
    vocab = Path(tokens or default_sibling(TOKENS_PADRAO))
    validar_par_modelo_vocabulario(modelo.parent, tokens_path=vocab)
    return modelo, vocab


def carregar_tokens(path: str | Path) -> dict[int, str]:
    """`{id: token}` de um `tokens.txt` do icefall (`<token> <id>` por linha)."""
    d: dict[int, str] = {}
    for linha in Path(path).read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 2:
            d[int(partes[1])] = partes[0]
    if not d:
        raise ValueError(f"vocabulário vazio: {path} — formato esperado `<token> <id>` por linha")
    return d


@dataclass(frozen=True)
class Motor:
    """Sessão ONNX + vocabulário, com o par já validado."""

    sessao: object
    id2tok: dict[int, str]
    modelo: Path
    tokens: Path

    @classmethod
    def carregar(
        cls,
        model: str | None = None,
        tokens: str | None = None,
        threads: int | None = None,
        *,
        memoria_restrita: bool = False,
    ) -> Motor:
        """A sequência completa. É o caminho por default de quem transcreve."""
        modelo, vocab = resolver(model, tokens)
        return cls(
            sessao=criar_sessao(str(modelo), threads, memoria_restrita=memoria_restrita),
            id2tok=carregar_tokens(vocab),
            modelo=modelo,
            tokens=vocab,
        )
