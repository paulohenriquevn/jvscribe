---
type: medicao
title: Pré-registro E6 — beam search e modelo de linguagem
description: Predições e critérios de morte escritos ANTES de rodar. O beam nu é um controle, não um candidato.
tags: [medicao, pre-registro, beam, lm, decoding, ctc]
timestamp: 2026-07-31T00:00:00Z
---

# E6 — pré-registro: beam search + LM

> Escrito **antes** de qualquer corrida. O ADR-0005 registra por que isto existe: o protocolo
> declara predição e critério de morte antes de medir, e foi essa disciplina que pegou uma
> predição errada em E2 (0,27 medido contra 0,3–1,3 previsto) em vez de escondê-la.

## Contexto

O ADR-0005 nomeou **LM + beam** como o próximo investimento, com dois números por trás:

- `real_word_hyp` é **36,6%** [IC95 29,9; 43,1] do erro — o maior terço, e o único que nenhuma
  outra fase toca. É "a palavra existe, mas está errada": só contexto conserta.
- O custo do beam não é o obstáculo que se supunha: beam 8 custa **15,2 ms** contra **134 ms** de
  encoder `[MEDIDO]` E4, RTFx 45,77× no lote.

## Desenho: posteriores cacheadas, comparação pareada

O encoder domina o custo e é **idêntico** para todos os decoders. Cacheando `log_probs` das N
utterances uma vez, todo decoder decide sobre os **mesmos frames** — a comparação fica pareada por
construção, sem ruído de corrida entre condições. Isto não é otimização: é o que remove a variância
que já enganou este projeto três vezes.

## H1 — o beam SEM LM não muda o WER (controle, não candidato)

**Predição:** |Δ WER| < 0,2 p.p. e o IC95 do delta **cruza zero** para larguras 2, 4 e 8.

**Razão:** CTC assume independência condicional entre frames. Sem LM, o score do beam é a mesma
distribuição que o greedy maximiza quadro a quadro, e as posteriores de CTC são *peaky* — o beam
reencontra o caminho greedy. O próprio `probes/beam_ctc_probe.py` já documentava essa expectativa
antes desta corrida.

**Por que medir algo que se espera nulo:** para atribuir corretamente o ganho depois. Se o beam nu
render zero e beam+LM render X, então X **é do LM**, e o beam é veículo. Sem este controle, um
ganho de beam+LM seria creditado à "busca melhor" — conclusão que excede a evidência.

**Critério de morte de H1:** se o beam nu render ganho significativo (IC95 exclui zero), a premissa
teórica está errada neste modelo e o pré-registro do LM precisa ser reescrito antes de continuar.

## H2 — beam + LM entrega 10–20% relativo

**Predição:** WER 15,99% → **12,8%–14,4%** (ganho de 1,6 a 3,2 p.p.), IC95 do delta excluindo zero.

**Proveniência da faixa:** `[LITERATURA]` — é a faixa que o CLAUDE.md registra para beam+LM, e é
**predição herdada, não medida aqui**. Se cair fora, o erro é da transferência de literatura para
este modelo/língua, e isso é resultado publicável.

**Critério de morte:** IC95 do delta cruzando zero → o LM não entrega neste sistema, e a aposta do
ADR-0005 estava errada. Registrar e voltar para a composição do erro.

## H3 — o ganho concentra em `real_word_hyp`

**Predição:** a redução em `real_word_hyp` é maior que em `non_word_hyp`, em pontos percentuais da
classe.

**Por que importa mais que o WER agregado:** se o ganho vier de `non_word_hyp`, o LM está fazendo o
trabalho que a correção pós-decode com portão já fazia por 0,27 p.p. e quase de graça — e as duas
técnicas **se canibalizam** em vez de somar. Esta é a hipótese que decide se as apostas compõem.

## O invariante que pode invalidar tudo — vazamento pelo LM

⚠️ **FLEURS pt_br deriva do FLoRes-101, de origem Wikipédia/Wikinews.** Um LM treinado em dump de
Wikipédia em português pode conter **literalmente as sentenças do test set**. O resultado seria um
WER espetacular e sem valor — a versão em LM da falácia § 3 #10 (pseudo-label no test set).

**Regra desta fase, inegociável:** o texto de treino do LM sai das transcrições de **treino** do
próprio projeto (Common Voice pt / MLS pt / CORAA train), que são disjuntas do FLEURS test por
construção. Qualquer corpus externo exige verificação explícita de sobreposição de sentença contra
o test set **antes** de treinar, e o resultado dessa verificação entra no relatório.

**Teste de sanidade obrigatório:** contar quantas sentenças do FLEURS test aparecem literalmente no
corpus do LM. O número tem de ser **0**, e tem de estar publicado no relatório — não basta afirmar
que não há vazamento.

## O que esta fase NÃO decide

- **Nada sobre tempo real.** Tudo aqui é caminho de lote. Ao vivo o RTFx medido é 3,58× contra um
  RNF-01 de 3×, e `asr-evidence-discipline` § 4 é explícita: benchmark de componente não transfere.
- **Nada sobre call center.** FLEURS é leitura de notícias. O regime do produto é 8 kHz espontâneo,
  e o WER lá é `[DESCONHECIDO]`.
- **O ponto de operação.** Escolher largura de beam e peso do LM olhando o resultado no mesmo
  conjunto é seleção sobre o test set — o erro que o ADR-0005 registra em τ. Qualquer escolha de
  hiperparâmetro exige split separado.
