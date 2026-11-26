---
type: medicao
title: E7 — o que o int8 custou em WER
description: >-
  Mesmos pesos (ckpt124k), só a precisão muda. Isola o custo de acurácia da quantização e testa se
  o orçamento de RTFx relaxado para 1.5× compra o fp32 de volta.
tags: [medicao, quantizacao, int8, fp32, rtfx, orcamento, e7]
timestamp: 2026-07-31T00:00:00Z
---

# E7 — o custo de acurácia do int8

## Hipóteses (pré-registradas no docstring de `probes/quantizacao_probe.py`)

- **H1** — o int8 custou WER mensurável. Predição: fp32 melhor por **0,1 a 0,8 p.p.**, IC95
  excluindo zero. Morte: IC95 cruzando zero.
- **H2** — o fp32 cabe em lote no alvo novo de 1.5×, e não cabe ao vivo.

## Desenho

O par é **controlado**: `models/jvscribe-ptbr-zipformer-ctc-64m/alternates/ckpt124k.int8.onnx` e `models/jvscribe-ptbr-zipformer-ctc-64m/alternates/ckpt124k.fp32.onnx` são os **mesmos pesos**; só a precisão difere.
As features de fbank são extraídas **uma vez** e reusadas — extrair por modelo adicionaria custo e
a chance de os dois verem entradas diferentes, o que destruiria o pareamento.

## Evidência

`[MEDIDO]` FLEURS pt_br `test[0:100]`, greedy CTC, `intra=2`, régua
`normalize_for_wer_compare`. IC95 por bootstrap de **utterance**, 10.000 reamostragens.

| precisão | WER | RTFx | ms/utt |
|---|---|---|---|
| int8 | 17.32% | 14.3× | 959 |
| fp32 | 17.20% | 9.0× | 1524 |

**Δ (int8 → fp32): +0.12 p.p.**, IC95 [-0.25; +0.49]
— o intervalo **cruza zero**.

> Convenção de sinal do kernel: **Δ positivo = redução de WER** (o fp32 é melhor).

> ⚠️ **load average 7.9 — acima do limiar 1: números de TEMPO indeterminados** — o WER acima continua válido (não depende de tempo), mas **RTFx e ms
> são indeterminados**: medem contenção, não o custo do produto. Repita numa máquina ociosa antes
> de decidir orçamento por estes números.

## Conclusão

**H1 refutada.** O IC95 do delta cruza zero: nesta amostra a quantização int8 **não custou
acurácia mensurável**. `comparar_pareado` devolveria `melhor=None`.

Isso tem consequência direta para o orçamento: **relaxar o RNF-01 não compra acurácia por esta
via.** Se sobra compute, ele deve ser gasto em algo que a evidência mostre que rende — o modelo de
linguagem no decode é o candidato com massa de erro medida atrás dele (`real_word_hyp`, 36,6%).

Vale registrar o que isto **não** diz: não diz que o int8 é gratuito em todo regime. Diz que, em
FLEURS wideband com n=100, não se enxerga custo. Em 8 kHz — onde o sinal tem menos energia e a
faixa dinâmica dos ativações muda — o efeito da calibração pode ser outro, e isso é `[DESCONHECIDO]`.
## Limitações

- ⚠️ **Estes são os pesos do checkpoint ÚNICO (WER 17,32%), não os do modelo entregue** (média de
  112k+124k, 15,99%). Aplicar este delta ao modelo médio é `[ESTIMATIVA]`: a média de checkpoints
  altera a distribuição dos pesos, que é exatamente o que a quantização discretiza. Para decidir
  sobre o modelo entregue, é preciso exportar o fp32 dele — o `.pt` está em disco.
- **n=100, uma corrida, FLEURS.** Leitura de notícias, banda larga. O regime do produto é call
  center 8 kHz espontâneo, onde o WER medido é bem pior e o efeito da quantização é `[DESCONHECIDO]`.
- **RTFx aqui é de lote, com features pré-extraídas.** Ao vivo há dois canais, subprocessos de
  captura e reprocessamento de janela — a disciplina de evidência (§ 4): benchmark de componente não
  transfere para o sistema.
