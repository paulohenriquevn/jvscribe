---
type: medicao
title: E11 — a banda é causa, e é minoria; augmentação alcança ~18% do gap
description: >-
  Ablação controlada de passa-baixa no MESMO áudio. Limitar o FLEURS ao perfil espectral do NURC-SP
  custa +6,07 p.p. — real, e apenas um sexto dos ~34 p.p. que separam os dois corpora.
tags: [medicao, banda, augmentacao, dominio, nurc, ablacao, e11]
timestamp: 2026-08-01T00:00:00Z
---

# E11 — a banda explica quanto do gap? Uma ablação controlada

## A pergunta

O dono perguntou se dá para **caracterizar o áudio difícil e aplicar essas características via
augmentação ao treino**. A resposta depende de uma coisa que não se responde por argumento: **quanto
do gap é acústico?** Augmentação só alcança o que é acústico. Espontaneidade, sotaque e conteúdo
ela não simula.

## O que motivou a hipótese da banda

`[MEDIDO]` perfil espectral por corpus (mediana, com remoção de DC):

| conjunto | banda 90% | **banda 99%** | SNR proxy | WER estrita |
|---|---|---|---|---|
| FLEURS | 770 Hz | **5494 Hz** | 34,7 dB | 12,75% |
| LapsBM | 833 Hz | **4405 Hz** | 22,9 dB | 9,71% |
| NURC-SP high | 710 Hz | **1588 Hz** | 21,2 dB | 32,63% |
| NURC-SP low | 656 Hz | **1452 Hz** | 17,8 dB | 49,22% |

**A banda acompanha o WER; o SNR não.** LapsBM e NURC-high têm SNR quase igual (22,9 vs 21,2 dB) e
WER de 9,7% contra 32,6%. O que os separa é banda: 4405 contra 1588 Hz.

> ⚠️ **Um defeito do próprio instrumento, corrigido antes de concluir.** A primeira medição deu
> `banda90 = 0 Hz` e SNR 1,2 dB para o LapsBM — 90% da energia no bin DC. Aqueles arquivos têm
> **offset DC**, e o medidor não o removia; todo frame ficava com energia alta e o "SNR" colapsava.
> Sem remover a média antes da FFT, a conclusão teria sido o oposto da correta.

## A ablação — a única forma de separar causa de coincidência

Os quatro corpora diferem em **tudo** (espontaneidade, época, locutores, conteúdo). Correlação
entre eles não estabelece causa. A intervenção controlada aplica passa-baixa ao **mesmo áudio**:

`[MEDIDO]` 60 utterances do FLEURS, greedy, régua estrita, filtro Butterworth ordem 8 (zero-fase):

| corte | WER | Δ |
|---|---|---|
| íntegro | 14,63% | — |
| **3400 Hz** (banda telefônica) | 15,37% | **+0,74** |
| **1800 Hz** (perfil NURC-high) | 19,08% | **+4,45** |
| **1500 Hz** (perfil NURC-low) | 20,70% | **+6,07** |

## Conclusão

### A banda é causa — e é minoria

Limitar o FLEURS ao perfil do NURC-low leva o WER de 14,63% a **20,70%**. Se a banda explicasse o
gap, o FLEURS filtrado deveria chegar perto dos **49,22%** do NURC-low. Chega a 20,7%.

**A limitação de banda responde por cerca de 6 dos ~34 p.p. que separam os dois corpora — perto de
um sexto.** Os outros ~5/6 são espontaneidade, locutores, época e conteúdo. **Augmentação não
simula nenhum deles**: não existe filtro que transforme leitura fluente em fala hesitante,
autocorrigida e sobreposta.

> A decomposição supõe aditividade entre os fatores, que **não é garantida** — banda estreita pode
> custar mais em fala espontânea do que em leitura. A fração "um sexto" é ordem de grandeza, não
> partição exata.

### O achado colateral que contraria a intuição do produto

**Banda telefônica sozinha custa apenas +0,74 p.p.** (14,63% → 15,37%). O nosso produto opera em
8 kHz, e a degradação medida no CORAA telefônico é de ~6 p.p. — muito acima disso. Logo **o custo
da telefonia não é principalmente a banda**: é codec (G.711/GSM/Opus), AGC, crosstalk e a
espontaneidade da conversa. Augmentação por passa-baixa isolada endereça a menor parte.

## Resposta à pergunta original

**Sim, faz sentido científico, e é uma família estabelecida** (*multi-condition training* /
augmentação casada ao domínio alvo). Mas o dimensionamento honesto é:

| componente do gap | augmentação alcança? | tamanho medido |
|---|---|---|
| limitação de banda | **sim** — passa-baixa casada ao perfil | ~6 p.p. de ~34 |
| ruído de fundo / SNR | sim — MUSAN etc. | **não é o driver** (SNR não separa os corpora) |
| codec telefônico | sim — cadeia já existe em `common/audio/` | não medido isoladamente |
| **espontaneidade** | **não** | **a maior parte** |
| sotaque, época, conteúdo | não | não separado |

E há uma cicatriz deste repositório que precisa entrar na conta: **full-finetune com codec-aug já
colapsou o greedy para ~98%** `[MEDIDO]` duas vezes, o que motivou o `run_ft_freeze.sh`. Augmentação
aqui não é interruptor grátis — é o eixo que já derrubou runs inteiros.

## Limitações

- **n=60** para a ablação. Suficiente para um efeito de 6 p.p. dentro de comparação pareada;
  insuficiente para afirmar a forma da curva entre 1800 e 3400 Hz.
- **Passa-baixa não é a degradação real do NURC-SP.** Fita analógica adiciona ruído correlacionado,
  wow/flutter e distorção não-linear que um Butterworth não reproduz. A ablação isola **um** fator,
  não recria o domínio.
- **A causa do gap `quality=high` vs `low` dentro do NURC-SP continua `[DESCONHECIDO]`.** A
  diferença acústica medida (1,7 dB de SNR, 9% de banda) é pequena demais para explicar 16,6 p.p.,
  e marcadores de hesitação são ~1,4% dos tokens nos **dois** recortes. Não sei o que dirige o gap
  e não vou inventar.
