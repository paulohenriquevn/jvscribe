---
type: Componente
title: FeatureCache — as três regras que o tornam correto
description: Cada amostra é featurizada uma vez. Errar qualquer das três regras diverge em silêncio, trocando CPU por WER.
resource: jvscribe/common/streaming.py
tags: [fbank, cache, features, kaldi, otimizacao]
timestamp: 2026-07-31T00:00:00Z
---

# FeatureCache — fbank incremental

Antes dele, `StreamingCTC` reextraía o fbank da **janela inteira** a cada hop — 21,6% do custo
de decode gasto refazendo o que já estava feito.

O cache só é legítimo se produzir exatamente as mesmas features. Senão troca CPU por WER **sem
nenhum erro visível**. Três regras, cada uma descoberta por divergência medida:

## 1. O offset tem de ser múltiplo do frame shift (160 amostras)

Com `snip_edges=False` o Kaldi **centra** os frames e preenche as bordas. Extrair a partir de um
offset desalinhado desloca o centro de todos os frames.

Medido: offset desalinhado diverge em **6,57**; alinhado converge a **9,5 × 10⁻⁷** — ruído de
float32.

## 2. A contagem de frames vem da extração, não de predição

O lhotse usa `round(L/shift)`, não `//`. **1.680 amostras dão 11 frames, não 10.** Predizer
errado por um desalinha o cache inteiro em silêncio.

## 3. Os 2 últimos frames de cada extração são retidos

O frame *i* abrange `[i·160 − 200, i·160 + 200]`, logo um buffer de tamanho *L* deixa até
**1,75 frames incompletos** na cauda — calculados com padding, mudariam quando chegasse mais
áudio.

Sem margem, divergiam exatamente os frames 49, 99, 149… — o último de cada pedaço, em até 6,27.
Com margem 1 ainda divergiam 4 frames; **2 é o valor derivado da conta**, não escolhido.

## Verificação

6 testes em `jvscribe/tests/test_streaming_features.py`, incluindo pedaços de tamanho irregular
(o caso real: `read()` devolve lotes variáveis) e milhares de appends de 32 ms.
