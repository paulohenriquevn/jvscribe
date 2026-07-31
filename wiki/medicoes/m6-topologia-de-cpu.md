---
type: Medição
title: Topologia de CPU e o limite do instrumento
description: CPU híbrida, spin-wait em barreira, e a constatação de que o harness não separa sob carga.
tags: [medicao, cpu, perf, m6]
timestamp: 2026-07-31T00:00:00Z
---

# M6 — topologia de CPU, afinidade e o limite do próprio instrumento `[MEDIDO]`

Data: 2026-07-31 · i7 híbrido (2 P-cores a 5,0 GHz com HT + 8 E-cores a 3,7 GHz, 12 lógicos)
· `perf_event_paranoid=1` liberado pelo dono, o que tornou possível ler contadores de hardware.

## Evidência 1 — a CPU é híbrida e isso importa

Lido do sysfs: `cpu0-3` a 5000 MHz, `cpu4-11` a 3700 MHz.

Benchmark **isolado** (uma inferência, janela de 6 s, round-robin entre configs, 5 repetições):

| configuração | mediana | dispersão |
|---|---|---|
| P-cores `0-3`, intra=2 | **70,2 ms** | 67,8–72,5 |
| P-cores `0-3`, intra=4 | 72,5 ms | 69,2–77,5 |
| todos, intra=6 (default de então) | 94,0 ms | 74,4–99,1 |
| E-cores `4-11`, intra=8 | 94,3 ms | 89,0–101,8 |
| todos, intra=12 | 93,5 ms | 72,8–104,4 |

## Evidência 2 — o mecanismo, via `perf`

| | P-cores intra=2 | todos intra=6 |
|---|---|---|
| tempo | **65,9 ms** | 81,2 ms |
| **IPC** | **1,87** | 1,22 |
| **instruções** | **30,9 G** | 90,9 G |
| cache miss | 26,9% | 25,4% |

O cache miss é **igual** nos dois — logo o workload **não é memory-bound**, como o IPC baixo
isolado sugeriria. Seis threads executam **3× mais instruções para o mesmo trabalho**: é
spin-wait em barreira. Numa CPU híbrida cada barreira do matmul espera o E-core, 26% mais
lento em clock e de microarquitetura mais estreita.

## Evidência 3 — a otimização isolada PIOROU o sistema

Aplicada a afinidade no app ao vivo, o RTFx caiu de **4,60× para 2,33×**.

Causa, verificada diretamente: **`sched_setaffinity` é herdado pelos processos filhos.**

```
afinidade do processo ANTES:      [0..11]
afinidade do processo DEPOIS:     [0, 1, 2, 3]
afinidade de um SUBPROCESSO filho: [0, 1, 2, 3]   ← o `parec` da captura herda
```

Os dois `parec` da captura passaram a disputar os mesmos 2 P-cores físicos com a inferência.
E no soak determinístico (sem subprocessos) a afinidade é **neutra**: 6,49× fixado contra
6,88× livre.

**Ganho zero e um modo de falha real → removida.** Coberto por
`test_o_modulo_nao_expoe_nada_que_mude_a_afinidade_do_processo`, que falha se alguém
reintroduzir qualquer função que mute afinidade de processo no módulo.

## Evidência 4 — o instrumento não separa o que eu queria comparar

Harness **ao vivo**, mesma configuração, quatro execuções: **3,51× · 2,90× · 2,82× · 2,50×**.
A dispersão para config idêntica é ~1,0× de RTFx.

Harness **determinístico** (`stress_test`, 2 canais, 3 repetições por config):

| intra | RTFx por repetição | mediana |
|---|---|---|
| 2 | 4,20 · 3,95 · 6,31 | 4,20 |
| 4 | 4,20 · 4,50 · 5,19 | 4,50 |
| 6 | 2,92 · 4,54 · 5,03 | 4,54 |

**As três são indistinguíveis.** A dispersão dentro de cada uma engole a diferença entre as
medianas. Com a máquina em load 3–4, nem o harness determinístico separa contagem de threads
no nível de sistema.

### O que decorre disso

O ganho de threads é `[MEDIDO]` **em inferência isolada**, com mecanismo confirmado por IPC e
contagem de instruções. No **nível de sistema** ele é `[DESCONHECIDO]` — não medido, não
refutado.

A escolha de `intra=2` como default fica, mas por um argumento que **não depende de
velocidade**: se as configurações são indistinguíveis em vazão, escolhe-se a que ocupa 2 dos
12 lógicos em vez de 6 — e o RNF-05 exige que um softphone esteja rodando junto.

## O defeito estrutural que estas medições expuseram

Este projeto declarou vencedor a partir de corrida única **três vezes**, e errou nas três:

| conclusão | o que era |
|---|---|
| "intra=8 é 30,9% melhor" | não reproduziu |
| 158,8 ms vs 169,1 ms | a **mesma** configuração — 35 ms de ruído |
| "afinidade nos P-cores é 25% melhor" | no sistema real piorou 46% |

O erro não é de quem mede — é de a ferramenta **permitir** declarar sem provar separação.

Criado `jvscribe/common/stats.py`: `comparar_pareado()` devolve `melhor=None` quando o IC95%
do delta cruza zero, e recusa amostras menores que 3. O `runtime_bench` passou a consumi-lo em
vez da própria cópia do bootstrap. 9 testes cobrem inclusive o caso "configurações idênticas
nunca produzem vencedor".

## Limitações

- **Máquina em load 3–4** durante tudo (navegador e agente rodando). É a causa direta da
  dispersão que impediu a separação. Um soak limpo exige a máquina ociosa.
- **`perf` só dá contadores por processo**; sem `-a` não há visão de contenção do sistema.
- Uma máquina, uma topologia. Num BYOD de 4 núcleos homogêneos a conta muda inteiramente — o
  módulo detecta dinamicamente por isso, mas o piso da frota segue `[DESCONHECIDO]` (Q-01).
- **RNF-04 e RNF-05 continuam não exercitados**: nenhuma corrida chegou a 30 min, nenhuma teve
  softphone ativo.

## Reprodução

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0,'jvscribe/common')
from cpu_topology import detectar; print(detectar().como_dict())
EOF

perf stat -e cycles,instructions,cache-references,cache-misses \
  taskset -c 0-3 python3 <carga> 15 2

python3 jvscribe/tools/stress_test.py --audio-dir <wavs> --minutos 1 --canais 2 --threads 2
```
