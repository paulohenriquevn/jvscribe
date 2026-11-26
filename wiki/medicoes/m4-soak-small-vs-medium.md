---
type: Medição
title: M4 — soak que decidiu o tamanho
description: Sob carga concorrente small e medium empatam em RTFx; empatado o RTFx, o desempate migra para acurácia.
tags: [medicao, m4, soak, adr-0003]
timestamp: 2026-07-31T00:00:00Z
---

# Soak RNF-04 + carga RNF-05: small vs medium — o tamanho por medição

> ⚠️ **Proveniência histórica.** Os caminhos e comandos citados abaixo são da árvore de
> diretórios vigente na data desta medição e **não resolvem no repositório atual**. Ficam
> preservados como registro de *como* o número foi produzido: reescrevê-los para os caminhos
> de hoje documentaria um comando que nunca foi executado.

**Data:** 2026-07-28 · **Máquina:** i7-1355U de referência (esta) · **Modelos:** Zipformer-CTC
small (22M) e medium (64M), int8, ambos SEM cabeça de fonema (decisão de TAMANHO isolada) ·
**Harness:** `soak_harness.py` (reusa `make_session` de `bench_rtfx.py`) · **Afinidade:**
`taskset -c 0,2` (2 P-cores físicos, sem self-contention de HT — RNF-06) · **Estressor RNF-05:**
`stressor.py` (carga multiproc numpy nos cores restantes — teto CPU/térmico/banda, **não Zoom real**).

Fecha a pendência que o ADR 0002 deixou explícita: a escolha small vs medium dependia de
soak/carga que **nunca tinham sido medidos** (o RTFx do ADR era clip único, offline).

## Método e a contaminação (honestidade)

Máquina **compartilhada** (várias sessões Claude + k3s) → as janelas "idle" tiveram contenção
externa (load1 chegou a 20-30). O harness grava **load1/temp por janela de 30s** como covariável;
filtro para **janelas limpas (load1 ≤ 6)** para isolar o RTFx real do modelo. A covariável provou
que a queda de RTFx nas "idle" era **contenção (load1↑), não throttle térmico** (temp estável
87-94°C). Runs sob estressor: load1 alto é o teste (não se filtra).

## Resultado `[MEDIDO]`

**Soak isolado (janelas limpas, load1 ≤ 6, áudio 10s, 2 P-cores):**

| Modelo | RTFx median (limpo) | RTFx min (limpo) | nº janelas limpas |
|---|---|---|---|
| small | **74,1×** | 56,2× | 14/19 |
| medium | **64,3×** | 60,4× | 7/19 |

→ small é apenas **1,15× mais rápido** que medium isolado (não 2×). Ambos **>> piso RNF-07 (6×)**.

**Sob carga concorrente pesada (estressor, load1 24-33 — RNF-05):**

| Modelo | RTFx median | RTFx min | ≥6×? |
|---|---|---|---|
| small | 11,0× | **7,1×** | ✅ |
| medium | 10,8× | **7,6×** | ✅ |

→ **EMPATE sob carga.** A vantagem de velocidade do small **evapora** quando a CPU está saturada
(o gargalo vira contenção, não o modelo). Ambos sustentam ≥6× com folga.

## Reconciliação: o RTFx do medium no ADR 0002 estava subestimado `[MEDIDO]`

O ADR 0002 citou medium **"17-38×"**. Bench independente `bench_rtfx.py` @ 2 threads (isolado),
mesmo protocolo da tabela do small na fase-5:

| Áudio | medium @ 2t | small @ 2t |
|---|---|---|
| 5s | 60,0× | 72,8× |
| 10s | 53,9× | 62,2× |
| 20s | 41,8× | 46,9× |
| 30s | 34,9× | 32,5× |

→ o medium real é **35-60×** @ 2 threads (e 64× sustentado na soak), **~2× acima** do "17-38×"
do ADR. Só o small teve tabela detalhada na fase-5; o número do medium foi rústico e
**enviesou a decisão para o small**. Ratio small/medium consistente ~1,15×.

## Conclusão (apenas o que a evidência sustenta)

**A evidência favorece o `medium` como finalista.** Na condição-ALVO (softphone concorrente =
carga, RNF-05), small e medium **empatam** em RTFx (~11× median, min ~7×, ambos ≥6×); isolado,
o medium perde só 1,15×. E o medium é **−1,11pp mais preciso** (WER 28,86% vs 29,97%). A margem
que justificava o small no ADR 0002 (a) só existe numa máquina ociosa (não o cenário de produção)
e (b) apoiava-se num RTFx de medium subestimado em ~2×.

**Limites honestos (§2 / §4):**
- **Frota (Q-01) não medida.** Esta é a máquina BOA. Numa máquina 2-3× mais fraca, o pior caso do
  medium (30s, ~35×) cai a ~12-17× — ainda >6×, mas com menos folga absoluta que o small.
  A resposta madura pode ser **tiering** (medium default, small fallback em CPUs fracas) — trabalho
  de `hardware-validation-engineer` quando o piso da frota for conhecido. Como **default único**,
  a evidência aponta medium.
- **Estressor ≠ Zoom real** (padrão de memória/IO difere) — é aproximação documentada, teto.
- **Máquina contaminada** por outras sessões durante os runs; mitigado pela covariável + filtro de
  janelas limpas, mas o nº de janelas limpas do medium (7/19) é menor que o ideal.
- **Cabeça de fonema não medida no medium** — a ablação (−4,63%) foi no small; deve transferir
  (cabeça auxiliar, RTFx-neutra), mas não medido no medium.
- Acurácia é **wideband FLEURS**; o gap 8 kHz de produção (M5) é maior e pode não escalar o 1,11pp.

## Reprodução

```bash
export ORT_DYLIB_PATH=$PWD/vendor/onnxruntime-linux-x64-1.23.0/lib/libonnxruntime.so
bash scratchpad/run_soaks.sh   # 4 soaks: small/medium × idle/carga, 10min cada
# análise: filtrar windows por load1<=6, median RTFx (ver seção Resultado)
taskset -c 0,2 python3 training/bench_rtfx.py training/results/onnx/medium.int8.onnx --threads 2
```
JSONs por janela: `training/results/soak-runs/{small,medium}-{idle,load}.json`.
