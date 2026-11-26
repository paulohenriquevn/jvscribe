"""Normalização de texto PT-BR — **um módulo, duas réguas nomeadas**.

Este projeto mede WER em seis lugares, e duas semânticas de normalização convivem por
necessidade real:

| função | acento | para quê |
|---|---|---|
| `normalize_for_wer_compare` | **remove** | régua de COMPARAÇÃO — todo WER publicado |
| `normalize_train_target`    | **preserva** | ALVO de treino — o modelo tem de aprender a acentuar |

Escolher a errada não levanta erro: produz um WER inflado e plausível. `[MEDIDO]` numa frase
em que só o acento difere, a régua de treino dá **62,5%** onde a de comparação dá **0%**.

## Por que um módulo só (consolidação de 2026-07-31)

O domínio esteve partido em `text.py` + `text_normalize_ptbr.py`, e o mesmo símbolo era
alcançável por dois caminhos de import — 12 arquivos via `text_normalize_ptbr`, 5 via `text`.
Isso não é estética: foi essa ambiguidade que permitiu ao defeito de régua sobreviver.
`eval_runtime_wer.py` importava de `text`, `measure_callcenter.py` de `text_normalize_ptbr`,
e ninguém enxergou que mediam com réguas diferentes.

Antes disso o problema era pior: **cinco** funções chamadas `normalize_ptbr` conviviam, com
duas semânticas opostas sob o mesmo nome. Os nomes atuais dizem o contrato; este módulo
garante que só exista um lugar onde procurá-los.

Determinístico: mesma entrada, mesma saída — o WER precisa ser reprodutível
(determinismo exigido pelos testes).

## Fora de escopo (YAGNI, deliberado)

Numerais por extenso ("150" ↔ "cento e cinquenta") NÃO são convertidos; os dígitos passam
inalterados. Deferido até haver evidência de erro de WER que o justifique.
"""
from __future__ import annotations

import re
import unicodedata

# Coloquialismos → forma canônica. Pequeno e explícito (KISS); cresce sob evidência de erro
# real, não por antecipação (YAGNI).
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

# Classe de caracteres do alvo de treino: preserva os acentos do PT-BR.
_TRAIN_KEEP = r"[^\w\sáàâãéêíóôõúçü]"


