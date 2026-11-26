---
type: medicao
title: E16 — relaxar o RTFx para 1× não compra qualidade
description: >-
  A 1×, todo lever de decode já está refutado ou saturado, e um modelo maior de prateleira ainda
  NÃO cabe (Whisper small = 0,7× nesta CPU). A aposta de especialização sobrevive.
tags: [medicao, rtfx, orcamento, whisper, arquitetura, e16]
timestamp: 2026-08-03T00:00:00Z
---

# E16 — o que 1× de RTFx compra

## A proposta

Despriorizar o RNF-01 até **~1×** (tempo real sem folga) para comprar qualidade de transcrição.
É a terceira relaxação do orçamento nesta campanha (3× → 1,5× → 1×), e cada uma foi medida.

## O que o orçamento extra teria para comprar

Todos `[MEDIDO]` nesta campanha, e todos consomem compute:

| alavanca | resultado |
|---|---|
| int8 → fp32 | IC cruza zero — **nada** (E7) |
| beam sem LM | IC cruza zero — **nada** (E6 etapa 1) |
| largura de beam 8 vs 4 | **pior** com LM (E6) |
| corpus do LM acima de 2,5M palavras | satura — **nada** (E6) |
| ordem do n-grama acima de 3 | satura; ordem 5 **piora** (E6) |
| realce / denoising / BWE | seis técnicas, **seis pioras** (E12) |
| viés de blank sob o canal alvo | **não valida** (E15 adendo) |

**Não há onde gastar o orçamento no decode.** Está tudo refutado ou saturado, e isso foi medido
*antes* de a relaxação ser proposta.

## O que 1× realmente reabriria — e a medição fecha de novo

O [`ROADMAP.md`](../../ROADMAP.md) § Vision fundamenta a aposta do projeto assim: *"um modelo que só faz PT-BR telefônico cabe em
dezenas de milhões de parâmetros onde um multilíngue de 600M não fecha real-time em CPU"*. Se o
requisito cai para 1×, essa premissa precisa ser reexaminada.

`[MEDIDO]` 2026-08-03, mesma CPU, mesmo áudio (NURC-SP `quality=low` + canal do spec), 173 s:

| modelo | params | RTFx | cabe em 1×? |
|---|---|---|---|
| **jvscribe** | **64M** | **16,7×** | sim, com folga de 16× |
| faster-whisper small (int8, 4 threads) | 244M | **0,7×** | **NÃO** |
| faster-whisper medium | 769M | não medido — small já não cabe | não |

**Mesmo a 1×, um modelo de prateleira de 244M não cabe nesta CPU.** A aposta de especialização
sobrevive à relaxação — e sobrevive por margem larga, não por pouco.

## O que NÃO foi estabelecido, e por que não publico o número

A comparação de **WER** contra o Whisper foi **injusta** e não é reportada como acurácia dele. Os
segmentos do NURC-SP são curtos (2–4 palavras em alguns casos) e o Whisper é desenhado para janelas
de 30 s: ele preenche, alucina ou devolve vazio. A inspeção da saída mostra os dois modos:

```
REF: Porque ele trocava pelo preço que estava
HYP: Porque ele tocava pelo preço que estava fixado.   <- quase certo + alucinou "fixado"

REF: exagerada exagerados. Ou quadris
HYP: (VAZIO)
```

Os 97,22% que a corrida produziu medem **descasamento de desenho**, não capacidade. Uma comparação
justa exigiria áudio longo com o VAD do próprio Whisper e alinhamento de referência compatível —
não foi feita, e o número não entra em lugar nenhum como "o WER do Whisper".

## O achado colateral: degradações compõem de forma super-aditiva

`[MEDIDO]` o mesmo canal do spec aplicado a dois recortes do NURC-SP:

| recorte | sem canal | com canal | Δ |
|---|---|---|---|
| `quality=high` | 32,45% | 51,62% | **+19,2** |
| `quality=low` | 54,02% | 80,97% | **+27,0** |

O **mesmo** canal custa 19 p.p. no áudio melhor e 27 p.p. no pior. E no FLEURS lido custava ~4 p.p.
(E14). **A degradação não soma — ela compõe.** Estimar WER de produção somando "custo do canal" ao
WER de fala espontânea subestima, e subestima mais quanto pior for o áudio base.

## Conclusão

**Relaxar o RTFx para 1× não compra qualidade.** O gargalo não é compute — é modelo e dado. Manter
o RNF-01 em ≥3× não está custando acurácia nenhuma hoje, e abrir mão dele entrega folga que não tem
onde ser gasta.

O que compra qualidade, pela evidência desta campanha: **treinar em fala espontânea no canal alvo.**

## Limitações

- **n=30 para a comparação de RTFx**, uma corrida, máquina com load moderado. Suficiente para
  separar 16,7× de 0,7× (fator 24×); insuficiente para afirmar o RTFx do Whisper com precisão.
- **`cpu_threads=4` para o Whisper contra `intra=2` do nosso** — a comparação de RTFx é generosa
  com o Whisper, não com o nosso, e mesmo assim ele não cabe.
- **Whisper medium e large-v3 não foram medidos.** Estão em cache, mas o small já responde a
  pergunta: se 244M dá 0,7×, 769M não chega perto.
