---
type: ADR
title: TAGARELA como corpus principal, com o risco de licença aceito
description: 8.130 h de pt-BR espontâneo contra ~1.660 h de alternativas limpas. O risco NC/SA é aceito com os olhos abertos, e as mitigações são parte da decisão.
tags: [adr, corpus, tagarela, licenca, pt-br, m10, risco]
timestamp: 2026-09-14T18:00:00Z
---

# ADR-0006 — TAGARELA como corpus principal do M10

- Status: aceito
- Data: 2026-09-14
- Decisor: dono do projeto
- Evidência: [`m10-t3-quanto-corpus-pt-existe`](../medicoes/m10-t3-quanto-corpus-pt-existe.md)

## Contexto

O M10 precisa de corpus pt-BR em escala. A medição de T3 inventariou o que existe de fato, e o
resultado é assimétrico.

O **TAGARELA** (`freds0/TAGARELA`, ICASSP 2026) declara **8.130 h de pt-BR** e 842 h de pt-PT,
16.806 episódios, 2.094 shows, **13.368 falantes distintos**, com segmentos de **9,30 ± 5,49 s** —
forma adequada ao chunk de 1120 ms fixado no ADR-0006 de latência. Traz coluna `accent`, que
permite estratificar por sotaque. É `CC-BY-NC-SA-4.0`.

As alternativas de licença comercialmente limpa somam **~1.660 h**, das quais ~480 h são
VoxPopuli — medido em **3,8% de pt-BR** pela construção gramatical, ou seja, majoritariamente
português europeu de parlamento. O que sobra de pt-BR limpo e utilizável são **~1.180 h**, e
dessas 250 h do YODAS têm mediana de 0,98 s por segmento, curtas demais para ensinar contexto a um
modelo com chunk de 1120 ms.

A via de contornar a licença indo à fonte bruta **não existe**: o *Cem Mil Podcasts* é o Spotify
Podcast Dataset em português, e o canal público de distribuição saiu do ar (Q-09, respondida na
mesma medição). O TAGARELA é o acesso mais permissivo que existe àquele áudio.

## Decisão

**Usar o TAGARELA como corpus principal do M10, aceitando o risco de licença.**

O risco já estava registrado no `ROADMAP.md` § Constraints como "assumido em 2026-07-24". Esta ADR
não o cria — **dimensiona o que foi assumido** e o reafirma com o número na mesa: sem o TAGARELA,
o corpus pt-BR do projeto é **seis vezes menor**.

## O que exatamente se está aceitando

`CC-BY-NC-SA-4.0` impõe três coisas, e as três importam:

| cláusula | o que exige | por que pesa aqui |
|---|---|---|
| **BY** | atribuição | trivial de cumprir |
| **NC** | uso **não comercial** | o produto é para operação de call center de empresa |
| **SA** | derivados sob a **mesma licença** | se o modelo for derivado, ele herda NC e SA |

**A questão jurídica de fundo não está resolvida na indústria:** um modelo treinado sobre um
corpus é trabalho derivado dele? Não há consenso, há litígio em curso, e a prática comercial
corrente ignora a pergunta na maior parte dos casos. Este ADR **não resolve** a questão — registra
que o projeto avança sabendo que ela existe.

## Alternativas consideradas

**Corpus limpo, escala menor.** Usar só as ~1.180 h de pt-BR com licença comercial. Rejeitada: é
menos dado do que o modelo atual já viu (~1.413 h, `e13`), então não move o gargalo que o
diagnóstico de M5 identificou. Manteria o projeto exatamente onde está.

**Ir à fonte bruta do Cem Mil Podcasts.** Rejeitada por impossibilidade: canal fechado, e a
licença de origem é mais restritiva, não menos.

**Coletar corpus próprio.** Não rejeitada — adiada. É a saída de longo prazo se o risco se
materializar, e a preparação para ela está nas mitigações abaixo.

**Comprar corpus licenciado.** Não avaliada. Fica registrada como opção não explorada, porque o
orçamento de dado nunca foi discutido — só o de GPU.

## Consequências

**Positivas.** O gargalo de dado deixa de ser estrutural: 8.130 h de fala espontânea brasileira,
com 13.368 falantes e segmentos bem dimensionados, é a diferença entre um experimento e um modelo.
A coluna `accent` permite construir o test set estratificado que o critério de call center vai
exigir.

**Negativas, e assumidas.**

1. **O artefato final pode não ser distribuível comercialmente** sem resolver a questão do
   derivado. Isso não bloqueia M10 (que é pesquisa e medição), mas **bloqueia M8** (piloto com
   atendentes reais numa operação) se não for resolvido antes.
2. **O SA pode contaminar a distribuição do modelo.** Se derivado, o peso teria de sair sob
   `CC-BY-NC-SA-4.0` — incompatível com a `Apache-2.0` do repositório.
3. **A dependência é de fornecedor único.** Se o TAGARELA sair do ar, como o Cem Mil Podcasts
   saiu, o projeto perde 84% do seu corpus pt-BR.

## Mitigações — parte da decisão, não promessa vaga

1. **Proveniência por shard, obrigatória.** Cada entrada do manifesto carrega fonte e licença
   (critério de aceitação de T3). Sem isso, não há como separar depois o que veio de onde.
2. **Um braço de corpus limpo, mantido em paralelo.** As ~1.180 h de licença comercial formam um
   subconjunto identificável, para que "retreinar sem TAGARELA" seja uma operação de horas e não
   de meses.
3. **Cópia local do TAGARELA preservada.** Mitiga a consequência 3, e vale a regra de M9: peso e
   dado não se apagam.
4. **A questão do derivado precisa ser respondida antes de M8, não antes de M10.** Fica registrada
   como pendência explícita no `ROADMAP.md`, com o milestone que ela bloqueia.

## O que mediria esta decisão como errada

Se o braço de corpus limpo (~1.180 h) produzir WER a menos de 2 p.p. do braço completo, então as
8.130 h do TAGARELA não estavam pagando o risco que carregam — e a decisão deve ser revista. Esse
contraste é barato de medir e **deve** ser medido em T5, não assumido.
