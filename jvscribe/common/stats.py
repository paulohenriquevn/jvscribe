"""Separação estatística de duas configurações medidas em rodadas pareadas.

Existe porque este projeto concluiu três vezes a partir de corrida única, e errou nas três:

| conclusão                              | o que era |
|----------------------------------------|-----------|
| "intra=8 é 30,9% melhor"               | não reproduziu |
| 158,8 ms vs 169,1 ms                   | a MESMA configuração — 35 ms de ruído |
| "afinidade nos P-cores é 25% melhor"   | no sistema real piorou 46% |

O erro não é de quem mede — é de a ferramenta deixar declarar vencedor sem provar separação.
Aqui o veredito é um objeto que carrega o intervalo junto, e `melhor` é `None` quando o IC
cruza zero.

**Por que pareado.** As configurações são medidas em round-robin, uma após a outra na mesma
rodada: a carga da máquina entra igual nas duas e some na diferença. Foi o que separou 15,99%
de 17,32% de WER quando a comparação não-pareada não separava, e o que mostrou que `intra=2`
e `intra=6` são indistinguíveis quando as medianas sugeriam o contrário.
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

MIN_AMOSTRAS = 3
BOOTSTRAP_N = 5000
SEED = 42


@dataclass
class Comparacao:
    delta_medio: float
    ic95: tuple[float, float]
    conclusivo: bool
    melhor: str | None
    n: int
    rotulo_a: str = "A"
    rotulo_b: str = "B"
    unidade: str = ""

    def resumo(self) -> str:
        lo, hi = self.ic95
        u = f" {self.unidade}" if self.unidade else ""
        base = (f"delta ({self.rotulo_b} − {self.rotulo_a}) = {self.delta_medio:+.3f}{u}  "
                f"IC95% [{lo:+.3f}, {hi:+.3f}]{u}  n={self.n}")
        if not self.conclusivo:
            return base + "  → INCONCLUSIVO: o IC cruza zero, a diferença pode ser ruído"
        return base + f"  → {self.melhor} é melhor (IC não cruza zero)"


def comparar_pareado(
    a: list[float],
    b: list[float],
    *,
    maior_e_melhor: bool = False,
    rotulo_a: str = "A",
    rotulo_b: str = "B",
    unidade: str = "",
    n_bootstrap: int = BOOTSTRAP_N,
    seed: int = SEED,
) -> Comparacao:
    """Compara `a` e `b` medidos nas MESMAS rodadas. `a[i]` e `b[i]` são a mesma condição.

    Devolve `melhor=None` quando o IC95% do delta cruza zero — é a recusa explícita a
    declarar vencedor sem separação.
    """
    if len(a) != len(b):
        raise ValueError(
            f"comparação pareada exige o mesmo tamanho: {len(a)} contra {len(b)}. "
            "Cada rodada tem de render um ponto de cada configuração."
        )
    if len(a) < MIN_AMOSTRAS:
        raise ValueError(
            f"{len(a)} amostras não sustentam intervalo (mínimo {MIN_AMOSTRAS}). "
            "Recusar é melhor que devolver um número que ninguém pode contestar."
        )

    pares = [y - x for x, y in zip(a, b)]
    media = statistics.mean(pares)

    rng = random.Random(seed)
    k = len(pares)
    medias = sorted(
        sum(pares[rng.randrange(k)] for _ in range(k)) / k for _ in range(n_bootstrap)
    )
    lo, hi = medias[int(0.025 * n_bootstrap)], medias[int(0.975 * n_bootstrap)]

    conclusivo = hi < 0 or lo > 0
    melhor = None
    if conclusivo:
        b_venceu = (media > 0) if maior_e_melhor else (media < 0)
        melhor = rotulo_b if b_venceu else rotulo_a

    return Comparacao(
        delta_medio=media, ic95=(lo, hi), conclusivo=conclusivo, melhor=melhor,
        n=k, rotulo_a=rotulo_a, rotulo_b=rotulo_b, unidade=unidade,
    )
