---
type: Índice
title: jvscribe — base de conhecimento
description: ASR PT-BR em tempo real sobre CPU. Modelo, motor de inferência, medições e as decisões que os produziram.
resource: https://github.com/paulohenriquevn/jvscribe
tags: [asr, pt-br, cpu, real-time, zipformer, ctc]
timestamp: 2026-07-31T00:00:00Z
---

# jvscribe

Transcritor de português brasileiro que roda **ao vivo no notebook do atendente** — sem GPU,
sem chamada de rede, sem custo por hora transcrita.

O escopo é **o modelo** e **o motor de inferência**. Plataforma de frota, compliance e UI
ficam fora.

## Por onde começar

| Se você quer… | Vá para |
|---|---|
| Saber o que o modelo é e quanto ele acerta | [modelo/](modelo/index.md) |
| Entender como a inferência funciona | [motor/](motor/index.md) |
| Retomar o treino ou fazer finetuning | [treino/](treino/index.md) |
| Otimizar o runtime, ou saber o que já foi tentado | [otimizacao/](otimizacao/index.md) |
| Ver os números e sob que condição foram medidos | [medicoes/](medicoes/index.md) |
| Saber por que uma arquitetura foi escolhida | [decisoes/](decisoes/index.md) |
| Entender as regras de evidência deste projeto | [disciplina/](disciplina/index.md) |

## O estado, em uma tabela

| | valor | condição |
|---|---|---|
| WER | **15,99%** | FLEURS pt_br `test[0:100]`, greedy CTC, máquina ociosa |
| CER | **7,30%** | idem |
| RTFx | **40,0×** | i7 híbrido, ONNX int8 |
| Publicado | `paulohenriquevn/jvscribe` | HuggingFace, privado |

## As três coisas que a intuição erra aqui

1. **O modelo não é streaming** — é não-causal, e cada atualização reprocessa a janela inteira.
   Ver [modelo/nao-e-streaming.md](modelo/nao-e-streaming.md).
2. **O matmul quantizado é só 24,4% do custo** — mais de 40% é elementwise.
   Ver [medicoes/m6-profile-por-operador.md](medicoes/m6-profile-por-operador.md).
3. **Um número de corrida única não é evidência** — este projeto errou três vezes assim.
   Ver [disciplina/nunca-concluir-de-uma-corrida.md](disciplina/nunca-concluir-de-uma-corrida.md).

## Histórico

Mudanças em ordem cronológica: [log.md](log.md).
