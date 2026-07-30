"""Normalização de texto PT-BR — as duas semânticas, com nome que revela o contrato (M9/T3.2).

Cinco funções chamadas `normalize_ptbr` conviviam no repositório. Medido em 2026-07-30
(`training/tests/test_text_normalization.py`): são **2 semânticas distintas**, com 3 cópias
byte-idênticas de uma delas.

O problema não era a duplicação — era o **nome compartilhado por comportamentos opostos**.
Uma remove acento, a outra o preserva. Enquanto isso durasse, todo WER do projeto carregava
uma ambiguidade silenciosa sobre qual régua foi usada, e comparar dois números pressupunha
uma igualdade que ninguém tinha verificado.

Nomes agora dizem o contrato:
  `normalize_for_wer_compare` — remove acento; é a régua de COMPARAÇÃO
  `normalize_train_target`    — preserva acento; é o ALVO de treino
"""
from __future__ import annotations

import re
import unicodedata

# Classe de caracteres do alvo de treino: preserva os acentos do PT-BR.
_TRAIN_KEEP = r"[^\w\sáàâãéêíóôõúçü]"


def normalize_train_target(text: str) -> str:
    """Normalização do ALVO DE TREINO — **preserva** acentos.

    Fonte da verdade histórica: `training/finetune/prep_icefall.py:49`, replicada
    byte-a-byte em `training/tools/eval_runtime_wer.py:37` e
    `training/tools/analyze_error_composition.py:37`.
    """
    text = unicodedata.normalize("NFC", (text or "").lower().strip())
    text = re.sub(_TRAIN_KEEP, " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_wer_compare(text: str) -> str:
    """Normalização de COMPARAÇÃO DE WER — **remove** acentos, expande coloquialismos.

    Delega à implementação canônica em `training/common/text_normalize_ptbr.py`, que tem os passos
    em ordem fixa e determinística (caixa baixa → símbolo monetário → pontuação → acento →
    coloquialismos). Não é reimplementada aqui: uma segunda cópia recriaria exatamente o
    problema que esta task resolve.
    """
    from text_normalize_ptbr import normalize_for_wer_compare as _canonical

    return _canonical(text)
