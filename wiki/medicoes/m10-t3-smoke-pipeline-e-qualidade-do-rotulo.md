---
type: Medição
title: T3 smoke — a cadeia funciona, e os dois professores discordam em ~20%
description: >-
  Pipeline validada de ponta a ponta em 2 shards reais. O rótulo que o TAGARELA já traz e o do
  Nemotron divergem em 22,7% das palavras — o que justifica re-rotular, mas não prova quem erra.
tags: [medicao, m10, t3, pipeline, smoke, concordancia, tagarela, rotulo]
timestamp: 2026-09-20T14:00:00Z
---

# T3 smoke — a cadeia inteira em 2 shards reais `[MEDIDO]`

Data: 2026-09-20 · i7-1355U, `taskset -c 0-3`, `num_threads=2` · chunk 1120 ms ·
`nemotron-3.5-asr-streaming-0.6b` int8 · 150 segmentos de 2 shards do TAGARELA (250 e 1450),
25,1 min de áudio.

## Por que este teste existe

O plano de treino na vast.ai comete o projeto a baixar centenas de gigabytes e pagar GPU. Antes
disso vale provar que a cadeia funciona em dados reais — ler shard, decodificar, normalizar,
comparar, emitir manifesto com proveniência.

E há uma oportunidade que o corpus oferece de graça: **o TAGARELA já traz `sentence`**, um
pseudo-rótulo de Whisper-large-v3 que os autores fine-tunaram sobre 1.000 h transcritas por API
comercial. Rodar o Nemotron sobre o mesmo áudio dá **dois professores de famílias diferentes** —
exatamente o sinal que o [ADR-004](../decisoes/index.md) defende, e que o filtro de concordância
consome.

## Resultado 1 — a cadeia funciona

150 segmentos processados, manifesto emitido com `source`, `licence`, `label_provenance`, `accent`
e `shard` por linha — o que a mitigação 1 do [ADR-0006](../decisoes/0006-tagarela-como-corpus-principal.md)
exige e o que torna o braço de licença limpa um filtro, não uma refação.

**RTFx em áudio real do domínio: 3,16×** — contra 3,44× medido em FLEURS no soak. Consistente:
áudio de podcast espontâneo não é mais caro que leitura de notícias.

## Resultado 2 — os dois professores discordam em 22,7% das palavras

| régua | mediana | p25 | p75 |
|---|---|---|---|
| canônica (sem acento, dígito) | 23,6% | 15,8% | 34,6% |
| leaderboard (acento, falado) | 24,1% | 15,4% | 33,3% |
| treino (acento, dígito) | 24,2% | 16,7% | 34,6% |

**A régua não é a causa.** A hipótese de que o formato numérico inflava a divergência — um
professor escrevendo `15` e outro `quinze` — está **refutada**: as três réguas dão o mesmo
número, e a do leaderboard converte dígito para forma falada nos dois lados.

Excluindo os 3 segmentos (2,0%) em que o Nemotron devolveu vazio, a mediana é **22,7%**. E ela
cai com a duração do segmento:

| recorte | n | mediana | p25 | p75 |
|---|---|---|---|---|
| todos, sem vazios | 147 | 22,7% | 15,6% | 33,3% |
| ≥ 5 s | 111 | 21,1% | 13,6% | 28,6% |
| ≥ 8 s | 88 | **18,8%** | 12,2% | 27,6% |

A queda é coerente com o chunk de 1120 ms: segmentos de 3 s dão dois ou três chunks, pouco
contexto para o encoder cache-aware. Os três vazios tinham mediana de **3,0 s**.

## Resultado 3 — o filtro de concordância, por limiar

| limiar de discordância | sobrevive | do TAGARELA (8.130 h pt-BR) |
|---|---|---|
| 5% | 5,3% | ~430 h |
| 10% | 11,3% | ~920 h |
| **20%** | **41,3%** | **~3.360 h** |
| **30%** | **66,0%** | **~5.370 h** |
| 50% | 87,3% | ~7.100 h |

Isto é o que o ADR-004 precisa para ser operacionalizado: **o limiar é um botão que troca volume
por qualidade de rótulo**, e agora a curva é conhecida.

## O que os exemplos mostram — e a ressalva que eles impõem

**Concordância alta** (0%): fala clara, frases completas, os dois idênticos exceto por pontuação.

**Na mediana** (~23%), ambos erram, e em direções diferentes:

| A (TAGARELA) | B (Nemotron) |
|---|---|
| *"a forma como os militares olham"* | *"a fórmula como os militares olham"* |
| *"perto da casa da minha mãe"* | *"perto a causa da minha mãe"* |
| *"é completamente justificável"* | *"É completamente inexplicável"* |
| *"tão polenemática"* | *"tão plemática"* |

O último par é instrutivo: **os dois estão errados**. A palavra provavelmente era "problemática".

⚠️ **Discordância não é erro.** Sem transcrição humana não se sabe quem erra: A errado e B certo,
B errado e A certo, os dois errados, ou os dois defensáveis. O que está medido é **divergência**,
e ela é um limite superior conjunto da qualidade dos dois — não uma acusação a nenhum.

## Consequência para o plano

**O ADR-003 fica justificado por medição.** Rótulos com ~20% de divergência contra um professor
independente são exatamente o tipo de ruído ao qual `wiki/treino/corpus.md` atribui o overfitting
de M5. Re-rotular com professor adaptado deixa de ser precaução e passa a ser resposta a um
número.

**O filtro de concordância ganha um ponto de operação defensável.** A 30% de limiar sobram
~5.370 h de pt-BR — dentro da faixa de 5.000–8.000 h que a Fase 3 do
[plano de treino](../../docs/plans/m10-treino-vastai.md) assume, sem precisar do corpus inteiro.

**E o braço de controle do ADR-004 fica mais barato do que parecia**: a curva acima permite
escolher dois limiares e comparar, em vez de treinar com e sem filtro.

## Limitações

1. **150 segmentos de 2 shards**, de 1.764. Cada shard é um show, então isto são **dois
   podcasts** — não uma amostra do corpus.
2. **Sem ground truth humano.** A ressalva acima vale inteira.
3. **O Nemotron não é o professor final.** O ADR-003 manda adaptá-lo a PT-BR antes de rotular;
   aqui ele rodou genérico. Um professor adaptado discordaria menos — ou discordaria do mesmo
   jeito, e isso é justamente o que a Fase 1 precisa medir.
4. **Segmentos curtos penalizam o Nemotron** a 1120 ms de chunk. Parte da divergência medida é
   artefato da configuração, não do modelo: em ≥ 8 s ela cai para 18,8%.
5. **A extração de fbank e o manifesto Lhotse completo não foram exercitados** — o manifesto
   emitido aqui é JSONL com os campos de proveniência, não um `CutSet`.
