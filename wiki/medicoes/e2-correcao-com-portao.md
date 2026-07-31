---
type: Medição
title: E2 — a correção funciona, e menos do que eu previ
description: Redução de 0,27 p.p. [IC95 0,04; 0,54] a τ=1,0. Predição era 0,3 a 1,3 — errei por 0,03 e não movo a trave.
tags: [medicao, e2, correcao, portao, wer, protocolo]
timestamp: 2026-07-31T00:00:00Z
---

# E2 — correção pós-decode com portão `[MEDIDO]`

Data: 2026-07-31 · `git ca436e1` → E2 · FLEURS pt_br, n=100 · i7-1355U.
Fase E2 de [`portao-de-confianca-plan.md`](../../knowledge-base/plans/portao-de-confianca-plan.md).
Bruto: [`dados-brutos/e2-correcao-n100-tau1.0.md`](dados-brutos/e2-correcao-n100-tau1.0.md).

## Hipótese

Corrigir para o vizinho mais próximo do dicionário, **apenas** nas palavras que o portão sinaliza
e **apenas** quando a hipótese não é palavra, reduz o WER sem quebrar mais do que conserta.

**Predição pré-registrada:** redução entre **0,3 e 1,3 p.p.**, com **consertou/quebrou ≥ 3**.
**Critério de morte:** IC95% da redução **cruza zero**, ou `quebrou ≥ consertou`.

⚠️ **Escopo declarado antes de rodar:** FLEURS não tem domínio, logo não há lista de domínio para
o caminho `rare_ref`. Esta fase exercita **só** o caminho do dicionário (`non_word_hyp`, 31,5% do
erro), enquanto a predição foi calibrada sobre o teto dos **dois**.

## Evidência

Convenção única, a do kernel: **redução em p.p., positivo é melhor.**

| τ | redução | IC95% | cruza zero? | consertou | quebrou | razão |
|---|---|---|---|---|---|---|
| 0,50 | 0,16 | [−0,04; 0,38] | **SIM** ❌ | 4 | 1 | 4,0 |
| **1,00** | **0,27** | **[0,04; 0,54]** | não ✅ | **6** | **1** | **6,0** |
| 2,00 | 0,31 | [0,04; 0,61] | não ✅ | 8 | 2 | 4,0 |
| 3,00 | 0,39 | [0,08; 0,70] | não ✅ | 9 | 2 | 4,5 |

WER a τ=1,0: **16,07% → 15,79%** (1,7% relativo). Bootstrap pareado por utterance,
`common/metrics.paired_bootstrap`, seed fixa.

### O que ele consertou, e o que quebrou

```
consertou   dividades→divindades · filalactelistas→filatelistas · lagatos→lagartos
            radeo→radio · musquitos→mosquitos · openacao→operacao
quebrou     tmz→tez
```

A única quebra é **exemplar**: `TMZ` é o nome de um veículo de imprensa — um `rare_ref` que o
dicionário desconhece e que o corretor transformou numa palavra real. É a *over-correction* que
[`arXiv:2505.17410`](https://arxiv.org/abs/2505.17410) nomeia, flagrada em ato.

### O corretor se absteve em 93% do que o portão sinalizou

A τ=1,0 o portão sinaliza ~296 palavras e o corretor mexeu em **22** (6 consertos, 1 quebra, 15
neutras). A precondição de classe, o orçamento de distância e a abstenção em empate fazem o
trabalho de contenção que E1 previu ser necessário — lá se mediu que 44,1% do que o portão
sinaliza está **correto**.

## Conclusão — e apenas isto

**A predição errou, e não movo a trave.**

| | predito | medido | veredito |
|---|---|---|---|
| redução a τ=1,0 | 0,3 a 1,3 p.p. | **0,27 p.p.** | **errei por 0,03** |
| consertou/quebrou | ≥ 3 | **6,0** | confirmado |

**O efeito é real** — o IC95% [0,04; 0,54] exclui zero — mas menor que o previsto. Nenhum
critério de morte disparou a τ=1,0, então **E2 sobrevive**.

**E o critério de morte funcionou:** a τ=0,5 o IC **cruza zero**. Portão apertado demais sinaliza
pouco, o corretor mexe em menos, e o efeito deixa de ser distinguível de ruído.

### O aviso que vale mais que o número

A redução **cresce monotonicamente** com τ (0,16 → 0,27 → 0,31 → 0,39). É tentador reportar
**0,39 p.p. a τ=3,0**, que estaria *dentro* da faixa predita.

**Seria escolher o limiar depois de ver o resultado, no mesmo conjunto — seleção sobre o test
set.** O número honesto é o do ponto de operação **pré-registrado**: 0,27 p.p. Escolher τ exige
um split separado, e isso não foi feito.

## O que esta medição NÃO diz

- **Só o caminho do dicionário.** `rare_ref` (31,9% do erro) não foi exercitado — precisa de lista
  de domínio, e FLEURS não tem domínio.
- **O corretor filtra por (primeira letra, comprimento).** Erro que troca a primeira letra é
  invisível para ele. Troca deliberada de recall por tempo — comparar contra 436.107 palavras por
  consulta custaria minutos. O custo aparece como distância entre o obtido e o teto de 26,4%.
- **A atribuição consertou/quebrou é por posição**, aproximação que erra quando a correção muda o
  alinhamento. O ΔWER **não** depende disso; as contagens sim.
- **A varredura de τ é exploratória**, não um resultado. Ver o aviso acima.
- **Orçamento de distância não foi varrido** — o plano pedia τ × orçamento, e só τ foi feito.
- FLEURS é leitura de notícias; uma corrida; n=100.

## Aprendizado para o loop

> **Meu relatório usou duas convenções de sinal no mesmo documento** — Δ negativo como melhoria e
> IC positivo como melhoria — e por um instante o resultado pareceu contraditório. Uma convenção
> só, e a do kernel, porque é a que todo delta de WER publicado neste projeto já usa.

O segundo aprendizado é sobre o próprio protocolo: **a predição pré-registrada valeu a pena
justamente por ter errado.** Um alvo declarado depois de ver 0,39 a τ=3,0 teria "confirmado" a
hipótese e escondido que o efeito, no ponto que eu escolhi antes de olhar, é **um terço menor**
do que eu esperava.
