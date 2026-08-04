---
type: Medição
title: M1 — harness de medição
description: O instrumento antes do experimento.
tags: [medicao, m1, m2, rtfx]
timestamp: 2026-07-31T00:00:00Z
---

# M1 — Medição do Harness (evidência [MEDIDO])

> ⚠️ **Proveniência histórica.** Os caminhos e comandos citados abaixo são da árvore de
> diretórios vigente na data desta medição e **não resolvem no repositório atual** — inclusive
> o runtime Rust, removido em 2026-07-30. Ficam preservados como registro de *como* o número
> foi produzido: reescrevê-los para os caminhos de hoje documentaria um comando que nunca
> foi executado.

**Data:** 2026-07-24
**Comandos:** `./scripts/bench.sh 10` (janela curta) e `./scripts/bench.sh 3000 --load` (soak ~15 min sob carga) — P-cores fixados via `taskset -c 0-1`, release build
**Hardware:** máquina de referência do dev (i7 híbrido); **NÃO** é o piso da frota BYOD (Q-01 — `[DESCONHECIDO]`)
**Subject:** encoder emprestado de 600M (`models/m0-borrowed/encoder-model.onnx`), 10 iterações (2 de warmup), 2,98 s de áudio por iteração
**Rótulo:** `[MEDIDO — encanamento apenas]` — números do modelo **emprestado**, não do produto. Provam que a **régua** funciona, não que o modelo é bom (o modelo próprio vem em M5/M6).

## Resultado — duas medições

Rodadas duas medições distintas: **(A)** janela curta sem carga (`bench.sh 10`) e
**(B)** soak sustentado de ~15 min sob carga concorrente (`bench.sh 3000 --load`,
10 cores de `openssl` nos E-cores, encoder preso aos P-cores 0-1) — a medição
RNF-04/05 de verdade.

### (A) Janela curta, sem carga — encanamento

| Métrica | Valor | Alvo (RNF) | Observação |
|---|---|---|---|
| RTFx (áudio/parede), sem carga | **17,81×** | RNF-07 ≥ 6× | Warm, 8 amostras; ver warmup abaixo |
| Latência p50/p95/p99 | **154,9 / 237,8 / 237,8 ms** | RNF-02 p99 ≤ 500 ms | amostra pequena (p95=p99 por nearest-rank) |

### (B) Soak sustentado ~15 min SOB CARGA concorrente — RNF-04/05 `[MEDIDO]`

Comando: `./scripts/bench.sh 3000 --load` · 3000 iterações · carga concorrente
`openssl` nos E-cores 2-11 · encoder preso aos P-cores 0-1 via `taskset`.

| Métrica | Valor medido | Alvo (RNF) | Veredito honesto |
|---|---|---|---|
| **RNF-05** — RTFx sob carga concorrente | **11,32×** | RNF-07 ≥ 6× | ✅ passa mesmo sob 10 cores de carga (vs 17,81× sem carga — a carga custou ~36%) |
| **RNF-02** — latência p50/p95/p99 sob carga | **222 / 620 / 907 ms** | p99 ≤ 500 ms | ❌ **p99 907ms ESTOURA 500ms sob carga** — o encoder emprestado de 600M não sustenta a cauda (esperado: é 12× maior que o alvo de ~80M de M2) |
| **RNF-04** — razão térmica (2ª½ ÷ 1ª½) do soak | **2,09** | ≥ 0,80 | ⚠️ 2,09 > 1 = 2ª metade MAIS rápida; **sem throttling detectado** em 15 min, mas o valor é confundido pelo ramp-up da carga na 1ª metade — não é uma medição térmica limpa |
| Backlog | n/a offline | RNF-03 = 0 em 99,9% | Medido no modo `live` com captura real, não no bench offline |

**Leitura honesta (o ponto de M1):** a régua **funciona e mede** — inclusive
captou que o modelo emprestado **viola RNF-02 (p99) sob carga**. Isso é a régua
fazendo o trabalho dela: dar o número honesto, não fazer o modelo passar. O modelo
próprio de M2+ (~80M, streaming) é quem tem que fechar os 5 critérios; o encoder de
600M offline aqui é `[MEDIDO — encanamento apenas]`.

## O warmup importa (valida o ADR D2 do plano)

- **1ª iteração fria** (`macaw-cli fixture`, sem warmup): 1981 ms → RTFx ≈ **1,5×**.
- **Quente, janela curta** (bench, 2 warmup descartados): ~155 ms/iter → RTFx **17,81×** (não confundir com o RTFx sustentado do soak de 10 min, que não rodou).

Um benchmark que inclui o run frio na média (como `sherpa-onnx/…rtf-cxx-api.cc:120`)
reportaria um número entre os dois e **mentiria** sobre o regime sustentado — exatamente
a falácia § 3 #4 da disciplina de evidência. A régua descarta o warmup por
construção (`RtfxMeter::new(warmup_iters)`).

## Limites conhecidos (honestidade — § 4)

- **Razão térmica > 1 (2,09)**: em 15 min sob carga, o encoder não throttlou — mas o valor é confundido pelo ramp-up da carga concorrente na 1ª metade (a 1ª metade mediu o sistema esquentando, não um estado térmico estável). Um soak mais longo com carga estabilizada desde o início daria a medição térmica limpa. O chip híbrido desta máquina de referência (não o i7-1355U de referência) também tem envelope térmico diferente.
- **Máquina de referência ≠ piso da frota** (Q-01) — extrapolar estes números para "a frota" BYOD seria a falácia mais provável do projeto. Estes são de uma máquina de 12 cores com 15 GB; o parque real é desconhecido e provavelmente pior.
- **Modelo emprestado ≠ produto**: p99 907ms sob carga é do encoder de 600M offline. O modelo próprio de M2+ (~80M streaming) é 12× menor e tem que fechar RNF-02 — a régua existe justamente para provar isso quando ele existir.

## Reprodução

```bash
./scripts/bench.sh 10          # sem carga concorrente
./scripts/bench.sh 30 --load   # com carga nos E-cores (RNF-05)
```
