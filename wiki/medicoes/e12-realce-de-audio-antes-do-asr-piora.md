---
type: medicao
title: E12 — realçar o áudio antes do ASR piora, e a subtração espectral é catastrófica
description: >-
  Três técnicas de realce testadas no recorte mais difícil (NURC-SP quality=low). Todas pioram.
  Subtração espectral custa +15,72 p.p. Confirma localmente um achado consolidado da literatura.
tags: [medicao, realce, denoising, pre-processamento, nurc, e12]
timestamp: 2026-08-01T00:00:00Z
---

# E12 — dá para melhorar o áudio antes de entregar ao modelo?

## A pergunta

Se o áudio ruim custa WER (E11 mostrou que banda estreita custa ~6 p.p.), a ideia natural é
**consertar o sinal antes do reconhecedor**. É o que o dono perguntou, e é o que a intuição manda.

## Evidência

`[MEDIDO]` NURC-SP `quality=low` (o recorte mais difícil que este projeto mediu), n=100, greedy,
régua estrita:

| tratamento | WER | Δ |
|---|---|---|
| **nenhum (cru)** | **50,20%** | — |
| pré-ênfase 0,97 | 50,36% | +0,16 |
| realce de agudos +12 dB acima de 1500 Hz | 50,44% | +0,24 |
| **subtração espectral** (α=1,5, ruído dos 200 ms iniciais) | **65,92%** | **+15,72** |

**As três pioram.** As duas equalizações são praticamente neutras (dentro do ruído); a subtração
espectral é **catastrófica** — 31% relativo de degradação.

## Não é a primeira vez neste projeto

O `probes/tta_feature_align_probe.py` (DISC-05) já tinha tentado a mesma ideia no domínio das
features — transformação afim global por mel-bin para trazer o domínio telefônico de volta às
estatísticas de wideband. Resultado registrado: **−24,6 p.p.**

⚠️ **Esse número vive apenas num docstring**, citado de segunda mão em
`probes/blank_penalty_probe.py`. Não há artefato dele em `wiki/medicoes/`. Um resultado negativo
dessa magnitude precisa estar na wiki, não escondido num comentário — enquanto não estiver, a
mesma ideia será reproposta.

## Por que piora — o mecanismo

`[LITERATURA]` verificado em 2026-08-01. O achado é consolidado e recente:

