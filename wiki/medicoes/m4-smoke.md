---
type: Medição
title: M4 — smoke do piloto
description: Verificação de que o pipeline de treino roda antes de gastar GPU no piloto completo.
tags: [medicao, m4, smoke]
timestamp: 2026-07-31T00:00:00Z
---

# M4 — Smoke de treino: evidência [MEDIDO] e a lição de overfitting

> ⚠️ **Proveniência histórica.** Os caminhos e comandos citados abaixo são da árvore de
> diretórios vigente na data desta medição e **não resolvem no repositório atual**. Ficam
> preservados como registro de *como* o número foi produzido: reescrevê-los para os caminhos
> de hoje documentaria um comando que nunca foi executado.

**Data:** 2026-07-25 · **Infra:** vast.ai RTX 3090 (imagem oficial `k2fsa/icefall:torch2.4.1-cuda12.1`) · **Custo:** ~$0,35 (instância ~1,5 h a $0,179/h)

## O que o smoke PROVOU (evidência real)

O **pipeline de treino de M4 funciona end-to-end numa GPU real** — o gargalo que o discover identificou (k2 ABI-pinado a torch/CUDA) foi resolvido usando a **imagem Docker oficial do icefall** (reuso, Regra 9). A cadeia completa rodou:

FLEURS pt_br (curl HTTP) → manifests Lhotse + fbank → BPE 256 → **treino Zipformer-CTC (6,1M) do zero na GPU** → checkpoint → **decode CTC-greedy → WER**. Reuso máximo: `Zipformer2`/`Conv2dSubsampling`/`ScaledAdam`/`Eden` do icefall; o mínimo próprio foi as 2 cabeças CTC + o loop + a cabeça de fonema (que **não existe na recipe** — Blueprint Q2). CTC via `torch.nn.functional.ctc_loss` (sem k2).

## Resultado da ablação — e por que a leitura ingênua é FALSA

| Modelo | WER **validation** (= set de treino) | WER **test held-out** (não visto) |
|---|---|---|
| Baseline (CTC subword) | 41,17% | **95,21%** |
| + cabeça de fonema | 17,89% | **99,27%** |

**A "melhoria de ~57% relativo" no validation é overfitting puro, NÃO evidência de que a supervisão fonética ajuda.** No held-out (o único WER honesto), ambos os modelos são inúteis (~95%+) e a cabeça de fonema é **até pior**. Com 386 utts (~1 h de áudio), modelo de 6,1M e 30 épocas, o modelo **memorizou** o treino — e a supervisão fonética (mais sinal) ajudou a memorizar mais, não a generalizar.

Isto é exatamente a armadilha que a disciplina de evidência existe para pegar: **WER de treino ≠ WER de generalização** (§ 2 — conclusão não pode exceder a evidência). Avaliar no held-out (feito por rigor) evitou reportar uma conclusão falsa sedutora.

## Conclusão honesta

- **`[MEDIDO]`** o pipeline de treino de M4 é **executável e correto** — treina, converge no set de treino, decoda, produz WER. Código pronto para escalar.
- **`[MEDIDO]`** o smoke (1 h de corpus) **não produz um modelo que generaliza** — WER held-out ~95%+. Esperado para esse volume.
- **A ablação da supervisão fonética é INCONCLUSIVA no smoke** — o overfitting domina; o held-out não mostra ganho. A tese só pode ser testada com o corpus/tamanho do **piloto real (~500 h)**, onde o modelo generaliza e a diferença fonema-vs-baseline é medível no held-out com IC (§ 3 #12).

## O que falta para M4 COMPLETO (o piloto real, precisa de mais crédito/tempo)

- Treinar em **~500 h** (não 1 h) → modelos que generalizam. Custo `[ESTIMATIVA]` do discover: ~$98-200 pela grade.
- Ablação da supervisão fonética **no held-out com corpus grande** (o critério ≥ 3% relativo só é medível aí).
- Os **3 tamanhos** (~30/80/123M) + curva **WER × RTFx** (RTFx na CPU-alvo via régua de M1).
- **FastConformer** (2º finalista de M2).

## Artefatos

- Código versionado: `training/{prep_fleurs,gen_phonemes,train_ctc,decode_ctc}.py`
- Log do treino/ablação (validation): `training/results/pilot-validation.log`
- G2P Q-08 (cobertura/determinismo medidos): Blueprint M4 § Corner 4/Q3
