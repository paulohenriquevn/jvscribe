---
type: ADR
title: Orçamento da correção pós-decode
description: Correção com portão rende 0,27 p.p.; o beam custa 15 ms contra 134 ms de encoder. O caro é barato e o barato rende pouco.
tags: [adr, decoding, correcao, portao, beam, orcamento]
timestamp: 2026-07-31T00:00:00Z
---

# ADR-0005 — Onde investir contra o erro de transcrição

- Status: aceito
- Data: 2026-07-31
- Decisor: dono do projeto
- Protocolo: [`portao-de-confianca-plan.md`](../../knowledge-base/plans/portao-de-confianca-plan.md)

## Contexto

A pergunta que motivou tudo foi específica — *"BACEN sai errado"* — e o dono corrigiu a moldura
cedo: **o problema não é um termo, é o erro de transcrição.** A pergunta virou *onde está a massa
do erro e qual ferramenta alcança cada parte*.

Cinco artigos foram lidos e mapeados
([`composicao-do-erro`](../medicoes/composicao-do-erro-e-o-que-cada-remedio-alcanca.md)). Três
convergem no mesmo achado — o conhecimento externo faz o trabalho, o LLM é embalagem cara — e
nenhum se aplica diretamente: somos CTC greedy, 64M, sem entrada de contexto, RTFx ≥ 6× em CPU.

## As medições que precederam a decisão

### O erro se divide em três terços

`[MEDIDO]` FLEURS pt_br, n=100, WER 16,07%:

| classe | fração | IC95 | ferramenta |
|---|---|---|---|
| `non_word_hyp` | 31,5% | [25,0; 38,4] | lista / léxico |
| `real_word_hyp` | 36,6% | [29,9; 43,1] | só LM alcança |
| `rare_ref` | 31,9% | [25,8; 38,8] | biasing / contexto |

Nenhuma intervenção isolada alcança mais que um terço.

### Existe um portão de confiança, e ele é gratuito

`[MEDIDO]` margem top-1 sobre top-2, mínimo dentro da palavra, extraída do **mesmo** colapso:
custo **+0,31%** do decode. A τ=1,0 sinaliza 11,3% das palavras com precisão **55,9%**
[IC95 49,4; 62,0] contra taxa base 14,3% — os seis limiares medidos separam.

### Correção com portão funciona, e rende pouco

`[MEDIDO]` no ponto pré-registrado τ=1,0: WER **16,07% → 15,79%**, redução **0,27 p.p.**
[IC95 0,04; 0,54], razão consertou/quebrou **6,0**. O efeito é real (IC exclui zero) e **menor que
a predição** de 0,3 a 1,3 p.p.

### O custo do beam não é o obstáculo que se supunha

`[MEDIDO]` beam 8 custa **15,2 ms** contra **134 ms** de encoder → RTFx **45,77×** no caminho de
lote, a 7,6× do limiar. Consistente com o profile: `ctc_output` é 0,3% do custo do modelo.

## A decisão

**Investir no caminho do LM, não no da correção pós-decode.**

Três números sustentam isso, e nenhum é intuitivo:

1. **O caro é barato.** A objeção histórica ao beam era custo; ele custa 11% de tempo de parede
   no lote. A alavanca que ataca o **maior** terço estava bloqueada por uma suposição nunca medida.
2. **O barato rende pouco.** A correção com portão entrega 0,27 p.p. — 1,7% relativo — contra os
   10–20% que a literatura atribui a beam + LM.
3. **O portão e o LM são anticorrelacionados.** O portão pega 69% de `non_word_hyp` mas só **32%**
   de `real_word_hyp`, onde o modelo está *confiantemente* errado. **Condicionar o beam à
   confiança — que era a proposta original — destruiria o próprio benefício.**

## Alternativas consideradas

- **Correção pós-decode como caminho principal.** Rejeitada pelo teto medido: 63% (substituições)
  × 50% (sinalizados) × 26% (alcançáveis) ≈ **8% dos erros** com corretor perfeito. Entregou 1,7%
  relativo. Fica como complemento barato, não como aposta.
- **Beam local só nas palavras sinalizadas** (fase E3 do protocolo). **Não executada**: o gatilho
  era a correção falhar, e ela não falhou. A complexidade não foi comprada por nenhum número.
- **Gatear o beam pela confiança** para caber no orçamento. Refutada pela anticorrelação acima —
  e a refutação veio depois de a proposta ter sido feita.
- **RAG/LLM na inferência** ([`arXiv:2502.15264`](https://arxiv.org/abs/2502.15264)). Não se
  aplica: exige decoder autoregressivo, e somos CTC puro.
- **Dados sintéticos de termos raros no treino**
  ([`arXiv:2505.17410`](https://arxiv.org/abs/2505.17410)). Adiada, não rejeitada — ataca
  `rare_ref` na origem e ~90% do ganho daquele artigo veio daí. Precisa de GPU.

## Consequências

### O que fica decidido

- `common/ctc.greedy_palavras` entra no kernel: a confiança é gratuita e tem uso **independente**
  do corretor — marcar palavra incerta na tela do atendente já vale sem corrigir nada.
- O corretor **permanece em `probes/`**. Rendeu, mas 0,27 p.p. não compra promoção a kernel.
- O próximo investimento é **LM + beam**, com `/deps-audit` próprio (nenhum LM instalado).

### O que continua desconhecido, e é grande

- **O custo do beam no TEMPO REAL.** Tudo acima é caminho de lote. Ao vivo o RTFx é 2,5×–4,6×
  contra um RNF-01 de ≥ 3×; **+12% em cima de 3,0× derruba abaixo do limiar**. A § 4 da disciplina
  é explícita: benchmark de componente não transfere — a afinidade de CPU já custou essa lição
  (25% melhor isolada, 46% pior no pipeline).
- **Toda a composição do erro é FLEURS**, leitura de notícias. Em conversa telefônica espontânea
  os três terços podem inverter, e a ordem das apostas com eles.

### A armadilha que fica registrada

A redução cresce monotonicamente com τ e chega a **0,39 p.p. em τ=3,0** — *dentro* da faixa
predita. Reportar esse número seria **escolher o limiar depois de ver o resultado, no mesmo
conjunto**: seleção sobre o test set. O número desta ADR é o do ponto pré-registrado, **0,27**.
Escolher τ exige split separado, e isso não foi feito.

## Nota de método

O protocolo declarava **predição e critério de morte antes de cada corrida**. Duas coisas
aconteceram por causa disso e não teriam acontecido sem:

1. **Uma predição errou** (0,27 contra 0,3–1,3 previstos) e foi registrada como erro. Um alvo
   declarado depois de ver 0,39 teria "confirmado" a hipótese e escondido que o efeito, no ponto
   escolhido antes de olhar, é um terço menor.
2. **Um critério de morte disparou** em τ=0,5, onde o IC [−0,04; 0,38] cruza zero.
