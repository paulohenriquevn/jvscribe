---
type: Pipeline
title: Tempo real — dois canais, com rótulo de falante
description: Captura mic e loopback em paralelo, transcreve os dois e mede os RNF enquanto roda.
resource: jvscribe/realtime/live_transcribe.py
tags: [tempo-real, captura, dual, localagreement, rnf]
timestamp: 2026-07-31T00:00:00Z
---

# Pipeline de tempo real

```
   microfone                        loopback da placa
 (ATENDENTE)                          (CLIENTE)
      └──────── DualCapture ──────────────┘
             (um `parec --device=` por stream)
                      ▼  read() DRENA a fila, teto POR STREAM
              backpressure: atraso > 2 s → descarta o áudio ANTIGO
        ┌─────────────┴─────────────┐
  StreamingCTC (mic)         StreamingCTC (loopback)
        │  FeatureCache · janela deslizante · ONNX (sessão COMPARTILHADA)
        │  ctc_words → LocalAgreement-2 → confirma o que se repetiu
        └────────► Transcricao (turnos) + MetricasRNF ◄──────┘
```

## Por que não há diarização

No caso 1:1 — o dominante — ela não precisa existir. O microfone **é** o atendente por
construção da captura, e o loopback **é** o cliente. Roteamento de stream: custo zero,
acurácia 100%. Diarização só entra no caso de 3 falantes.

`sounddevice` não serve: `sd.query_devices()` lista 8 entradas e **zero** monitor sources. Daí
o `parec` com `--device=` explícito, um processo por stream.

## LocalAgreement-2

O modelo é offline; a ilusão de streaming vem do algoritmo. Uma palavra só é dada como final
quando **duas decodificações consecutivas concordam** com ela — é o que evita o texto piscar.

O preço é latência (nada é final antes de dois ciclos) e o retrabalho da redecodificação; o
ganho é poder usar um modelo não-causal ao vivo. Ver
[../modelo/nao-e-streaming.md](../modelo/nao-e-streaming.md).

## Estado limitado por construção

`committed` guarda no máximo **64** palavras — só a última é consultada, e o histórico do
diálogo é responsabilidade de `Transcricao`. Sem esse teto, uma ligação de 40 min acumulava
~28 mil tuplas no caminho quente (medido: 2.128 em 3 min).

## Backpressure

Quando o consumidor fica para trás, o áudio **antigo** é descartado, preservando a cauda: numa
ligação, o que o cliente acabou de dizer importa mais que o de 15 s atrás.

Sem isso, o laço atrasado nunca recuperava — o atraso medido subiu de 392 ms para 18.798 ms e
ficou lá. A perda aparece no relatório: preferir texto recente a texto completo é uma **troca**,
não um conserto grátis.

## O defeito de captura que isso expôs

`DualCapture.read()` devolvia **um** chunk por stream por chamada, enquanto o `parec` produz
~30/s por canal. O backlog crescia sem limite — 101 → 227 chunks em 4,4 s. Corrigido com dreno
e teto **por stream**; o teto global da primeira tentativa deixava um canal cheio matar o outro
de fome, o que perderia metade da conversa.

Backlog caiu de **100% para ~2%** das amostras.
