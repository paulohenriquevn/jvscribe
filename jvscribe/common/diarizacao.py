"""Diarização opcional — e o orçamento que decide se ela cabe.

**O padrão continua sendo não ter diarização.** No caso 1:1 — o dominante — o microfone **é** o
atendente e o loopback **é** o cliente, por construção da captura: custo zero, acurácia 100%
(`CLAUDE.md`). Este módulo não revoga esse desenho; ele destrava os casos que a captura por canal
genuinamente não resolve:

| caso | onde o canal falha |
|---|---|
| escritório aberto | o mic pega o atendente da baia ao lado |
| supervisor entra na ligação | três falantes, dois canais (é o M7 do `ROADMAP.md`) |
| duas pessoas do lado do cliente | o loopback carrega duas vozes |

⚠️ **O orçamento é aritmético e não é intuitivo.** Taxas somam pelo **inverso** (`PRD.md` § 6,
racional do RNF-07): um ASR a 3× somado a uma diarização a 3× dá **1,5×**, não 3×. Com o RTFx ao
vivo medido em 2026-07-31 — **3,58×** — um diarizador precisaria rodar a **18,5×** para o pipeline
ficar em ≥3×.

Por isso a opção **confere a conta antes de ligar**. Habilitar diarização sem verificar o
orçamento repetiria um erro que este projeto já catalogou: benchmark de componente que não
transfere para o sistema (`asr-evidence-discipline.md` § 4 — a afinidade de CPU deu 25% melhor
isolada e 46% pior no pipeline com os subprocessos de captura).

## Estado dos candidatos `[LITERATURA]`

Nenhum implementador real vive aqui ainda, e é deliberado: a lição de E4 do protocolo é **medir o
custo antes da capacidade**. Os candidatos levantados em 2026-07-31, com os números que se
conseguiu verificar:

| candidato | params | nota |
|---|---|---|
| `sherpa-onnx` (k2-fsa) | — | **mesma organização do icefall** que produziu nosso modelo; roda em ONNX Runtime, que já é o nosso runtime; tem `int8`. Melhor ponto de partida |
| ERes2NetV2 (3D-Speaker) | **17,8M · 12,6 GFLOPs** | verificado em `arXiv:2406.02167`. Pesado para o orçamento |
| CAM++ (3D-Speaker) | ~7M | a variante leve da mesma família; ONNX publicado |
| `pyannote.audio` | — | padrão de facto; segmentação + embedding + clustering, e modelos com acesso restrito |

**Embedding de locutor é largamente independente de língua** — modela característica de voz, não
fonema. "Eficiente para PT-BR" é, na prática, "eficiente"; o que muda por língua é a avaliação,
não o modelo.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

ALVO_RNF01 = 3.0
"""RTFx mínimo do pipeline completo de tempo real (`PRD.md` § 6, RNF-01)."""


def rtfx_combinado(*taxas: float) -> float:
    """RTFx de estágios em série. **Taxas somam pelo inverso.**

    O erro intuitivo é somar ou tomar o mínimo. Dois estágios a 3× dão **1,5×**: cada segundo de
    áudio custa 1/3 s em cada um, e os custos é que somam.
    """
    if not taxas:
        raise ValueError("nenhuma taxa informada")
    if any(t <= 0 for t in taxas):
        raise ValueError(f"toda taxa tem de ser positiva; veio {taxas}")
    return 1.0 / sum(1.0 / t for t in taxas)


def rtfx_minimo_do_diarizador(rtfx_asr: float, alvo: float = ALVO_RNF01) -> float | None:
    """Quão rápido o diarizador precisa ser para o pipeline ficar em `alvo`.

    `None` quando o ASR **sozinho** já está no alvo ou abaixo: aí não existe diarizador rápido o
    bastante, nem um infinitamente rápido. Devolver um número grande sugeriria que basta otimizar
    o diarizador; `None` diz a verdade — o problema é o ASR.
    """
    if rtfx_asr <= 0 or alvo <= 0:
        raise ValueError("taxas têm de ser positivas")
    if rtfx_asr <= alvo:
        return None
    return 1.0 / (1.0 / alvo - 1.0 / rtfx_asr)


def cabe_no_orcamento(
    rtfx_asr: float, rtfx_diarizador: float, alvo: float = ALVO_RNF01
) -> tuple[bool, str]:
    """`(cabe, motivo)`. O motivo **nunca** é vazio, inclusive quando cabe.

    Uma recusa sem explicação vira uma flag que alguém remove por não entender o porquê.
    """
    minimo = rtfx_minimo_do_diarizador(rtfx_asr, alvo)
    if minimo is None:
        return False, (
            f"o ASR sozinho entrega {rtfx_asr:.2f}×, que já não supera o alvo de {alvo:g}× — "
            "nenhum diarizador cabe, nem um infinitamente rápido. O gargalo é o ASR."
        )
    combinado = rtfx_combinado(rtfx_asr, rtfx_diarizador)
    if combinado < alvo:
        return False, (
            f"não cabe: ASR {rtfx_asr:.2f}× + diarizador {rtfx_diarizador:.2f}× = "
            f"{combinado:.2f}× (taxas somam pelo inverso), abaixo do alvo de {alvo:g}×. "
            f"O diarizador precisaria de {minimo:.1f}×."
        )
    return True, (
        f"cabe: ASR {rtfx_asr:.2f}× + diarizador {rtfx_diarizador:.2f}× = {combinado:.2f}× "
        f"≥ {alvo:g}× (mínimo exigido do diarizador: {minimo:.1f}×)."
    )


@runtime_checkable
class Diarizador(Protocol):
    """O que o pipeline de tempo real precisa saber sobre quem fala.

    Interface do **domínio**, não da biblioteca (DIP): o motor pede um rótulo para um trecho de
    áudio e não conhece embedding, clustering nem ONNX. Trocar de implementação não toca no
    `live_transcribe`.
    """

    rtfx: float
    """RTFx **medido** desta implementação. Entra na conta de `cabe_no_orcamento`."""

    def rotular(self, audio, sr: int) -> str:
        """Quem falou neste trecho."""
        ...


class SemDiarizacao:
    """O padrão: o canal **é** o falante. Zero custo, acurácia 100% no caso 1:1.

    Não é um stub nem um placeholder — é a implementação **correta** para o caso dominante, e a
    razão de a diarização ser opcional em vez de obrigatória.
    """

    rtfx = float("inf")
    """Nada é processado, então nada é gasto. A conta do orçamento tem de refletir isso."""

    def __init__(self, rotulo: str) -> None:
        self._rotulo = rotulo

    def rotular(self, audio, sr: int) -> str:  # noqa: ARG002 — a assinatura é do contrato
        return self._rotulo

    def __repr__(self) -> str:
        return f"SemDiarizacao({self._rotulo!r})"
