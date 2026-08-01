---
type: medicao
title: E9 — o normalizador padrão pune modelos de forma falada, e só em não-inglês
description: >-
  O EnglishTextNormalizer do Whisper converte número por extenso em dígito; o BasicTextNormalizer
  usado para português não faz nada. Modelos treinados em forma falada pagam ~2,3 p.p. de WER que
  o modelo não errou.
tags: [medicao, wer, normalizacao, benchmark, vies, fleurs, e9]
timestamp: 2026-08-01T00:00:00Z
---

# E9 — o viés do normalizador padrão contra modelos de forma falada

## A pergunta

Depois de descobrir que a nossa régua contava acerto como erro (2,29 p.p.), a pergunta seguinte é
se a régua **padrão da área** faz o mesmo. Se fizer, toda comparação nossa contra modelos públicos
está enviesada — e não a nosso favor.

## Evidência

`[MEDIDO]` 2026-08-01, `transformers` 4.57.3, chamando os normalizadores do Whisper diretamente:

| entrada | `BasicTextNormalizer` (não-inglês, **inclui PT**) | `EnglishTextNormalizer` (só inglês) |
|---|---|---|
| `na casa dos 20 anos` | `na casa dos 20 anos` | — |
| `na casa dos vinte anos` | `na casa dos vinte anos` | — |
| `he was 20 years old` | — | `he was 20 years old` |
| `he was twenty years old` | — | **`he was 20 years old`** |

**Para inglês, o normalizador padrão resolve o descasamento dígito↔extenso. Para português, ele
não faz nada** — as duas formas nunca casam, e cada número vira erro.

## Por que isso nos atinge, e não atinge o Whisper

Três fatos, todos já medidos neste projeto, formam a assimetria:

1. **A referência do FLEURS pt_br traz dígito** — 187 das 919 utterances, depois da régua canônica.
2. **O nosso texto de treino não tem dígito** — o CORAA tem **zero** em 106.620 palavras. Um modelo
   treinado assim **não consegue** emitir dígito; a forma falada é a única que ele conhece.
3. Portanto, nessas 187 utterances, o nosso modelo é penalizado por **não fazer** algo que nunca
   foi treinado a fazer, e que é tarefa de **ITN** (*inverse text normalization*), a jusante do
   reconhecedor.

Custo medido dessa penalidade no nosso modelo: **2,29 p.p.** (14,83% → 12,54%), IC95 pareado
[+1,73; +2,42].

## O que isto NÃO estabelece

⚠️ **Não medi o Whisper.** A afirmação "o Whisper emite dígito e por isso não paga essa
penalidade" é `[LITERATURA]`/plausível — decorre de ele ser treinado em texto da web em forma
escrita — mas **não foi verificada aqui**. Verificá-la exige rodar o Whisper em português sobre as
mesmas 187 utterances e contar quantas saídas trazem dígito. Enquanto isso não for feito, o que
está medido é apenas: **o normalizador padrão não corrige o descasamento em português, e corrige em
inglês**.

Também não estabelece que a régua corrigida seja "a certa". A direção da conversão é decisão de
produto: se o consumidor a jusante quer CPF em dígito, o conserto é um estágio de ITN na hipótese;
se quer verbatim, o conserto é expandir a referência. O que **não** é defensável é medir forma
falada contra forma escrita e chamar a diferença de erro de reconhecimento.

## Consequência prática

Publicar **um** número passou a ser insuficiente. A partir daqui, todo WER deste projeto sai em par:

| régua | uso |
|---|---|
| `normalize_for_wer_compare` | **comparabilidade externa** — é o que os leaderboards usam para PT, mesmo enviesada |
| `+ expandir_numeros` | **decisão interna** — mede acurácia de reconhecimento, não formatação |

Citar só a segunda infla o nosso número contra terceiros; citar só a primeira esconde 2,29 p.p. de
acerto que o modelo teve. As duas, sempre rotuladas.

## Limitações

- `n=919`, FLEURS pt_br, leitura de notícias. Em call center espontâneo a densidade de número é
  **maior** (CPF, protocolo, valor), então o efeito tende a ser **pior** lá — mas isso é
  `[DESCONHECIDO]`, não medido.
- A verificação do normalizador foi feita em `transformers` 4.57.3. Outras implementações
  (`whisper_normalizer`, o repositório original da OpenAI) não foram testadas.
- Nada aqui diz respeito a acento, que é o outro eixo do `BasicTextNormalizer` e onde este projeto
  já pagou um defeito de régua separado.
