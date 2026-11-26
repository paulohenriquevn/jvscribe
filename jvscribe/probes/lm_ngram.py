"""E6 etapa 2b — n-grama com *stupid backoff*, para fusão rasa no beam de CTC.

## Por que existe código próprio aqui, e não uma biblioteca

A Regra 9 foi cumprida na ordem certa. `nltk.lm` **está instalado** (degrau 4 da escada) e foi a
primeira tentativa: `KneserNeyInterpolated(3)` sobre **10%** deste corpus **estourou 10 minutos de
build** e não terminou — extrapolado, mais de uma hora e memória incerta para os 5M de palavras.
`kenlm` não está instalado e exige compilar. Sobra a exceção explícita da Regra 9: *"a abstração é
tão fina que a dependência externa custa mais do que a implementação"*.

E ela é mesmo fina. *Stupid backoff* (Brants et al. 2007, `Large Language Models in Machine
Translation`) é literalmente contagem com desconto por nível:

    S(w | c) = count(c, w) / count(c)          se count(c, w) > 0
    S(w | c) = α · S(w | c[1:])                caso contrário,  α = 0,4

Não é probabilidade normalizada — a soma sobre o vocabulário não dá 1. **Para fusão rasa isso não
importa**: o beam compara hipóteses entre si, e uma constante multiplicativa comum não altera a
ordem. O artigo mostra que, com dado suficiente, a qualidade se aproxima de Kneser-Ney a uma fração
do custo. É a escolha padrão quando o corpus é grande e o orçamento é apertado — exatamente aqui.

## A decisão que mais importa: OOV recebe piso, nunca −∞

Uma palavra fora do vocabulário do LM tem de receber um score **finito e baixo**. Com −∞ o LM
poderia **eliminar** uma hipótese acústica plausível, deixando de ser um *prior* e virando um
*filtro* — e um filtro treinado em Wikipédia recusaria justamente os termos raros de call center
que mais importam para o produto (`rare_ref` é 31,9% do erro). Há teste guardando isto.
"""
from __future__ import annotations

import math
import pathlib
import pickle
from collections import Counter

ALPHA_BACKOFF = 0.4
"""Desconto por nível de recuo. 0,4 é o valor do artigo original, obtido empiricamente."""


class NgramLM:
    """N-grama com stupid backoff. `log_score(palavra, contexto)` é a única API que o beam usa."""

    def __init__(self, contagens: list[Counter], total_unigramas: int, ordem: int) -> None:
        self._c = contagens          # índice n → Counter de tuplas de tamanho n
        self._total = total_unigramas
        self.ordem = ordem
        # Piso de OOV: um pouco abaixo do unigrama mais raro possível (frequência 1). Assim uma
        # palavra desconhecida é penalizada, mas nunca eliminada.
        self._piso = math.log(0.5 / max(total_unigramas, 1))

    @classmethod
    def treinar(cls, sentencas, ordem: int = 3) -> "NgramLM":
        """`sentencas` é iterável de str OU de list[str] — aceita as duas formas de propósito.

        O corpus em disco é uma linha por sentença; os testes passam listas de tokens. Exigir uma
        forma só obrigaria o chamador a converter, e conversão silenciosa é onde nasce a diferença
        entre a régua do treino e a do uso.
        """
        c = [Counter() for _ in range(ordem + 1)]
        total = 0
        for s in sentencas:
            toks = s.split() if isinstance(s, str) else list(s)
            if not toks:
                continue
            total += len(toks)
            for n in range(1, ordem + 1):
                # `<s>` implícito: contextos no começo da sentença são mais curtos, e o backoff
                # os resolve. Padding explícito inflaria a contagem de um token que não existe
                # na saída do decoder.
                for i in range(len(toks) - n + 1):
                    c[n][tuple(toks[i:i + n])] += 1
        return cls(c, total, ordem)

    def log_score(self, palavra: str, contexto: tuple[str, ...]) -> float:
        """log S(palavra | contexto). Recua do contexto mais longo para o unigrama."""
        ctx = tuple(contexto)[-(self.ordem - 1):] if self.ordem > 1 else ()
        desconto = 0.0
        while True:
            n = len(ctx) + 1
            num = self._c[n].get(ctx + (palavra,), 0)
            if num:
                den = self._c[len(ctx)].get(ctx, 0) if ctx else self._total
                if den:
                    return desconto + math.log(num / den)
            if not ctx:
                break
            ctx = ctx[1:]
            desconto += math.log(ALPHA_BACKOFF)
        return desconto + self._piso

    def salvar(self, destino: pathlib.Path) -> pathlib.Path:
        destino = pathlib.Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("wb") as fh:
            pickle.dump({"c": self._c, "total": self._total, "ordem": self.ordem}, fh,
                        protocol=pickle.HIGHEST_PROTOCOL)
        return destino

    @classmethod
    def carregar(cls, origem: pathlib.Path) -> "NgramLM":
        with pathlib.Path(origem).open("rb") as fh:
            d = pickle.load(fh)
        return cls(d["c"], d["total"], d["ordem"])

    def __repr__(self) -> str:
        tamanhos = " · ".join(f"{n}-gr {len(self._c[n]):,}" for n in range(1, self.ordem + 1))
        return f"NgramLM(ordem={self.ordem}, {self._total:,} palavras, {tamanhos})"
