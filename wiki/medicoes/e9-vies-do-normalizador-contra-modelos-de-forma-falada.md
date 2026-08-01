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

---

# Adendo — a régua canônica erra nos DOIS sentidos, e o paper índico não cobre nem um

## O que `arXiv:2409.02449v4` de fato diz

Verificado em 2026-08-01. O paper trata de **outra falha**: o normalizador do Whisper remove
caracteres da *mark class* do Unicode, destruindo matras e virama de escritas índicas. Achados:

- **Não menciona numeral nem dígito** em lugar nenhum.
- Conclui que línguas de **escrita latina são largamente não afetadas** pela falha que descreve.
- Os autores declaram explicitamente que **não propõem novo algoritmo** de normalização.

**Não há, portanto, "corrigir a avaliação conforme o paper"** — não existe procedimento descrito a
aplicar, e o defeito que ele documenta não é o nosso.

## O princípio que transfere, e nos incomoda

O argumento central do paper é que **remover diacrítico infla artificialmente a melhora de WER**.
A nossa régua canônica **remove acento**. Medido no test completo (n=919, greedy):

| régua | WER |
|---|---|
| sem acento · com dígito — **a publicada** | 14,83% |
| sem acento · forma falada | 12,54% |
| com acento · com dígito | 15,14% |
| **com acento · forma falada** | **12,75%** |

**A remoção de acento nos favorece em +0,31 p.p.**, IC95 pareado [+0,24; +0,38] — reproduzindo o
0,31 que o projeto já medira em n=100, de brinde como checagem.

Logo a régua canônica erra nos dois sentidos: **pune 2,29 p.p.** no eixo do dígito e **premia 0,31
p.p.** no eixo do acento. O número que este projeto vinha chamando de corrigido (12,54%) ainda
embutia o prêmio.

## Por que, em português, isto é pior que "perdoar grafia"

Remover acento não perdoa apenas ortografia — **funde palavras distintas**:

| par | são a mesma palavra sem acento | significam |
|---|---|---|
| `e` / `é` | `e` | "e" / "é" |
| `pais` / `país` | `pais` | "pais" / "país" |
| `esta` / `está` | `esta` | "esta" / "está" |
| `avô` / `avó` | `avo` | "avô" / "avó" |

Num call center, `é` virando `e` altera o sentido da frase. A régua que apaga essa diferença mede
algo mais permissivo do que "o sistema entendeu o que foi dito".

## Recomendação

O número defensável para **acurácia de reconhecimento** é o da régua estrita: **com acento e forma
falada nos dois lados**. As outras continuam existindo, com uso declarado:

| régua | uso | WER (greedy) |
|---|---|---|
| sem acento · com dígito | comparabilidade com leaderboards de PT (enviesada, mas é a deles) | 14,83% |
| **com acento · forma falada** | **decisão interna e afirmação de acurácia** | **12,75%** |

⚠️ O número de beam+LM publicado neste projeto (**12,03%**) foi medido na régua *sem acento*. Na
régua estrita ele fica em torno de **12,2%** `[ESTIMATIVA]`, aplicando o delta de acento medido no
greedy — **não medido diretamente**, e portanto não citável como resultado.
