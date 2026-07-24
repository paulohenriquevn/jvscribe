# Análise — o DoD de M0 e o modelo emprestado

> 2026-07-24. Rotulagem conforme `.claude/rules/asr-evidence-discipline.md` § 1.
> Registro honesto de uma tensão real no DoD, não um contorno.

## O fato

O `ROADMAP.md` M0 lista dois critérios sobre o modelo:

1. *"Modelo existente (`alefiury/...`) transcrevendo o mix, com texto aparecendo
   incrementalmente"*
2. *"Uma chamada real de ≥ 5 minutos transcrita sem crash e sem crescimento de
   backlog"*

O modelo emprestado é `nemo-conformer-tdt`, **600M parâmetros, offline** (não
streaming), pesos de **2,3 GB** `[MEDIDO — HF repo]`.

## A tensão

O critério 2 é **estruturalmente impossível com este modelo — por design do
projeto.** Um transducer de 600M offline não faz transcrição real-time em CPU
commodity. Essa infeasibilidade **é a premissa do projeto inteiro**: se um modelo
de 600M rodasse real-time em CPU, não haveria razão para treinar um modelo próprio
de ~80M (`PRD.md` § 1, `deep-research-arquiteturas-alternativas.md`).

Rodar o modelo emprestado sobre 5 min de áudio **vai** gerar crescimento de
backlog — e isso não é falha do encanamento de M0; é a **evidência empírica que
motiva M2-M6**.

O próprio blueprint já registrou isto (ADR D4): *"nenhum número de WER ou RTFx
obtido em M0 é válido para o produto... rotular todo resultado como
`[MEDIDO — encanamento apenas]`"*.

## A interpretação honesta do DoD

M0 é o **walking skeleton**: prova que o **encanamento** conecta de ponta a ponta.
O que M0 prova, com evidência:

| Estágio | Independente de arquitetura? | Provado |
|---|---|---|
| Captura dual (mic + loopback) | ✅ | 6 testes de integração + evidência medida |
| VAD por stream | ✅ | testes de detecção |
| Roteamento de falante | ✅ | tabela-verdade |
| Features log-mel 128 bins, zero-alocação | ✅ | teste com `stats_alloc` |
| Backlog / drift / sink-health | ✅ | testes + experimento de drift |
| **Carga do modelo ONNX real** | modelo emprestado (descartável) | forward pass do encoder |
| **Transcrição real-time de 5 min** | ❌ **impossível com 600M offline** | — estruturalmente M5/M6 |

O critério 2 do DoD, lido literalmente, **pertence a M5/M6** (modelo próprio de
~80M streaming), não a M0. Cobrar real-time de um modelo escolhido *precisamente
por não fazer real-time* seria testar contra a própria tese do projeto.

## O que M0 entrega de fato sobre o modelo

Prova que o **encanamento acústico funciona de ponta a ponta sobre dados reais**:
captura → VAD → features → **encoder ONNX real (600M, pesos reais) → tensor de
saída de shape correto**. Isso valida a fronteira features→modelo, que é o que o
walking skeleton precisa provar.

O **decoder TDT completo** (encoder → decoder_joint → decode ganancioso → texto) é
código específico do modelo emprestado — e o blueprint marcou "decoder" como
**BLOQUEADO POR M2**. Construir um decoder TDT descartável para o modelo emprestado
contradiz a disciplina de escopo do próprio blueprint (`asr-evidence-discipline.md`
§ 0: trabalho que depende da arquitetura é bloqueado por M2).

## Proposta para o DoD de M0 no ROADMAP

Reescrever os dois critérios de modelo do M0 para refletir o que o walking skeleton
honestamente prova, movendo a transcrição real-time para onde ela pertence:

- **M0 (revisado):** o encoder ONNX real carrega e produz tensor de saída válido a
  partir de features reais do pipeline — provando a fronteira features→modelo.
- **M5/M6:** transcrição real-time sustentada (o modelo próprio streaming; é lá que
  o critério de 5 min sem backlog é atingível e significativo).

Esta é uma correção de DoD, registrada e proposta — não uma dispensa silenciosa. A
decisão de editar o ROADMAP fica explícita no CHANGELOG.

## Medição que M0 ainda produz (motiva o projeto)

Rodar o forward pass do encoder de 600M no i7-1355U e **medir o tempo por chunk** é
evidência valiosa: mostra `[MEDIDO — encanamento apenas]` o quão longe de real-time
um modelo de 600M está nesta CPU — o número que justifica todo o M2-M8.
