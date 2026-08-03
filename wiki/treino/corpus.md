---
type: Diagnóstico
title: O gargalo é dado, não arquitetura
description: O finetune faz overfitting, não underfitting — o que prova que a capacidade do encoder é suficiente.
tags: [corpus, overfitting, dados, alavancas]
timestamp: 2026-07-31T00:00:00Z
---

# O gargalo é dado, não arquitetura

## O diagnóstico `[MEDIDO]`

O finetune de M5 faz **overfitting**, não underfitting. No melhor ponto de cada época (logo
após o reshuffle) train ctc ≈ val ctc (~0,23 ≈ 0,23), mas **dentro da época** a val sobe acima
da train (0,23 → 0,29–0,34) e o WER no CORAA humano degrada.

**Overfitting prova que a capacidade do encoder é suficiente** — um modelo pequeno demais faria
o oposto.

Logo: não se muda a arquitetura. Seria retrabalho contra a medição de M4, e 64M é o tamanho
**certo dado o constraint** de real-time (`large`/`XL` violariam o RNF-07). A alavanca é
**dado — qualidade antes de quantidade**, porque o overfitting é ao ruído dos pseudo-rótulos
Whisper do TAGARELA.

## Três alavancas antes de colher dado novo (caro)

Todas atacam o **mesmo** overfitting:

1. **Augmentação LIGADA** — o run de convergência rodou com `--enable-musan 0`. Religar a
   cadeia Reverb→Noise→Telephone + SpecAugment mais forte + weight decay é regularização de
   graça. Bônus: ataca também o WER telefônico 8 kHz.
2. **Checkpoint averaging** — `[MEDIDO]`, não mais estimativa: a média de 112k+124k dá WER
   **15,99%** contra 17,32% do checkpoint único, IC95% do delta [−2,25; −0,43] pp.
3. **Beam search + LM no decode** — **4,7% relativo** `[MEDIDO]` em 2026-08-01
   ([`e6-beam-lm.md`](../medicoes/e6-beam-lm.md)), **não** os 10–20% que esta linha afirmava. A
   faixa antiga era `[LITERATURA]` colhida de CTC nível-caractere e de modelos treinados em
   minutos de áudio — falácia § 3 #2. Corpus, ordem e largura de beam **saturaram**.
   O decode de hoje é greedy, o piso. **É também o que tornaria o FLToP aplicável** —
   ver [../otimizacao/o-que-nao-se-aplica.md](../otimizacao/o-que-nao-se-aplica.md).

Ordem de valor por custo: averaging → beam/LM → medir; se platôar acima do alvo, religar
augmentação num run curto; só então investir em dado.

## O tamanho do corpus

**8.972 h** disponíveis, contra as **15.000–94.000 h** que a receita de referência usa para
monolíngues pequenos treinados do zero — num regime que a própria fonte identifica como o que
*mais* precisa de dados.

Q-09 (acesso às ~76k h brutas do Cem Mil Podcasts) vale mais para o WER final do que qualquer
escolha de encoder.

## Invariante

**Pseudo-label nunca entra no test set.** Mede concordância com o professor, não acurácia.
