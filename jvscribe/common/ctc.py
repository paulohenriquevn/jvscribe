"""Colapso CTC greedy — implementação única para todas as pipelines (M9/T3.1).

Consolida o que estava replicado em `batch/batch_transcribe.py`, `batch/decode_onnx_local.py`,
`eval/measure_callcenter.py`, `eval/measure_realcodec.py` e `probes/tta_feature_align_probe.py`.

A consolidação só foi feita DEPOIS de medir a equivalência (`jvscribe/tests/test_ctc_equivalence.py`):
o laço de colapso é idêntico entre as cópias; o que divergia era a **detokenização** — quatro
usam `join + replace("▁", " ")` e `measure_realcodec` usa `sp.decode()`. Por isso as duas
convenções são funções distintas e nomeadas aqui, em vez de uma unificação cega que mudaria um
número já publicado.

Havia uma implementação Rust equivalente (`ctc_greedy` do runtime); ela saiu do repositório
em 2026-07-30 junto com o runtime. Não existe mais conformidade cross-language a verificar —
`jvscribe/tests/test_ctc_equivalence.py` compara este kernel contra uma referência escrita à
mão no próprio teste, e proíbe que as cópias voltem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

# O id do símbolo blank no vocabulário do modelo. Declaração ÚNICA: estava replicado em
# cinco arquivos, e é conhecimento do artefato — um vocabulário com outro blank id
# tornaria todas as cópias erradas de uma vez, em silêncio.
BLANK = 0
WORD_START = "▁"


def collapse(ids: Iterable[int], blank: int = BLANK) -> list[int]:
    """Remove blank e colapsa repetição adjacente — a regra canônica do CTC greedy.

    >>> collapse([0, 5, 5, 0, 5, 3, 3])
    [5, 5, 3]
    """
    out: list[int] = []
    prev = -1
    for i in ids:
        i = int(i)
        if i != prev and i != blank:
            out.append(i)
        prev = i
    return out


def greedy_ids(log_probs_row, valid_len: int | None = None, blank: int = BLANK) -> list[int]:
    """`(T, V)` → ids colapsados, usando só os `valid_len` frames válidos."""
    row = log_probs_row[:valid_len] if valid_len is not None else log_probs_row
    return collapse(row.argmax(-1), blank=blank)


def detok_pieces(ids: Sequence[int], id2tok: dict[int, str]) -> str:
    """Detokenização por concatenação de pieces — convenção de 4 das 5 cópias originais."""
    return "".join(id2tok.get(i, "") for i in ids).replace(WORD_START, " ").strip()


def greedy_text(log_probs_row, id2tok: dict[int, str], valid_len: int | None = None) -> str:
    """Atalho `(T,V) → texto` com a convenção `join + replace`."""
    return detok_pieces(greedy_ids(log_probs_row, valid_len), id2tok)


@dataclass(frozen=True)
class Palavra:
    """Uma palavra do decode e a confiança que o modelo teve ao emiti-la.

    `margem` é `log P(top-1) − log P(top-2)` em nats, reduzida ao **mínimo** entre os tokens da
    palavra: o elo mais fraco. `[MEDIDO]` sobre FLEURS pt_br (n=100): palavras corretas têm
    mediana 6,18 e as erradas 1,32 — a τ=1,0 o corte contém 49,8% dos erros sinalizando 10,3%
    das palavras, precisão 4,8× a taxa base.
    """

    texto: str
    margem: float


def greedy_palavras(
    log_probs_row,
    id2tok: dict[int, str],
    valid_len: int | None = None,
    blank: int = BLANK,
) -> list[Palavra]:
    """`(T,V)` → palavras com confiança, **sem tocar** no texto que `greedy_text` produz.

    A confiança sai de graça: o `argmax` já percorre o eixo do vocabulário, e o segundo colocado
    custa uma partição parcial no mesmo passo. Nenhum modelo extra, nenhuma memória extra.

    ⚠️ **A invariante que fecha o risco R4** (protocolo do portão de confiança)
    é verificável e está em `tests/test_ctc_palavras.py`::

        [p.texto for p in greedy_palavras(x)] == greedy_text(x).split()

    O plano previa `greedy_text` virar invólucro desta função. Foi **refutado na execução**: o
    vocabulário canônico tem o token id 7 == `'▁'`; emitido, ele vira espaço solto e
    `detok_pieces` produz `"a  b"` enquanto uma junção por palavras produziria `"a b"`. Comparar
    por `.split()` é exato nos dois casos, e `greedy_text` — com seus seis chamadores de
    produção — não é tocada.

    A margem de um token que dura vários frames é a do **primeiro** frame da emissão. É a regra
    com que os números do protocolo foram medidos; trocar por "máximo sobre o span" muda a
    distribuição e invalidaria as predições pré-registradas de E1/E2.
    """
    import numpy as np

    linha = np.asarray(log_probs_row[:valid_len] if valid_len is not None else log_probs_row)
    if linha.size == 0:
        return []

    ids = linha.argmax(-1)
    if linha.shape[-1] < 2:
        # Vocabulário degenerado: não há segundo colocado. Margem infinita é a leitura honesta
        # (nada compete), e não um IndexError no meio de uma corrida.
        margens = np.full(len(ids), np.inf)
    else:
        topo = np.partition(linha, -2, axis=-1)
        margens = topo[..., -1] - topo[..., -2]

    palavras: list[Palavra] = []
    pecas: list[str] = []
    ms: list[float] = []
    prev = -1

    def _fechar() -> None:
        if not pecas:
            return
        texto = detok_pieces_bruto(pecas)
        if texto:
            palavras.append(Palavra(texto, min(ms)))

    for t, tid in enumerate(ids):
        tid = int(tid)
        if tid == prev or tid == blank:
            prev = tid
            continue
        prev = tid
        peca = id2tok.get(tid, "")
        if peca.startswith(WORD_START) and pecas:
            _fechar()
            pecas, ms = [], []
        pecas.append(peca)
        ms.append(float(margens[t]))
    _fechar()
    return palavras


def detok_pieces_bruto(pecas: Sequence[str]) -> str:
    """Detokeniza um GRUPO de peças pela mesma convenção de `detok_pieces`.

    Existe para que a segmentação em palavras não reimplemente a regra de detokenização — a
    duplicação que este kernel foi criado para eliminar.
    """
    return "".join(pecas).replace(WORD_START, " ").strip()
