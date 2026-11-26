---
type: Medição
title: Benchmarks públicos reprodutíveis
description: FLEURS, CORAA e o recorte telefônico — com o comando de reprodução de cada um.
tags: [medicao, benchmark, fleurs, coraa]
timestamp: 2026-07-31T00:00:00Z
---

# Benchmarks públicos (reprodutíveis) — modelo M5 entregue


> ⚠️ **Superado em 2026-08-01.** Os 15,83% saem de `test[0:100]`, que é uma **amostra alta**: o test completo (919) dá **14,83%** na mesma régua, e **12,75%** na régua estrita. O slice foi aposentado. Ver [`e9`](e9-vies-do-normalizador-contra-modelos-de-forma-falada.md).
Medido com `jvscribe/batch/batch_transcribe.py` + `jvscribe/batch/eval_public_hf.py`
(ONNX int8, CPU, greedy). Todo número `[MEDIDO]`.

## FLEURS pt_br (test) — fala LIDA/limpa, banda-larga

`python3 jvscribe/batch/eval_public_hf.py --n 100`

| Métrica | Valor | (antes — régua local) |
|---|---|---|
| WER | **15,83%** | ~~16,14%~~ |
| acertos / subs / del / ins | 88,2% / 10,6% / 1,3% / 4,0% | 87,9% / 10,9% / 1,3% / 4,0% |
| amostras / palavras-ref | 100 / 2552 | idem |
| RTFx agregado (batch, CPU) | 44,8× ⚠️ | 24,6× |

**Re-medido em 2026-07-31 com a régua canônica** (`normalize_for_wer_compare`). Os 16,14%
anteriores saíram de uma `norm()` LOCAL do próprio script, que **preservava acento** — cada
acento errado contava como palavra inteira errada. Δ = **−0,31 p.p.**

> ⚠️ **O RTFx desta tabela não vale como medição.** Ambos os valores foram obtidos com a
> máquina sob carga (load 1,7–5,1 durante a re-medição) — a disciplina de evidência (§ 5):
> "máquina sob carga não mede". WER é determinístico e não sofre com isso; RTFx sofre. Para
> RTFx use `jvscribe/bench/runtime_bench.py` (pareado, round-robin) em máquina ociosa.

**Leitura:** em áudio de **boa qualidade banda-larga** (perfil de 128 kbps), o modelo entrega
~16% WER — melhor que os 23% de fala espontânea (CORAA) e muito abaixo do telefônico 8 kHz
(~32–40%). Confirma que o gargalo do telefônico é **canal/dado**, não o modelo.
