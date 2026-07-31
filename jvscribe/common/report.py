"""Renderização de relatório de medição a partir de template.

Existe com dois consumidores em vez de esperar o terceiro (Regra de 3) porque o que se
compartilha aqui **não é estilo, é uma decisão de segurança**: `StrictUndefined`.

No default do Jinja, uma variável com nome errado renderiza **string vazia**. Num documento
de evidência isso é um número que desaparece sem ninguém notar — o mesmo modo de falha que
este projeto já pagou com o vocabulário trocado (produz saída plausível e errada, sem erro).

Replicar a construção do ambiente é replicar essa escolha, e escolha replicada diverge: basta
um consumidor omitir `StrictUndefined` para o modo silencioso voltar naquele relatório — e o
teste que guarda a invariante passaria mesmo assim, porque olharia o outro ambiente.
"""
from __future__ import annotations

from pathlib import Path

import jinja2


def ambiente(pasta: Path) -> jinja2.Environment:
    """Ambiente Jinja para relatórios em Markdown de `pasta`.

    `autoescape=False` é deliberado: o destino é Markdown, não HTML. Escapar transformaria
    `&`, `<` e aspas em entidades no meio da prosa dos caveats.
    """
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(pasta),
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
    )
