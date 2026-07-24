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

O critério 2 combina duas coisas que M0 **não** entrega, por razões distintas — e é
importante separá-las com honestidade (a análise anterior as fundia numa claim
asseverativa de "impossibilidade" que não mediu, exatamente o erro de método que
`asr-evidence-discipline.md` § 2 proíbe):

1. **Transcrição (texto).** Requer o decode TDT completo (encoder → decoder_joint →
   loop autorregressivo → tokens). Esse decoder é específico da arquitetura do
   modelo e está **`BLOQUEADO POR M2`** (`asr-evidence-discipline.md` § 0). É uma
   **decisão de escopo**, não uma medição: M0 não constrói decoder descartável.

2. **Real-time sustentado por 5 min sem crescimento de backlog.** A viabilidade
   real-time do modelo completo de 600M nesta CPU é **`[DESCONHECIDO]`** — não
   medida em M0. O custo do decoder autorregressivo (a parte cara) não foi medido
   porque o decoder está bloqueado por M2.

O que **está** medido, e honestamente, é apenas o **forward pass do encoder**:
RTF ≈ 0,04 em uma passagem `[MEDIDO — n=1, sem warmup, grafo não-otimizado —
encanamento apenas]`. Esse número diz que o **encoder** sozinho é rápido; **não**
diz nada sobre o modelo completo com decode, que é onde mora o custo real de um
transducer. Concluir "real-time é impossível" a partir daqui excederia a evidência
tanto quanto concluir "real-time é fácil" — ambos são `[DESCONHECIDO]` até medir o
decode, o que M2 desbloqueia.

A hipótese que motiva o projeto (um modelo de 600M não fecha real-time em CPU
commodity com o pipeline completo — diarização + P&C + decode somados) permanece
**hipótese rotulada** a validar por medição, não fato estabelecido em M0
(`PRD.md` § 1, `deep-research-arquiteturas-alternativas.md`).

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
~80M streaming), não a M0 — por **decisão de escopo**: M0 não constrói o decoder
(bloqueado por M2), logo não há como produzir texto nem medir o custo real-time do
modelo completo. Isso é distinto de afirmar que o real-time é impossível: essa
viabilidade é `[DESCONHECIDO]` e será medida quando o decode existir.

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

## Medição que M0 produz — e o que ela NÃO diz

O forward pass do **encoder** de 600M no i7-1355U roda a **RTF ≈ 0,04**
`[MEDIDO — n=1, sem warmup, grafo não-otimizado — encanamento apenas]`. Ou seja: o
encoder sozinho é ~25× mais rápido que real-time nesta CPU.

**Este número não sustenta a tese do projeto — e é honesto reconhecer isso.** O
custo real de um transducer está no **decode autorregressivo**, não no encoder. Com
o decoder bloqueado por M2, o custo do modelo *completo* é `[DESCONHECIDO]`. A
evidência de M0 mostra apenas que a fronteira features→encoder funciona e é barata;
a viabilidade real-time do sistema completo (encoder + decode + P&C + diarização)
fica para medição em M2-M6, que é onde a tese se confirma ou se refuta com número.
