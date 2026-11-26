---
type: medicao
title: E6 etapa 1 — beam sem LM é um controle, e ele mede zero
description: >-
  Beam de prefixo CTC sem modelo de linguagem contra greedy, n=100 FLEURS pt_br, posteriores
  cacheadas (comparação pareada por construção).
tags: [medicao, beam, ctc, decoding, controle, e6]
timestamp: 2026-07-31T00:00:00Z
---

# E6 etapa 1 — o beam nu, medido

> **Pré-registro:** [`e6-preregistro-beam-lm.md`](e6-preregistro-beam-lm.md). H1 foi escrita antes
> desta corrida: *|Δ WER| < 0,2 p.p. e IC95 cruzando zero em todas as larguras*.

## Hipótese

**H1 — o beam SEM LM não muda o WER.** CTC assume independência condicional entre frames; sem LM,
o beam maximiza a mesma distribuição que o greedy já maximiza quadro a quadro, e as posteriores de
CTC são *peaky*. Isto é um **controle**, não um candidato: existe para permitir **atribuir** o
ganho da etapa 2 ao LM em vez de à busca.

## Evidência

`[MEDIDO]` FLEURS pt_br `test[0:100]`, régua `normalize_for_wer_compare`, posteriores extraídas
uma vez e compartilhadas por todos os decoders — a comparação é pareada **por construção**, não por
sorte. IC95 por bootstrap de **utterance** (10.000 reamostragens).

| decoder | WER | Δ p.p. | IC95 do Δ | ms/utt |
|---|---|---|---|---|
| greedy (base) | 16.07% | — | — | 0.4 || beam 2 | 15.99% | +0.08 | [-0.08; +0.24] | 17.3 || beam 4 | 16.11% | -0.04 | [-0.28; +0.20] | 30.6 || beam 8 | 16.18% | -0.12 | [-0.47; +0.17] | 46.4 |
> Convenção de sinal do kernel (`common/metrics.paired_bootstrap`): **Δ positivo = redução de
> WER**, isto é, o candidato é melhor.

## Conclusão

**H1 confirmada.** Nenhuma largura moveu o WER além de 0,2 p.p., e o IC95 do delta cruza zero em
todas — `comparar_pareado` devolveria `melhor=None`. O beam de prefixo, sozinho, **não é uma
alavanca de acurácia neste sistema**.

Isso não é um resultado negativo desperdiçado: é o que permite **atribuir** corretamente o que vier
na etapa 2. Se beam+LM render X, então X é do **modelo de linguagem** — o beam é o veículo que
torna o LM aplicável, e não uma melhoria de busca. Sem esta corrida, o ganho seria creditado à
"busca melhor", e a conclusão excederia a evidência.

Corolário de custo: os ms na tabela são o **piso** do que o LM vai custar. O LM só encarece, porque
adiciona uma consulta por extensão de prefixo.
## Limitações

- **n=100, uma corrida.** Suficiente para um resultado nulo pareado (o pareamento remove a
  variância entre condições), insuficiente para afirmar magnitude de um efeito pequeno.
- **FLEURS é leitura de notícias.** O regime do produto é call center 8 kHz espontâneo, onde o WER
  medido é bem pior (CORAA 23,31%). Nada aqui transfere para lá sem medição própria.
- **Caminho de lote.** O ms/utt é decode sobre posterior já pronta, em máquina ociosa. Ao vivo o
  RTFx é 3,58× contra um RNF-01 de 3× — a disciplina de evidência (§ 4): benchmark de componente não
  transfere para o sistema.
- **Nada aqui diz respeito ao LM.** A etapa 2 é outro experimento, com outro risco dominante — o
  vazamento do test set pelo corpus de treino do LM.
