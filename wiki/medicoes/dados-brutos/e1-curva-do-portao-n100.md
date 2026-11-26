---
type: Medição
title: E1 — curva do portão de confiança (bruto, n=100)
description: Precisão e recall do portão por limiar, com IC95% bootstrap sobre utterances.
tags: [medicao, dados-brutos, e1, portao, protocolo]
timestamp: 2026-07-31T00:00:00Z
---

# E1 — curva do portão de confiança `[MEDIDO]`

**Data:** 2026-07-31T18:10:00 · **Comando:** `python3 jvscribe/probes/portao_correcao_probe.py --curva --n 100`
**Amostra:** 100 utterances de FLEURS pt_br · 2623 palavras ·
374 erradas → **taxa base 14.3%**
**IC95%:** bootstrap percentil reamostrando **utterances** (2000 reamostragens, seed 20260731)

## Predição pré-registrada

A τ=1,0: precisão ≥ **35%**, com o **limite inferior** do IC95% **acima** da taxa base.

**Critério de morte:** limite inferior encosta na taxa base → o portão é ruído e o protocolo para.

## Resultado

| τ | sinalizado | recall | precisão | IC95% da precisão | ganho | separa? |
|---|---|---|---|---|---|---|
| 0.25 | 3.8% | 18.2% | 68.7% | [59.4; 77.3] | 4.8× | ✅ |
| 0.50 | 6.8% | 29.1% | 61.2% | [53.5; 68.4] | 4.3× | ✅ |
| 1.00 | 11.3% | 44.4% | 55.9% | [49.4; 62.0] | 3.9× | ✅ |
| 1.50 | 14.6% | 53.2% | 52.0% | [46.1; 57.6] | 3.6× | ✅ |
| 2.00 | 18.3% | 62.6% | 48.6% | [43.2; 54.0] | 3.4× | ✅ |
| 3.00 | 24.2% | 73.0% | 43.0% | [38.2; 47.8] | 3.0× | ✅ |

**"Separa"** = o limite inferior do IC95% da precisão fica **acima** da taxa base. É o critério
de morte da fase, não uma observação decorativa.

## Como ler

A precisão sobre zero sinalizados é `—`, não 100%: um τ que não sinaliza nada não mediu nada, e
um ponto perfeito no fim da curva é como se escolhe o τ errado.

A reamostragem é por **utterance**, não por palavra. Palavras da mesma locução são correlacionadas
— mesmo locutor, mesmo áudio, mesmo contexto — e tratá-las como independentes estreitaria o
intervalo artificialmente (falácia § 3 #12).

## Limitações

- **FLEURS é leitura de notícias.** A separação em conversa telefônica espontânea segue
  `[DESCONHECIDO]`. É o limite de todo o protocolo até a fase E5.
- A margem usa o **primeiro** frame de uma emissão repetida. A posterior da trajetória colapsada
  provavelmente separa melhor e **não foi comparada** (Unresolved Question 1 do protocolo).
- Palavras de `insert` no alinhamento contam como erradas; `delete` não aparece — nenhuma palavra
  foi emitida para carregar margem. O portão, por construção, não enxerga deleção.
