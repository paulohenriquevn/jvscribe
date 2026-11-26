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

⚠️ **Em 2026-08-01 a régua foi consertada e o conjunto foi corrigido.** Os 15,99% que este índice
anunciava vinham do slice `test[0:100]`, que é uma **amostra alta** — e a régua contava acerto do
modelo como erro. Todo WER agora sai **em par**, com a régua declarada
([`e9`](medicoes/e9-vies-do-normalizador-contra-modelos-de-forma-falada.md)).

| | valor | condição |
|---|---|---|
| WER — comparabilidade externa | **14,83%** | FLEURS test **completo** (919), greedy, régua canônica (sem acento, com dígito) |
| **WER — acurácia de reconhecimento** | **12,75%** | idem, régua estrita (com acento, forma falada nos dois lados) |
| WER com beam + LM | **12,03%** | idem, régua sem acento — na estrita fica ~12,2% `[ESTIMATIVA]` |
| RTFx | **40,0×** | i7 híbrido, ONNX int8, caminho de lote |
| Publicado | `paulohenriquevn/jvscribe` | HuggingFace, privado |

> O número histórico de **15,99%** (`test[0:100]`, régua canônica) continua válido **como aquilo que
> era**: uma amostra de 100 utterances medida com a régua antiga. Duas amostras honestas de 100
> utterances do mesmo conjunto variam de 12,4% a 17,5% — por isso o slice foi aposentado.

## As três coisas que a intuição erra aqui

1. **O modelo não é streaming** — é não-causal, e cada atualização reprocessa a janela inteira.
   Ver [modelo/nao-e-streaming.md](modelo/nao-e-streaming.md).
2. **O matmul quantizado é só 24,4% do custo** — mais de 40% é elementwise.
   Ver [medicoes/m6-profile-por-operador.md](medicoes/m6-profile-por-operador.md).
3. **Um número de corrida única não é evidência** — este projeto errou três vezes assim.
   Ver [disciplina/nunca-concluir-de-uma-corrida.md](disciplina/nunca-concluir-de-uma-corrida.md).

## Histórico

Mudanças em ordem cronológica: [log.md](log.md).
