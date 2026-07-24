"""Normalizador de texto PT-BR para cálculo de WER (M1 — T3.1).

O `whisper.normalizers.EnglishTextNormalizer` usado pelos peers
(`moonshine/scripts/eval-librispeech.py:60`) não serve para PT-BR: precisamos
tratar acentos, "R$" e coloquialismos ("pra"/"para"). Este é o componente PRÓPRIO
que o blueprint (EC-5) identificou como fronteira conhecida.

Escopo atual (review CV-4): caixa, moeda por extenso, remoção de pontuação/acentos
e coloquialismos. Conversão de **numerais por extenso** ("150" ↔ "cento e
cinquenta") NÃO está implementada — deferida (YAGNI) até haver evidência de erro
real de WER que a justifique; os dígitos passam inalterados.

Determinístico: a mesma entrada sempre produz a mesma saída, para que o WER seja
reprodutível (`.claude/rules/testing.md` § 6).

Uso como lib:
    from text_normalize_ptbr import normalize_ptbr
    normalize_ptbr("Pra pagar R$ 100, ligue já!")  # -> "para pagar 100 reais ligue ja"
"""

from __future__ import annotations

import re
import unicodedata

# Coloquialismos → forma canônica. Mantido pequeno e explícito (KISS); cresce sob
# evidência de erro real, não por antecipação (YAGNI).
_COLLOQUIAL = {
    "pra": "para",
    "pro": "para o",
    "pros": "para os",
    "pras": "para as",
    "vc": "voce",
    "tá": "esta",
    "ta": "esta",
    "cê": "voce",
}

# Símbolos monetários → por extenso (o WER compara palavras faladas).
_CURRENCY = {
    "r$": "reais",
    "us$": "dolares",
}


def _strip_accents(text: str) -> str:
    """Remove acentos via decomposição Unicode (á→a, ç→c). Determinístico."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_ptbr(text: str) -> str:
    """Normaliza texto PT-BR para comparação de WER.

    Passos (ordem fixa, determinística):
      1. caixa baixa
      2. símbolos monetários por extenso ("r$" -> "reais", posicionado após o número)
      3. remove pontuação (mantém espaços e dígitos)
      4. remove acentos
      5. expande coloquialismos token a token
      6. colapsa espaços
    """
    text = text.lower().strip()

    # 2. Moeda: "r$ 100" -> "100 reais". Captura o símbolo seguido de número.
    for sym, word in _CURRENCY.items():
        # "r$ 100" ou "r$100" -> "100 reais"
        pattern = re.escape(sym) + r"\s*(\d[\d.,]*)"
        text = re.sub(pattern, r"\1 " + word, text)
        # símbolo solto remanescente -> palavra
        text = text.replace(sym, word)

    # 3. Pontuação -> espaço (preserva letras, dígitos e espaços).
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)

    # 4. Acentos.
    text = _strip_accents(text)

    # 5. Coloquialismos token a token.
    tokens = text.split()
    tokens = [_COLLOQUIAL.get(tok, tok) for tok in tokens]

    # 6. Colapsa espaços.
    return " ".join(tokens).strip()
