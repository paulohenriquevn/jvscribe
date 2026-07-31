---
type: Runbook
title: Calibração — o que muda ao trocar de CPU
description: Correções algorítmicas são portáveis; contagem de threads e janela de decode não são.
resource: jvscribe/bench/calibrate.py
tags: [calibracao, cpu, portabilidade, runbook]
timestamp: 2026-07-31T00:00:00Z
---

# Calibração ao trocar de CPU

## O que é portável e o que precisa ser remedido

| otimização | portável? | por quê |
|---|---|---|
| [fbank incremental](fbank-incremental.md) | **sempre** | elimina trabalho redundante |
| dreno do `read()` da captura | **sempre** | era defeito de encanamento |
| teto do estado do motor | **sempre** | era estado sem limite |
| backpressure | **sempre** | propriedade de sistema de tempo real |
| arena de memória + `inter_op` | provavelmente | config de runtime, não de hardware |
| **`intra_op_num_threads`** | **não** | sai da topologia (P-cores vs E-cores) |
| **janela de decode** | **não** | sai da ocupação de CPU medida |

## Procedimento

1. **Máquina ociosa.** Não é formalidade: a mesma configuração deu RTFx 3,51× / 2,90× / 2,82× /
   2,50× com a máquina em load 3–4.
2. Conferir a topologia detectada (`cpu_topology.detectar()`).
3. `calibrate.py` — mede a curva `janela → custo`, calcula a ocupação com N canais, emite a
   maior janela que cabe. **Maior é melhor**: mais contexto para o LocalAgreement-2 confirmar.
4. `runtime_bench.py` — confirma os parâmetros de sessão com bootstrap pareado.
5. `stress_test.py --minutos 30` — valida sob carga sustentada (RNF-04); com softphone ativo,
   cobre também o RNF-05.

## Referência desta máquina

i7 híbrido, 2 P-cores a 5,0 GHz + 8 E-cores a 3,7 GHz, `intra=2` + arena ligada:

| janela | custo | ocupação com 2 canais @ 0,5 s |
|---|---|---|
| 2 s | 26,7 ms | 10,7% |
| 6 s | 112,2 ms | 44,9% |
| 10 s | 158,7 ms | 63,5% |
| 12 s | 270,4 ms | 108,2% — satura |

Antes das otimizações de sessão, 6 s custava 172 ms e 10 s pedia 104,9%.

## O que a calibração NÃO resolve

O retrabalho de 10,6× por hop, que vem de o modelo não ser streaming. Ver
[../modelo/nao-e-streaming.md](../modelo/nao-e-streaming.md).
