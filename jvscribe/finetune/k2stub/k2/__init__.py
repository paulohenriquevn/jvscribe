"""Stub de `k2` com **apenas** a ativação Swoosh — para o smoke de finetune rodar em CPU.

Por que existe: o `k2` instalado nesta máquina foi compilado contra PyTorch 1.13.1+cu117 e o
ambiente roda 2.13.0+cpu; importá-lo levanta `ImportError` de ABI. O `scaling.py` do icefall
importa `k2` **só** para as seis funções abaixo — nenhuma estrutura de grafo, nenhum FSA.

⚠️ As fórmulas NÃO foram escritas de memória. Foram extraídas do próprio `scaling.py`
(`SwooshL.forward` / `SwooshR.forward`, ramo `torch.jit.is_scripting()`), que carrega a
definição de referência em PyTorch puro para quando o TorchScript não pode chamar o k2:

    SwooshL(x) = logaddexp(0, x - 4.0) - 0.08·x - 0.035
    SwooshR(x) = logaddexp(0, x - 1.0) - 0.08·x - 0.313261687

Inventar a ativação produziria uma loss plausível e errada — a mesma classe do vocabulário
trocado. `tests/test_k2stub_swoosh.py` confere o stub contra o ramo JIT do icefall real quando
o clone está disponível, e contra valores fechados sempre.

Escopo: serve `construir_modelo()` do smoke (encoder_embed + encoder + cabeça CTC). NÃO serve
para treinar de verdade — a receita completa usa `k2.ctc_loss` e grafos, que não estão aqui.
"""
from __future__ import annotations

import torch
from torch import Tensor

_L_OFFSET, _L_CONST = 4.0, 0.035
_R_OFFSET, _R_CONST = 1.0, 0.313261687
_COEFF = 0.08


def _swoosh(x: Tensor, offset: float, const: float) -> Tensor:
    zero = torch.tensor(0.0, dtype=x.dtype, device=x.device)
    return torch.logaddexp(zero, x - offset) - _COEFF * x - const


def swoosh_l(x: Tensor) -> Tensor:
    return _swoosh(x, _L_OFFSET, _L_CONST)


def swoosh_r(x: Tensor) -> Tensor:
    return _swoosh(x, _R_OFFSET, _R_CONST)


# `*_forward` é o caminho sem gradiente no k2 real (kernel fundido). Aqui a distinção não
# existe: autograd do PyTorch cobre os dois. O nome é mantido porque `scaling.py` os indexa
# por string num dict — um nome faltando viraria KeyError no meio do backward.
swoosh_l_forward = swoosh_l
swoosh_r_forward = swoosh_r


def _forward_and_deriv(x: Tensor, offset: float, const: float) -> tuple[Tensor, Tensor]:
    """(y, dy/dx). A derivada é `sigmoid(x - offset) - 0.08` — derivada de logaddexp(0, u)."""
    y = _swoosh(x, offset, const)
    return y, torch.sigmoid(x - offset) - _COEFF


def swoosh_l_forward_and_deriv(x: Tensor) -> tuple[Tensor, Tensor]:
    return _forward_and_deriv(x, _L_OFFSET, _L_CONST)


def swoosh_r_forward_and_deriv(x: Tensor) -> tuple[Tensor, Tensor]:
    return _forward_and_deriv(x, _R_OFFSET, _R_CONST)


# ── Nomes que o icefall exige que EXISTAM, mas que este stub não implementa ────────────────
#
# `icefall/utils.py` faz `import k2` + `import k2.version` no topo e anota assinaturas com
# `k2.Fsa` / `k2.RaggedTensor` — anotações são avaliadas na definição da função, então os
# nomes precisam resolver mesmo que nada os chame.
#
# Eles resolvem para um marcador que LEVANTA ao ser usado. A alternativa — devolver algo
# inócuo — deixaria uma decodificação por grafo rodar sobre uma estrutura falsa e produzir
# hipóteses plausíveis e erradas, que é exatamente o que este projeto não aceita.
class _NaoImplementadoNoStub:
    """Marcador: o nome existe para o import/anotação resolver; usá-lo é erro."""

    def __init__(self, *a, **kw):
        raise NotImplementedError(
            "o stub de k2 implementa APENAS a ativação Swoosh (para o smoke de finetune em "
            "CPU). Grafos/FSA/SymbolTable exigem o k2 real — instale a build que casa com "
            "este PyTorch."
        )


def __getattr__(nome: str):
    """Qualquer nome de k2 que não seja Swoosh vira o marcador.

    Caçar os nomes um a um (`Fsa`, `RaggedTensor`, `SymbolTable`, …) era um jogo de
    tentativa-e-erro: cada import do icefall revelava o próximo, sempre como `AttributeError`
    numa ANOTAÇÃO de assinatura — avaliada na definição da função, mesmo que ninguém a chame.
    PEP 562 resolve todos de uma vez.

    O que NÃO muda: o nome resolve, mas construí-lo levanta. Devolver algo inócuo deixaria uma
    decodificação por grafo rodar sobre estrutura falsa e produzir hipóteses plausíveis e
    erradas — que é exatamente o que este projeto não aceita.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    return _NaoImplementadoNoStub