def _strip_accents(text: str) -> str:
    """Remove acentos via decomposição Unicode (á→a, ç→c). Determinístico."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_for_wer_compare(text: str) -> str:
    """Régua de COMPARAÇÃO de WER — **remove** acentos e expande coloquialismos.

    É a régua de todo número de acurácia publicado por este projeto. **Quem MEDE usa esta.**

    O `whisper.normalizers.EnglishTextNormalizer` dos peers não serve para PT-BR: é preciso
    tratar acento, "R$" e coloquialismo. Este é o componente próprio que o blueprint (EC-5)
    identificou como fronteira conhecida.

    Passos, em ordem fixa e determinística:
      1. caixa baixa
      2. símbolo monetário por extenso ("r$ 100" → "100 reais")
      3. remove pontuação (mantém espaço e dígito)
      4. remove acento
      5. expande coloquialismo token a token
      6. colapsa espaço

    >>> normalize_for_wer_compare("Pra pagar R$ 100, ligue já!")
    'para pagar 100 reais ligue ja'
    """
    text = text.lower().strip()

    for sym, word in _CURRENCY.items():
        # "r$ 100" ou "r$100" -> "100 reais"
        text = re.sub(re.escape(sym) + r"\s*(\d[\d.,]*)", r"\1 " + word, text)
        text = text.replace(sym, word)          # símbolo solto remanescente -> palavra

    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = _strip_accents(text)
    tokens = [_COLLOQUIAL.get(tok, tok) for tok in text.split()]
    return " ".join(tokens).strip()


def normalize_train_target(text: str) -> str:
    """ALVO de treino — **preserva** acentos. **Quem PREPARA CORPUS usa esta.**

    Fonte da verdade histórica: `jvscribe/finetune/prep_icefall.py`. Hoje esse é o único
    módulo do repositório que legitimamente a importa — `tests/test_regua_unica.py` mantém a
    lista fechada, porque estender a régua de treino a um módulo que MEDE já aconteceu e
    inflou o WER de runtime.

    >>> normalize_train_target("Coração, atenção!")
    'coração atenção'
    """
    text = unicodedata.normalize("NFC", (text or "").lower().strip())
    text = re.sub(_TRAIN_KEEP, " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def expandir_numeros(texto: str) -> str:
    """Converte dígitos em forma FALADA — a régua adicional, nunca a substituta.

    ⚠️ **Isto NÃO é uma melhoria de normalização. É o conserto de um defeito de medição.**

    `[MEDIDO]` 2026-07-31: 187 das 919 referências do FLEURS test contêm dígito **depois** de
    `normalize_for_wer_compare` (`na casa dos 20 anos`). O modelo foi treinado em fala e emite
    forma falada (`na casa dos vinte anos`). A régua canônica preserva o dígito e não faz ITN,
    então **conta o acerto como erro** — e a classe `número` marcava 99,0% de erro por artefato,
    carregando 12,4% de toda a massa de erro publicada.

    Custo do desalinhamento: **2,38 p.p.** do WER, IC95 pareado [1,97; 2,81].

    A direção da conversão é escolha técnica defensável, não arbitrária: o WER de ASR deve medir
    acurácia acústica e lexical, não formatação. Converter *falado → escrito* (ITN) é feature de
    produto, a jusante; converter a referência para falado mede o que o reconhecedor faz. Por isso
    a expansão se aplica aos **dois lados** — hipótese e referência — e nunca a um só.

    **E o CORAA não tem um dígito sequer** em 106.620 palavras `[MEDIDO]`. Consequência que
    invalida comparações já publicadas: os 15,99% do FLEURS e os 23,31% do CORAA **nunca foram
    comparáveis** — um estava inflado por artefato e o outro não.

    Convive com `normalize_for_wer_compare` em vez de substituí-la: a série histórica inteira foi
    medida com a régua antiga, e trocar a régua no meio do caminho é o defeito que este projeto já
    pagou três vezes. Publique as duas, lado a lado, sempre rotuladas.
    """
    from num2words import num2words

    def _falar(m: "re.Match[str]") -> str:
        try:
            return num2words(int(m.group()), lang="pt_BR")
        except (ValueError, NotImplementedError, OverflowError):
            # Número que a lib recusa: devolve como veio. `OverflowError` não é hipotético — a
            # Wikipédia tem inteiros de 20 dígitos e `num2words` recusa acima de 1e18; sem esta
            # captura o construtor do corpus morria. Devolver o token cru é a escolha certa:
            # apagá-lo falsearia o texto, e converter à força inventaria uma leitura.
            return m.group()

    # `normalize_for_wer_compare` já removeu pontuação, então só restam dígitos contíguos.
    return _RE_INTEIRO.sub(_falar, texto)


_RE_INTEIRO = re.compile(r"\d+")


# ---------------------------------------------------------------------------
# Régua PÚBLICA — a do Open ASR Leaderboard
# ---------------------------------------------------------------------------
#
# As duas réguas acima são deste projeto e servem a decisões internas. Nenhuma delas produz
# um número comparável com o que terceiros publicam: `normalize_for_wer_compare` remove
# acento e mantém dígito; o leaderboard faz o oposto nos dois eixos. A diferença entre as
# réguas internas já vale ~2 p.p. (14,83% contra 12,75% no mesmo áudio), então afirmar
# "batemos o modelo X" comparando régua interna contra número publicado compara coisas
# diferentes — o erro que `wiki/disciplina/` existe para impedir.
#
# Portada de `huggingface/open_asr_leaderboard` (Apache-2.0), `normalizer/normalizer.py`
# (`BasicMultilingualTextNormalizer`) e `normalizer/data_utils.py` (`MultilingualNormalizer`),
# lidos em 2026-09-14. O scoring multilíngue instancia o normalizador com
# `remove_diacritics=False` e chama com `lang=`, o que ATIVA a conversão de dígitos.

_RE_COLCHETE = re.compile(r"[<\[][^>\]]*[>\]]")
_RE_PARENTESE = re.compile(r"\(([^)]+?)\)")
_RE_MILHAR = re.compile(r"(\d)\s+(\d{3})\b")


def _remover_simbolos_mantendo_marcas(texto: str) -> str:
    """Troca símbolo e pontuação por espaço, preservando marcas combinantes (categoria 'M').

    Preservar 'M' é o que mantém o acento vivo quando o texto chega decomposto (NFD): em
    `combining acute` o acento é um caractere próprio, e removê-lo mudaria a régua de
    "com acento" para "sem acento" em silêncio, dependendo só de como o arquivo foi salvo.
    """
    return "".join(
        " " if unicodedata.category(c)[0] in "SP" else c
        for c in unicodedata.normalize("NFKC", texto)
    )


def normalize_for_leaderboard(text: str, lang: str = "pt") -> str:
    """Régua do Open ASR Leaderboard. **Quem COMPARA COM TERCEIROS usa esta.**

    Difere das duas réguas internas em dois eixos, e os dois importam:

    | | acento | dígito |
    |---|---|---|
    | `normalize_for_wer_compare` | removido | mantido como dígito |
    | `normalize_train_target` | preservado | mantido como dígito |
    | **esta** | **preservado** | **convertido para forma falada** |

    Ordem fixa: caixa baixa → remove `[...]` e `(...)` → símbolos viram espaço (marcas
    preservadas) → remove o que não é palavra nem espaço → colapsa espaço → junta grupos de
    milhar separados por espaço → dígitos viram palavras via `num2words`.

    ⚠️ NÃO trata símbolo monetário, ao contrário de `normalize_for_wer_compare`. "R$ 1.250"
    vira "r mil duzentos e cinquenta", com o "r" órfão. É fiel ao original — o objetivo aqui
    é reproduzir o número de terceiros, não produzir o número mais justo.

    `regex` e `num2words` são importados aqui dentro de propósito: `text.py` é a régua central
    e é importado por quase tudo, e nem todo consumidor precisa comparar com o leaderboard.

    >>> normalize_for_leaderboard("A fatura venceu no dia 15 de março.")
    'a fatura venceu no dia quinze de março'
    >>> normalize_for_leaderboard("Coração, atenção! [ruído] (aparte)")
    'coração atenção'
    """
    try:
        import regex as _regex
        from num2words import num2words as _num2words
    except ImportError as exc:  # pragma: no cover - ambiente sem as deps declaradas
        raise ImportError(
            "normalize_for_leaderboard exige `regex` e `num2words` "
            "(declarados em requirements-eval.txt). Instale-os antes de comparar com o "
            "Open ASR Leaderboard — sem eles o número não é o deles."
        ) from exc

    s = (text or "").lower()
    s = _RE_COLCHETE.sub("", s)
    s = _RE_PARENTESE.sub("", s)
    s = _remover_simbolos_mantendo_marcas(s).lower()
    s = _regex.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    s = _RE_MILHAR.sub(r"\1\2", s)

    def _falar_inteiro(m: "re.Match[str]") -> str:
        try:
            return _num2words(int(m.group()), lang=lang)
        except OverflowError:
            # `num2words` recusa acima de 10^15. Numa transcrição isso é lixo de ASR — uma
            # sequência longa de dígitos alucinada — e não um número que alguém falou. Deixar
            # o literal passar mantém o par referência/hipótese comparável; levantar aqui
            # derrubaria a avaliação inteira por causa de uma utterance defeituosa.
            # A captura é ESTREITA de propósito: qualquer outro erro é defeito e deve subir.
            return m.group()

    return _RE_INTEIRO.sub(_falar_inteiro, s)
