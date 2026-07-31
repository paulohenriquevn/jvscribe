"""Detecta a topologia da CPU e recomenda afinidade e contagem de threads.

Existe por uma medição `[MEDIDO]` 2026-07-31 num i7 híbrido (2 P-cores a 5,0 GHz com
hyperthreading + 8 E-cores a 3,7 GHz):

| configuração     | mediana | IPC  | instruções |
|------------------|---------|------|------------|
| P-cores, intra=2 | 70,2 ms | 1,87 |     30,9 G |
| todos, intra=6   | 94,0 ms | 1,22 |     90,9 G |

**25% mais rápido usando 3× menos threads.** O cache miss é idêntico nos dois (~26%), então
não é limite de memória: seis threads executam **3× mais instruções para o mesmo trabalho**.
É spin-wait em barreira — e numa CPU híbrida cada barreira do matmul espera o E-core, 26%
mais lento em clock e de microarquitetura mais estreita.

A dispersão também cai: 67,8–72,5 ms fixado contra 74,4–99,1 ms espalhado. Isso importa mais
que a mediana, porque o RNF-02 é **p99**, não média.

Efeito colateral que é requisito: ocupar 2 dos 12 lógicos em vez de 6 deixa CPU para o
softphone, que o RNF-05 exige que esteja rodando durante a medição.

⚠️ **Este módulo só OBSERVA.** Fixar o processo nos P-cores foi tentado e revertido: isolado
dava 25% de ganho, mas no sistema real com dois canais o RTFx caiu de 4,60× para 2,33×.
`sched_setaffinity` **é herdado pelos filhos**, então os `parec` da captura passavam a
disputar os mesmos 2 P-cores com a inferência. No soak sem subprocessos a afinidade era
neutra (6,49× fixado vs 6,88× livre) — ganho zero e um modo de falha real.

O ganho está na CONTAGEM de threads, não na afinidade: `intra=2` dá RTFx 6,88× contra 4,95×
de `intra=6` e 3,94× de `intra=12`. Deixar o escalonador colocar 2 threads (ele já prefere
P-core quando há) e manter os demais núcleos livres para captura e segundo canal.

⚠️ Isto é uma **heurística de uma máquina**. O piso da frota BYOD é `[DESCONHECIDO]` (Q-01);
num CPU de 4 núcleos homogêneos a conta é outra. Por isso a detecção é dinâmica e a
recomendação sempre pode ser sobrescrita por flag.
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
