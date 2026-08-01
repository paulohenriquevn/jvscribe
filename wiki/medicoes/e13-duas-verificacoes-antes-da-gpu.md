---
type: medicao
title: E13 — as duas verificações de custo zero antes de gastar GPU
description: >-
  A hipótese do replay 32× cai no mecanismo (o --use-mux não existe neste recipe), mas revela que
  o projeto NÃO SABE quantas horas treinou. A convenção do NURC-SP custa 0,18 p.p. — o alvo se sustenta.
tags: [medicao, corpus, mux, treino, nurc, convencao, e13]
timestamp: 2026-08-01T00:00:00Z
---

# E13 — duas verificações antes da GPU

Duas perguntas ficaram na fila porque custam zero e podem tornar caro o desnecessário. Ambas
respondidas.

---

## 1. O CORAA está sendo replayado ~32× no mux?

**Hipótese** (do `speech-data-scientist`): o `--use-mux` 1:1 sobre fontes desiguais oversampleia a
menor, e o CORAA (273,5 h) seria replayado ~3,2× por época, ~32× ao longo de 10 épocas — o que daria
ao overfitting medido uma causa trivial e um remédio de graça.

### Refutada no mecanismo

`[FONTE-REPO]` `jvscribe/finetune/run_ft_codec.sh:13`, literalmente:

> `# DEFERIDO (para não patchar o modelo com risco agora): --use-mux (inexistente neste recipe;`
> `#   o p=0.5 cumpre o papel)`

**O `--use-mux` não existe neste recipe.** O treino rodou com `--manifest-dir data/mux`, isto é, o
mux foi feito **no nível do manifesto** — arquivos concatenados em disco, não um sampler em runtime
com pesos uniformes. Sem sampler, não há o mecanismo de oversampling que a hipótese descreve.

### Mas a verificação encontrou algo maior

`[MEDIDO]` extraído de `models/current/finetune/training.log` (1.130.845 linhas):

| época | batches | frames/batch (médio) |
|---|---|---|
| 1–8, 10 | **13.601** | ~9.347 |
| **9** | **10.551** ⚠️ | 9.416 |

O significado de `frames` foi confirmado no código, não suposto — `[FONTE-REPO]`
`icefall-f84270c/egs/commonvoice/ASR/zipformer/train.py:853`:

```python
info["frames"] = (feature_lens // params.subsampling_factor).sum().item()
```

É **pós-subsampling**. Logo, com fator 4 e passo de 10 ms:

**13.601 batches × 9.347 frames × 4 × 10 ms = 1.412,6 h apresentadas por época.**

### O achado: o projeto não sabe quantas horas treinou

Contra o que se apresenta 1.412,6 h? A documentação **se contradiz**:

| fonte | TAGARELA |
|---|---|
| `jvscribe/finetune/prep_tagarela.py:6` | "~500h" |
| `CHANGELOG.md:1338` | "Subset ~600h baixado na instância" |

Somando o CORAA (273,5 h), o mux único seria **773,5 h ou 873,5 h** — razão apresentado/único de
**1,8× ou 1,6×**, e **não os 3,2× da hipótese**.

E o `training.log` **não registra o tamanho do corpus**: a linha do datamodule diz apenas
`About to get train cuts`, sem contagem de cuts nem soma de durações. O manifesto `data/mux/` está
na instância de treino, não em disco local.

**Conclusão honesta:** não é possível estabelecer se a razão de 1,6–1,8× é (a) repetição no
manifesto, (b) manifesto maior do que a documentação afirma, ou (c) erro na própria documentação.
As três explicam o número igualmente bem, e nenhuma pode ser eliminada com o que existe em disco.

> ⚠️ **Isto é mais grave do que a hipótese original.** Toda projeção de escala deste projeto — a
> faixa de 4.000–20.000 h para 10%, o β de 0,33, a leitura de que "o modelo viu ~870 h" — usa como
> denominador um número que **não está estabelecido**. Recuperar o manifesto e somar as durações é
> pré-requisito de qualquer decisão de escala, e custa minutos.

> **Anomalia registrada:** a época 9 rodou 10.551 batches contra 13.601 das outras — 22% mais curta.
> Não investigada aqui; candidata a relação com o incidente de disco cheio já registrado no projeto.

---

## 2. Os 36,88% do NURC-SP embutem convenção de anotação?

**A preocupação era concreta e vinha de precedente:** a nossa própria régua contava acerto como erro
por 2,29 p.p. Se o texto do NURC-SP marcasse hesitação, truncamento ou sobreposição, parte dos
36,88% seria convenção, não reconhecimento — e o alvo inteiro se moveria.

### A convenção, inspecionada

`[MEDIDO]` 500 referências do split de validação:

| marcador | referências que contêm |
|---|---|
| colchete `[ ]` | **0** |
| parêntese `( )` | **0** |
| chave `{ }` | **0** |
| marca de truncamento `palavra/` | **0** |
| sigla em caixa alta | **0** |
| **dígito** | **0** |
| reticências | 33 (6,6%) |
| `eh`/`ah`/`ahn` | 27 (5,4%) |
| `né` | 45 (9,0%) |

**Texto ortográfico limpo, sem sistema de anotação.** E `dígito = 0` significa que a expansão de
número é **no-op** aqui — os 36,88% não sofrem do artefato que inflava o FLEURS.

O que existe são fenômenos de fala espontânea transcritos **como palavra**: repetição verbatim
(`é é preparado`, `o o lá em cima`, `pomar pomar`) e evento não-fala (`tosse`, `riso`, `rindo`).

### Quanto isso vale

`[MEDIDO]` n=250, tratamento aplicado aos **dois** lados (referência e hipótese):

| tratamento | WER | Δ |
|---|---|---|
| nenhum (como está) | **37,13%** | — |
| sem eventos não-fala | 37,09% | −0,03 |
| sem fillers (`eh`/`ah`/`né`) | 37,10% | −0,03 |
| sem repetição imediata | 37,05% | −0,07 |
| **os três juntos** | **36,95%** | **−0,18** |

Eventos não-fala aparecem **5 vezes em 250 utterances** (`tosse` 2, `riso` 2, `rindo` 1).

### Conclusão: o alvo se sustenta

**A convenção custa 0,18 p.p. — cerca de 0,5% do WER.** Contra os 2,29 p.p. que o artefato de
dígito custava no FLEURS, é duas ordens de importância abaixo.

**Os 36,88% do NURC-SP são erro de reconhecimento real.** O conjunto é genuinamente difícil, e a
recomendação de adotá-lo (E10) sobrevive à auditoria que poderia tê-la derrubado.

## Limitações

- **A razão apresentado/único de 1,6–1,8× é `[ESTIMATIVA]`**, porque o denominador não está
  estabelecido. O numerador (1.412,6 h/época) é `[MEDIDO]`.
- **A auditoria de convenção cobre o split de validação (500), não o de teste.** Convenções podem
  diferir entre splits, ainda que seja improvável no mesmo corpus.
- **Remover repetição imediata dos dois lados é uma aproximação grosseira** de "ignorar gagueira":
  colapsa também repetições legítimas (`que que`, `já já`). O efeito medido é teto, não valor exato.
