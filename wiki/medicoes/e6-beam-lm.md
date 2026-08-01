---
type: medicao
title: E6 — beam + LM funciona, e entrega um terço do que a literatura prometia
description: >-
  Fusão rasa de n-grama no beam de CTC. Efeito real (IC exclui zero) de 4,7% relativo, contra os
  10–20% pré-registrados a partir da literatura. A predição errou e está registrada como erro.
tags: [medicao, beam, lm, decoding, ctc, fusao-rasa, e6]
timestamp: 2026-08-01T00:00:00Z
---

# E6 — beam search com modelo de linguagem

> **Pré-registro:** [`e6-preregistro-beam-lm.md`](e6-preregistro-beam-lm.md), escrito antes da
> primeira corrida. **Etapa 1** (controle) em [`e6-beam-controle.md`](e6-beam-controle.md).

## O que veio antes, e por que importa para ler este número

**Etapa 1 — o beam SEM LM não move o WER** `[MEDIDO]`: greedy 16,07% contra beam 2/4/8 em 15,99% /
16,11% / 16,18%, **todos os IC95 cruzando zero**. Isso não foi desperdício: é o que permite
**atribuir** o resultado abaixo ao **modelo de linguagem**, e não a "busca melhor". Sem o controle,
a conclusão excederia a evidência.

## Protocolo

| item | valor |
|---|---|
| LM | n-grama ordem 3, *stupid backoff* (Brants et al. 2007), 5.000.380 palavras da Wikipédia pt |
| **vazamento** | **0 sentenças do FLEURS test no corpus do LM** `[MEDIDO]` — auditado no mesmo script que constrói o corpus |
| escolha de α e β | **split de validação** do FLEURS (n=120), 16 configurações varridas |
| ponto de operação | **α=0,1 · β=0,0 · largura 4 — congelados na validação e NÃO tocados no test** |
| conjunto de publicação | FLEURS test **completo**, n=919 |
| IC95 | bootstrap pareado de **utterance**, 10.000 reamostragens |

O split de validação existe exatamente para isto. Varrer α no conjunto onde o número é publicado
seria seleção sobre o test set — o erro que o ADR-0005 registra em τ e que este projeto já pagou.

## Evidência

`[MEDIDO]` FLEURS pt_br test completo, n=919:

| régua | greedy | beam + LM | Δ | IC95 do Δ | relativo |
|---|---|---|---|---|---|
| publicada (dígito na ref) | 14,83% | **14,35%** | +0,48 p.p. | [+0,27; +0,69] | 3,2% |
| forma falada nos dois lados | 12,54% | **11,95%** | +0,59 p.p. | [+0,37; +0,81] | **4,7%** |

Custo: greedy 0,5 ms/utt contra **29 ms/utt** do beam+LM, sobre um encoder de ~134 ms — cerca de
**+22% de tempo de parede** no caminho de lote.

## Conclusão

**O efeito é real e é um terço do prometido.**

Real: o IC95 exclui zero nas duas réguas. Não é ruído, e a etapa 1 garante que vem do LM.

Um terço: a predição pré-registrada era **10–20% relativo** (1,6 a 3,2 p.p.), herdada da
literatura. O medido foi **4,7% relativo**. **A predição errou, e está registrada como erro** — é o
segundo pré-registro deste projeto a errar, depois de E2 (0,27 p.p. contra 0,3–1,3 previstos). Um
alvo declarado *depois* de ver o resultado teria "confirmado" a hipótese.

### Por que menor — hipóteses, não conclusões

Nenhuma destas foi testada; são as candidatas, em ordem de plausibilidade:

1. **O LM é pequeno.** 5M palavras, contra os 10⁸–10¹⁰ típicos dos LMs de ASR que produzem os
   números da literatura. Esta é a explicação mais provável e a mais barata de testar.
2. **Stupid backoff de ordem 3**, contra Kneser-Ney de ordem 4–5 do estado da prática.
3. **Domínio.** Wikipédia é próximo de FLEURS (notícia lida), mas não é o mesmo registro.
4. **α e β vieram de n=120.** Com 16 configurações varridas nesse tamanho, o ponto escolhido pode
   não ser o ótimo — as três melhores configurações ficaram dentro de 0,3 p.p. umas das outras.
5. **Largura 4.** A etapa 1 mostrou que largura não muda nada **sem** LM; com LM isso não foi
   remedido.

### O que isto faz com o alvo de 10%

Partindo de **12,54%** (régua sem artefato), o beam+LM entrega **11,95%**. Faltam **1,95 p.p.**

O pré-registro previa que beam+LM sozinho pudesse fechar o alvo pela ponta otimista da faixa da
literatura. **Não fecha.** Com 4,7% relativo medido, é preciso outra alavanca — e a regra de
composição vale: ganhos não somam. O piso do conjunto é `max(ganhos individuais)` e o teto é a
composição multiplicativa; a soma nunca é defensável sem medir a configuração conjunta.

## Limitações

- **A detecção de vazamento é por igualdade literal.** Sobreposição **parcial** — a mesma sentença
  com uma palavra trocada — não é detectada. O resultado carrega esse caveat.
- **FLEURS é leitura de notícias.** O regime do produto é call center 8 kHz espontâneo. Este ganho
  **não transfere** sem medição própria, e um LM de Wikipédia é pior candidato ainda para fala
  espontânea de atendimento.
- **Caminho de lote.** Os 29 ms/utt são decode sobre posterior pronta, em máquina ociosa. Ao vivo
  há dois canais, subprocessos de captura e reprocessamento de janela: `asr-evidence-discipline`
  § 4 — benchmark de componente não transfere para o sistema.
- **Uma corrida por configuração.** O pareamento por utterance elimina a variância entre
  condições, que é o que sustenta o IC; não substitui repetição para afirmar magnitude fina.
- **16 configurações varridas na validação.** O melhor ponto em validação carrega viés de seleção;
  o número do test set não carrega, porque os hiperparâmetros foram congelados antes.
