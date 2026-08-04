"""Capacidade da máquina — o que esta CPU **tem** e o que **cabe** nela.

Duas perguntas de um domínio só, e sempre respondidas juntas (`bench/calibrate.py` usa as
duas na mesma tela):

| função | responde |
|---|---|
| `detectar` | quantos núcleos, quais são rápidos, quantas threads recomendar |
| `ocupacao` / `janela_maxima` | com N canais a cada hop, qual janela de decode ainda cabe |

Estavam em `cpu_topology.py` + `calibracao.py`. `calibracao.py` tinha 53 linhas e duas
funções de aritmética que só fazem sentido sobre o resultado de `detectar` — um fragmento,
não uma unidade. Unificados em 2026-07-31.

⚠️ **NÃO existe função de afinidade aqui, de propósito.** `sched_setaffinity` deu 25% isolado
e derrubou o RTFx ao vivo de 4,60× para 2,33× `[MEDIDO]`, porque é **herdada pelos processos
filhos** e os `parec` da captura passavam a disputar os mesmos P-cores. Há teste de regressão.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SYSFS_CPU = Path("/sys/devices/system/cpu")

# Abaixo desta razão entre a menor e a maior frequência, a diferença é boost por núcleo e não
# assimetria de microarquitetura. Sem esta tolerância, uma CPU homogênea com boost seria
# fatiada e sobraria 1 thread.
LIMIAR_HIBRIDA = 0.85


@dataclass
class Topologia:
    total: int
    cpus_rapidas: list[int]
    hibrida: bool
    mhz_max: int

    @property
    def threads_recomendadas(self) -> int:
        """Metade dos lógicos rápidos, no mínimo 1.

        A metade vem do hyperthreading: dois lógicos do mesmo núcleo físico disputam as mesmas
        unidades SIMD, então o segundo thread adiciona sincronização sem adicionar vazão.
        Medido: `intra=2` bateu `intra=4` nos mesmos 4 lógicos rápidos.
        """
        return max(1, len(self.cpus_rapidas) // 2)

    def afinidade_taskset(self) -> str:
        """Lista no formato do `taskset -c`, com faixas contíguas compactadas."""
        if not self.cpus_rapidas:
            return ""
        partes, ini, ant = [], self.cpus_rapidas[0], self.cpus_rapidas[0]
        for c in self.cpus_rapidas[1:] + [None]:
            if c is not None and c == ant + 1:
                ant = c
                continue
            partes.append(f"{ini}-{ant}" if ant > ini else f"{ini}")
            if c is not None:
                ini = ant = c
        return ",".join(partes)

    def como_dict(self) -> dict:
        """Condição da medição para o relatório — número sem contexto não vale nada."""
        return {
            "total": self.total,
            "hibrida": self.hibrida,
            "cpus_rapidas": self.cpus_rapidas,
            "threads_recomendadas": self.threads_recomendadas,
            "mhz_max": self.mhz_max,
            "afinidade": self.afinidade_taskset(),
        }


def _frequencias(base: Path) -> dict[int, int]:
    """`{cpu_id: kHz}` lidos do sysfs. Entradas ilegíveis são ignoradas, não fatais."""
    freqs: dict[int, int] = {}
    if not base.is_dir():
        return freqs
    for d in base.iterdir():
        if not (d.is_dir() and d.name.startswith("cpu") and d.name[3:].isdigit()):
            continue
        f = d / "cpufreq" / "cpuinfo_max_freq"
        try:
            freqs[int(d.name[3:])] = int(f.read_text().strip())
        except (OSError, ValueError):
            continue
    return freqs


def detectar(base: Path | str = SYSFS_CPU) -> Topologia:
    """Lê a topologia. Sem sysfs (container, macOS), degrada para a contagem de CPUs."""
    freqs = _frequencias(Path(base))
    if not freqs:
        n = os.cpu_count() or 1
        return Topologia(total=n, cpus_rapidas=list(range(n)), hibrida=False, mhz_max=0)

    pico = max(freqs.values())
    rapidas = sorted(c for c, k in freqs.items() if k / pico >= LIMIAR_HIBRIDA)
    return Topologia(
        total=len(freqs),
        cpus_rapidas=rapidas,
        hibrida=len(rapidas) < len(freqs),
        mhz_max=pico // 1000,
    )


# ── o que CABE nesta máquina ─────────────────────────────────────────────────────────

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


# ── Condição da máquina no momento da medição ───────────────────────────────────────────────
#
# `LIMIAR_LOAD` decide se uma medição deste projeto CONTA. Estava declarado em `stress_test`
# e em `live_transcribe`, e o `calibrate` comparava contra um `1.0` solto no meio de um `elif`
# — a mesma classe do `SR = 16000` em sete arquivos, no lugar mais caro possível: se as cópias
# divergirem, uma ferramenta declara a medição válida e a outra a declara indeterminada para o
# MESMO estado da máquina, e as duas publicam.
#
# O número vem de medição, não de gosto: a mesma configuração deu RTFx 3,51× / 2,90× / 2,82× /
# 2,50× com a máquina em load 3–4 `[MEDIDO]`.
LIMIAR_LOAD = 1.0


def carga_media() -> float | None:
    """Load average de 1 min, ou `None` quando a plataforma não expõe.

    Uma das cópias devolvia `-1.0` como sentinela de falha, e `-1.0` passa em `carga > 1.0`:
    numa plataforma sem `getloadavg` a ferramenta **nunca avisaria** sobre carga, e a ausência
    do aviso é indistinguível de "máquina ociosa". Valor mágico para sinalizar falha é o que
    `error-handling.md` § 2 proíbe — `None` obriga o chamador a decidir.
    """
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return None


def medicao_de_tempo_e_confiavel(carga: float | None = None) -> bool:
    """A máquina está ociosa o bastante para um número de tempo significar algo?

    `None` (load indisponível) devolve **False**: não saber não é o mesmo que estar ocioso, e
    tratar desconhecido como bom é como a sentinela `-1.0` enganava o chamador.
    """
    c = carga_media() if carga is None else carga
    return c is not None and c <= LIMIAR_LOAD


# ── Orçamento de estágios em série ────────────────────────────────────────────────────────
#
# Mora aqui porque é capacidade da MÁQUINA, não de um estágio específico: diarização, AEC,
# beam search e qualquer outra coisa que entre em série no pipeline pagam a mesma conta.
# Enquanto vivia em `diarizacao.py`, o segundo consumidor (AEC) teria de copiá-la — e é
# decisão de SEGURANÇA replicada, a mesma classe do `LIMIAR_LOAD` em três arquivos.

ALVO_RNF01 = 3.0
"""RTFx mínimo do pipeline completo de tempo real (RNF-01)."""


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


def rtfx_minimo_do_estagio(rtfx_asr: float, alvo: float = ALVO_RNF01) -> float | None:
    """Quão rápido um estágio adicional precisa ser para o pipeline ficar em `alvo`.

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
    rtfx_asr: float, rtfx_estagio: float, alvo: float = ALVO_RNF01
) -> tuple[bool, str]:
    """`(cabe, motivo)`. O motivo **nunca** é vazio, inclusive quando cabe.

    Uma recusa sem explicação vira uma flag que alguém remove por não entender o porquê.
    """
    minimo = rtfx_minimo_do_estagio(rtfx_asr, alvo)
    if minimo is None:
        return False, (
            f"o ASR sozinho entrega {rtfx_asr:.2f}×, que já não supera o alvo de {alvo:g}× — "
            "nenhum estágio cabe, nem um infinitamente rápido. O gargalo é o ASR."
        )
    combinado = rtfx_combinado(rtfx_asr, rtfx_estagio)
    if combinado < alvo:
        return False, (
            f"não cabe: ASR {rtfx_asr:.2f}× + estágio {rtfx_estagio:.2f}× = "
            f"{combinado:.2f}× (taxas somam pelo inverso), abaixo do alvo de {alvo:g}×. "
            f"O diarizador precisaria de {minimo:.1f}×."
        )
    return True, (
        f"cabe: ASR {rtfx_asr:.2f}× + estágio {rtfx_estagio:.2f}× = {combinado:.2f}× "
        f"≥ {alvo:g}× (mínimo exigido do estágio: {minimo:.1f}×)."
    )