| fonte | achado |
|---|---|
| [`arXiv:2512.17562`](https://arxiv.org/abs/2512.17562) — *When De-noising Hurts* | realce degrada ASR **em todas as condições de ruído e em todos os modelos** testados |
| [`arXiv:2603.04710`](https://arxiv.org/pdf/2603.04710) — *When Denoising Hinders* | separação/denoising piora ASR zero-shot |
| [`arXiv:2501.02452`](https://arxiv.org/pdf/2501.02452) | o conserto é **treinar junto** (módulo de ponte), não encaixar um realçador pronto |

O mecanismo é sempre o mesmo: **o realce troca uma degradação que o modelo já viu no treino por
um artefato que ele nunca viu.** Modelos ponta-a-ponta modernos já são robustos a ruído natural; o
"musical noise" da subtração espectral, a descontinuidade espectral e a perda de pistas acústicas
são um domínio novo, e pior que o original.

Nossos 50,20% de baseline são a prova disso na direção positiva: o modelo aguenta um áudio com
99% da energia abaixo de 1,5 kHz e SNR de 17,8 dB. Ele não aguenta o que a subtração espectral faz
com esse mesmo áudio.

## Conclusão

**Realce genérico pré-ASR está refutado para este sistema.** Não é "não tentamos direito" — é o
resultado esperado pela literatura, reproduzido aqui e já reproduzido antes em outro domínio.

O que a literatura aponta como caminho que funciona é **outro**: treinar o realçador **junto** com
o reconhecedor, ou treinar o reconhecedor **na condição degradada** (augmentação). Os dois exigem
GPU e mudam o modelo — não são pré-processamento.

## Limitações

- **Três técnicas clássicas, não neurais.** Modelos de realce neural (DeepFilterNet, DNS-challenge)
  **não** foram testados. A literatura acima os inclui no achado negativo, mas isso é
  `[LITERATURA]`, não medição nossa. Um realçador neural forte poderia se comportar diferente — e
  custaria orçamento de RTFx que o E7 mostrou não render por outras vias.
- **n=100, um recorte, greedy.** Suficiente para um efeito de 15 p.p.; insuficiente para afirmar
  que os +0,16 e +0,24 das equalizações são reais e não ruído.
- **Não testamos extensão de banda (BWE).** É a técnica que ataca diretamente o fator que E11
  mediu como causal. Continua `[DESCONHECIDO]`, e é a única desta família que eu ainda
  investigaria — com a expectativa temperada por tudo acima.

---

# Adendo — extensão de banda (BWE): a exceção que eu queria investigar, e ela também cai

O corpo deste documento deixou BWE como `[DESCONHECIDO]` e como a única técnica da família que
valia investigar, porque ataca **o fator que o E11 mediu como causal**. Foi testada.

## Desenho: teto e piso conhecidos

Testar BWE direto no NURC-SP não seria interpretável — não se sabe quanto seria "recuperar tudo".
O desenho correto **degrada um sinal bom e tenta recuperá-lo**, porque aí os dois extremos são
medidos:

- **teto** = FLEURS íntegro (o que se recuperaria num mundo perfeito)
- **piso** = FLEURS com passa-baixa a 1500 Hz (o perfil do NURC-low, medido em E11)
- **tratamento** = piso + BWE

## Evidência

`[MEDIDO]` FLEURS n=60, greedy, régua estrita:

| condição | WER |
|---|---|
| **TETO** — íntegro | **14,63%** |
| **PISO** — passa-baixa 1500 Hz | **20,70%** |
| piso + BWE por **espelhamento espectral** (decaimento 6 dB) | **40,26%** |
| piso + BWE por **geração de harmônicos** (retificação de meia-onda) | **31,49%** |

Nenhuma recupera. As duas **quase dobram** o WER em relação ao piso já degradado — o espelhamento
sai 19,6 p.p. **abaixo** do sinal que ele deveria melhorar.

## A leitura

**Banda sintética é pior que banda ausente.**

Isso não é acidente das duas implementações; é a mesma lei do corpo deste documento, na forma mais
nítida que apareceu. Quando a banda alta some, os filtros mel correspondentes ficam **silenciosos**
— um estado que o modelo encontra o tempo todo em fala real (fonemas surdos, pausas, canais
estreitos) e trata com graça. Quando a banda alta é **fabricada**, esses filtros ficam **altos e
errados** — energia que não corresponde a nenhum fonema. O modelo não tem defesa contra isso.

Dito de outro modo: **o reconhecedor lida melhor com informação faltando do que com informação
inventada.** Essa assimetria é a explicação unificada de E12 e deste adendo.

## O que isto NÃO refuta

⚠️ **BWE neural continua não testado.** Espelhamento e harmônicos fabricam banda alta plausível
*espectralmente* e errada *foneticamente*. Um modelo neural treinado em fala real aprende a
relação estatística verdadeira entre banda baixa e alta, e poderia fazer melhor. Este resultado
**estreita** a questão, não a fecha.

O que ele faz é mudar o custo-benefício, e três fatos pesam contra seguir:

1. O estado da arte (AudioSR, NVSR, UniverSR) é **difusão ou vocoder neural**, pesado — e o E7 já
   mostrou que orçamento extra de CPU não compra acurácia por vias óbvias.
2. Esses modelos otimizam **qualidade perceptual**, e a própria literatura de ABE registra que
   *"critérios perceptuais podem não ser ótimos para ASR"* — é literalmente a distinção que este
   experimento acabou de exibir.
3. A direção que a literatura aponta como funcional ([`arXiv:2501.02452`](https://arxiv.org/pdf/2501.02452))
   é **treinar junto**, não encaixar pronto.

## Consequência: a família de pré-processamento está fechada

Somando o corpo e este adendo, com medição própria em cada caso:

| técnica | resultado |
|---|---|
| pré-ênfase | +0,16 p.p. |
| realce de agudos | +0,24 p.p. |
| subtração espectral | **+15,72 p.p.** |
| alinhamento afim de features (DISC-05) | **−24,6 p.p.** |
| BWE por espelhamento | **+19,56 p.p.** sobre o piso |
| BWE por harmônicos | **+10,79 p.p.** sobre o piso |

**Seis técnicas, seis pioras.** O componente acústico do gap não se ataca antes do modelo. Resta
atacá-lo **dentro** do treino — augmentação na condição degradada, ou treino conjunto — e os dois
exigem GPU e mudam os pesos.
