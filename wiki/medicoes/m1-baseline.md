---
type: Medição
title: M1 — baseline multi-modelo
description: Régua inicial: o que os modelos de referência entregam nesta máquina.
tags: [medicao, m1, m2, rtfx]
timestamp: 2026-07-31T00:00:00Z
---

# M1 — Baseline Report (test set 8 kHz)

> ⚠️ **Proveniência histórica.** Os caminhos e comandos citados abaixo são da árvore de
> diretórios vigente na data desta medição e **não resolvem no repositório atual**. Ficam
> preservados como registro de *como* o número foi produzido: reescrevê-los para os caminhos
> de hoje documentaria um comando que nunca foi executado.

**Corpus:** FLEURS pt_br (Google, CC-BY) — português BRASILEIRO, fala lida com transcrição humana, 12 utterances. **16 kHz limpo degradado para 8 kHz pela cadeia `telephone_augment.sh`** (resample + banda 300-3400 + G.711 a-law round-trip) — test set 8 kHz proxy, exercita a Fase 2 ponta-a-ponta. Caveat (falácia § 3 #6): fala LIDA (não conversa de call center 1:1 com crosstalk); o domínio real espontâneo depende de corpus consentido (LGPD, fora de escopo).

> Transcrição humana (NUNCA pseudo-label — invariante do projeto). Números `[MEDIDO]`; WER sempre com IC 95% via bootstrap por-utterance (blueprint ADR D3), nunca ponto isolado.

**Proveniência `[MEDIDO]`:** comando `python3 scripts/baseline_fleurs_ptbr.py 12 base,small,medium`; faster-whisper int8 CPU cpu_threads=1 beam_size=1 language=pt; dataset google/fleurs pt_br test (parquet); augmentação telephone_augment.sh; bootstrap seed=2026, n_boot=2000; hardware = máquina de referência do dev (NÃO o piso da frota BYOD, Q-01).

| Modelo | WER | IC 95% | n (utterances) |
|---|---|---|---|
| faster-whisper-base (int8, CPU) | WER = 21.3% | [IC95: 13.4%–30.8%] | 12 | `[MEDIDO]`
| faster-whisper-small (int8, CPU) | WER = 9.6% | [IC95: 5.0%–14.9%] | 12 | `[MEDIDO]`
| faster-whisper-medium (int8, CPU) | WER = 4.5% | [IC95: 2.1%–7.5%] | 12 | `[MEDIDO]`

