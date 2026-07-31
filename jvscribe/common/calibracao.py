"""Calibração do envelope operacional para a máquina-alvo.

A janela de 6 s **não é constante do produto**: é o resultado de medir este hardware. A de
10 s custava 262 ms de decode e, com 2 canais a cada 0,5 s, pedia 104,9% da CPU — saturava
por construção. Noutra CPU a conta é outra, e herdar a constante seria pior que não ter.

Aqui fica a parte **determinística**: dada a curva `janela → custo` medida na máquina, quantos
canais e qual hop, devolve a maior janela que cabe no orçamento de CPU.

**Maior é melhor**, não menor: mais janela dá mais contexto ao LocalAgreement-2 para confirmar
palavra. A busca é pelo teto que ainda cabe, não pelo mais rápido.

Quem mede a curva é `jvscribe/tools/calibrate.py`; quem a consome em produção é o
`live_transcribe`.
"""
from __future__ import annotations

# Fração da CPU que o decode pode ocupar. Acima disto não sobra para captura, extração de
# features e a carga concorrente que o RNF-05 exige (softphone). Medido: a 87,3% o backlog
# já cresce; a 104,9% satura por construção.
TETO_OCUPACAO = 0.80


def ocupacao(custo_ms: float, canais: int, hop_s: float) -> float:
    """Fração da CPU consumida só decodificando: `canais × custo ÷ hop`.

    Note que hop MENOR aumenta a ocupação — redecodifica a janela inteira mais vezes. É
    contra-intuitivo e foi medido: hop de 0,3 s deu RTFx 2,14× contra 3,66× de 0,6 s.
    """
    if hop_s <= 0:
        raise ValueError(f"hop tem de ser positivo, veio {hop_s}")
    return canais * (custo_ms / 1000.0) / hop_s


def janela_maxima(
    curva: dict[float, float],
    canais: int,
    hop_s: float,
    teto: float = TETO_OCUPACAO,
) -> float | None:
    """Maior janela cujo custo cabe no `teto`. `None` quando nenhuma cabe.

    Devolver `None` é deliberado: se a máquina não aguenta nem a menor janela, entregar a
    menor mesmo assim esconderia que ela não serve para o caso de uso, e o operador seguiria
    achando que está tudo bem.
    """
    if not curva:
        raise ValueError("curva vazia — sem medição na máquina-alvo não há calibração")
    if not 0 < teto <= 1:
        raise ValueError(f"teto tem de ficar em (0, 1], veio {teto}")

    cabem = [j for j, custo in curva.items() if ocupacao(custo, canais, hop_s) <= teto]
    return max(cabem) if cabem else None
