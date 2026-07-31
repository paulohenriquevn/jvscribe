---
type: Medição
title: E2 — correção pós-decode com portão (bruto, n=100, τ=0.5)
description: ΔWER da correção por vizinho mais próximo, com consertou e quebrou contados em separado.
tags: [medicao, dados-brutos, e2, correcao, portao, protocolo]
timestamp: 2026-07-31T00:00:00Z
---

# E2 — correção pós-decode com portão `[MEDIDO]`

**Data:** 2026-07-31T18:19:15 · **Comando:** `python3 jvscribe/probes/portao_correcao_probe.py --corrigir --n 100 --tau 0.5`
**Amostra:** 100 utterances de FLEURS pt_br · τ = 0.5

## Predição pré-registrada

Redução de WER entre **0,3 e 1,3 p.p.**, com **consertou / quebrou ≥ 3**.

**Critério de morte:** IC95% da redução **cruza zero**, ou `quebrou ≥ consertou`.

⚠️ **Escopo declarado antes de rodar:** FLEURS não tem domínio, logo não existe lista de domínio
para o caminho `rare_ref`. Esta medição exercita **apenas** o caminho do dicionário
(`non_word_hyp`, 31,5% do erro). A predição foi calibrada sobre o teto dos **dois** caminhos.

## Resultado

Uma convenção só, a do kernel: **redução em p.p., positivo é melhor.**

| | WER |
|---|---|
| base (greedy) | **16.07%** |
| com correção | **15.91%** |
| **redução** | **0.16 p.p.** (1.0% relativo) |

IC95% da **redução** (bootstrap pareado por utterance, seed fixa):
**[-0.04; 0.38] p.p.**

> ❌ **O IC cruza zero.** Pelo critério de morte pré-registrado, este caminho **morre aqui**.

## O dano dos dois lados

| | n |
|---|---|
| **consertou** | 4 |
| **quebrou** | 1 |
| neutro (errado antes, errado depois) | 12 |
| **razão consertou/quebrou** | 4.00 |

A redução isolada esconde isto: um delta nulo pode ser zero mudanças **ou** cinquenta consertos e
cinquenta quebras. São situações diferentes e exigem decisões diferentes.

- consertou: dividades→divindades, filalactelistas→filatelistas, radeo→radio, musquitos→mosquitos
- quebrou: tmz→tez

## Limitações

- **Só o caminho do dicionário.** `rare_ref` (31,9% do erro) exige lista de domínio, que FLEURS
  não tem.
- **Bucket por (primeira letra, comprimento)** no corretor: erro que troca a primeira letra é
  invisível. Troca de recall por tempo — comparar contra 436.107 palavras por consulta custaria
  minutos.
- **Atribuição consertou/quebrou por posição** — aproximação. Quando a correção muda o
  alinhamento (merge, split), a atribuição por índice erra. O ΔWER **não** depende disso; as
  contagens sim.
- FLEURS é leitura de notícias. Uma corrida.
