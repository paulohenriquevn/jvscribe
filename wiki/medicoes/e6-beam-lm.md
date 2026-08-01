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

### Por que menor — hipóteses, TESTADAS no adendo abaixo

Estas eram as candidatas quando esta seção foi escrita. **Quatro delas foram testadas depois e
caíram** — ver o adendo no fim deste documento. Ficam registradas como estavam, para que a ordem
do raciocínio permaneça auditável:

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

---

# Adendo — por que 4,7%, e por que a predição estava errada na origem

Depois do resultado principal, as cinco hipóteses da seção anterior foram **testadas**, não
deixadas como especulação. Quatro caíram.

## As três variáveis saturaram

`[MEDIDO]` split de **validação** (n=120), greedy = 15,25%, α varrido por condição:

### Tamanho do corpus — satura em ~2,5M palavras

| palavras do LM | tipos | Δ p.p. |
|---|---|---|
| 513.945 | 38.841 | +0,34 |
| 1.270.497 | 64.454 | +0,49 |
| 2.527.218 | 92.418 | **+0,71** |
| 5.000.380 | 137.753 | **+0,71** |

Dobrar de 2,5M para 5M rendeu **exatamente zero**. A hipótese "o LM é pequeno demais" — que era a
minha favorita e a mais barata de testar — **está refutada**. Mais texto da Wikipédia não compra.

### Ordem do n-grama — satura em 3, e a ordem 5 piora

| ordem | largura 4, α=0,1 | largura 8, α=0,1 |
|---|---|---|
| 3 | **+0,71** | +0,64 |
| 4 | **+0,71** | +0,60 |
| 5 | +0,60 | +0,49 |

Mais contexto não ajuda. Contexto de 4 palavras (ordem 5) **atrapalha**.

### Largura do beam — mais busca é PIOR

Largura 8 perde para largura 4 em **todas** as seis combinações. Isso é assinatura de LM mal
calibrado: dando mais candidatos para escolher, ele escolhe pior. Vale contrastar com a etapa 1,
onde a largura era **indiferente** sem LM — o dano vem do LM, não da busca.

### Domínio — teste inconclusivo, e digo que é inconclusivo

| LM | palavras | log-score médio por palavra | Δ p.p. |
|---|---|---|---|
| Wikipédia (fora do domínio) | 5.000.380 | −6,92 | **+0,71** |
| FLEURS train (**no** domínio) | 63.521 | −8,11 | +0,26 |
| os dois juntos | 5.063.901 | −6,88 | +0,71 |

O LM no domínio é pior nas duas medidas — mas tem **80× menos dado**, então este teste **não
separa domínio de volume**. É confundido por construção, e fica registrado como inconclusivo em
vez de ser lido como refutação do domínio.

> O "log-score médio por palavra" **não é perplexidade**: *stupid backoff* não normaliza. Serve
> para comparar os três LMs entre si sobre o mesmo texto, e para nada além disso.

## A causa provável: a predição herdada veio de outro regime

Com corpus, ordem, largura e (parcialmente) domínio descartados, sobra a hipótese estrutural — e
ela explica também **por que a predição de 10–20% estava errada antes de qualquer corrida**.

`[LITERATURA]` verificado em 2026-08-01:

| fonte | ganho relatado | regime |
|---|---|---|
| [HF blog, Wav2Vec2 + 5-grama Europarl](https://huggingface.co/blog/wav2vec2-with-ngram) | ~30% relativo | Wav2Vec2 **nível-caractere**, WER ~27% antes do LM |
| Wav2Vec2 paper, Apêndice C (citado no mesmo blog) | ~80% relativo | modelo treinado em **10 minutos** de dado rotulado |
| [levantamento geral de shallow fusion](https://arxiv.org/pdf/2302.08917) | **~3% relativo típico**, até ~10,5% | modelos acústicos fortes |

O padrão é consistente e conhecido: **quanto mais forte o modelo acústico, menor o ganho do LM
externo.** E há um segundo eixo que agrava: um CTC de **caractere** produz muitas não-palavras, que
o n-grama conserta trivialmente; um CTC de **BPE** já tem o vocabulário restringindo a saída a
sequências de subpalavra plausíveis, então essa parte do ganho **já está internalizada no modelo**.

A composição do erro deste projeto já dizia isso e ninguém leu assim: `non_word_hyp` é **31,5%** —
num CTC de caractere seria bem maior.

**Conclusão do adendo:** os 4,7% medidos estão **acima** do ~3% típico para fusão rasa sobre modelo
acústico forte. O erro não foi do experimento — foi da predição, que herdou uma faixa de
`[LITERATURA]` medida em arquitetura sem parentesco com a nossa. Isso é a falácia § 3 #2 do próprio
contrato de evidência deste projeto, cometida na documentação e repetida por mim ao pré-registrar.

**Correção proposta ao `CLAUDE.md`:** a linha "Beam search + LM no decode — 10–20% relativo
`[LITERATURA]`" está errada para este sistema e deve passar a `[MEDIDO]` 4,7%.
