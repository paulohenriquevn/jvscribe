---
type: Medição
title: E1 — o portão de confiança separa, e o IC prova
description: τ=1,0 → precisão 55,9% [IC95 49,4; 62,0] contra taxa base 14,3%. Todos os seis limiares separam.
tags: [medicao, e1, confianca, portao, ic, protocolo]
timestamp: 2026-07-31T00:00:00Z
---

# E1 — o portão de confiança `[MEDIDO]`

Data: 2026-07-31 · `git dbff0ea` → E1 · FLEURS pt_br, n=100 · i7-1355U, load 1,25.
Fase E1 do protocolo pré-registrado do portão de confiança
([`post-decode-budget.md`](../../docs/paper/post-decode-budget.md) § 8).
Bruto: [`dados-brutos/e1-curva-do-portao-n100.md`](dados-brutos/e1-curva-do-portao-n100.md).

## Hipótese

A margem entre primeiro e segundo colocado, reduzida ao mínimo dentro da palavra, separa palavra
certa de palavra errada — e a separação **sobrevive ao intervalo de confiança**.

**Predição pré-registrada:** a τ=1,0, precisão ≥ **35%**, com o limite **inferior** do IC95%
acima da taxa base.
**Critério de morte:** limite inferior encosta na taxa base → o portão é ruído; o protocolo
inteiro para.

## Evidência

2623 palavras, 374 erradas → **taxa base 14,3%**. IC95% percentil, bootstrap reamostrando
**utterances** (2000 reamostragens, seed fixa).

| τ | sinalizado | recall | precisão | IC95% | ganho | separa? |
|---|---|---|---|---|---|---|
| 0,25 | 3,8% | 18,2% | **68,7%** | [59,4; 77,3] | 4,8× | ✅ |
| 0,50 | 6,8% | 29,1% | 61,2% | [53,5; 68,4] | 4,3× | ✅ |
| **1,00** | **11,3%** | **44,4%** | **55,9%** | **[49,4; 62,0]** | **3,9×** | ✅ |
| 1,50 | 14,6% | 53,2% | 52,0% | [46,1; 57,6] | 3,6× | ✅ |
| 2,00 | 18,3% | 62,6% | 48,6% | [43,2; 54,0] | 3,4× | ✅ |
| 3,00 | 24,2% | 73,0% | 43,0% | [38,2; 47,8] | 3,0× | ✅ |

Nos **seis** limiares o limite inferior do IC fica acima da taxa base. A τ=1,0 ele está a
**3,5×** da base — não é margem apertada.

### A reamostragem é por utterance, de propósito

Palavras da mesma locução são correlacionadas: mesmo locutor, mesmo áudio, mesmo contexto.
Reamostrá-las como independentes estreitaria o intervalo artificialmente — a falácia § 3 #12 com
uma casa decimal a mais. `tests/test_portao_confianca.py` tem um teste que falha se a unidade
voltar a ser a palavra.

### Uma divergência de contagem que vale explicar

A medição exploratória que originou o protocolo reportou precisão **49,4%** sobre base **10,3%**;
aqui são **55,9%** sobre **14,3%**. Não é ruído — é **definição de erro**:

| | palavras | erradas | base |
|---|---|---|---|
| exploratória, só substituições | 2506 | 257 | 10,3% |
| **E1, substituições + inserções** | **2623** | **374** | **14,3%** |

Palavra inserida pela hipótese **é** erro e o portão deveria pegá-la; excluí-la subestimava tanto
a base quanto a precisão. A contagem de E1 reproduz **exatamente** a primeira medição exploratória
(2249 certas + 374 erradas = 2623), o que serve de verificação cruzada do instrumento.

## Conclusão — e apenas isto

**Predição confirmada.** 55,9% ≥ 35%, e o limite inferior (49,4%) está muito acima da base
(14,3%). O portão não é ruído. **E1 passa; E2 está liberada.**

O ponto de operação com melhor razão é τ=0,25 (precisão 68,7%), mas ele sinaliza só 3,8% das
palavras e pega 18,2% dos erros. **τ=1,0 é o joelho da curva**: 11,3% sinalizado, 44,4% de recall,
precisão ainda acima de 55%. É o valor que E2 usará como padrão, com varredura.

## O que esta medição NÃO diz

- **FLEURS é leitura de notícias.** A separação em conversa telefônica espontânea segue
  `[DESCONHECIDO]` (falácia § 3 #6). Limite de todo o protocolo até E5.
- **Detectar não é consertar.** Precisão de 55,9% significa que **44,1% do que o portão sinaliza
  está correto** — um corretor que mexa em tudo que é sinalizado quebra quase metade do que toca.
  É E2 que responde se sobra ganho.
- **O portão não enxerga deleção.** Palavra que o modelo não emitiu não carrega margem. Deleções
  são parte dos 37% do erro que nenhum corretor palavra-a-palavra alcança.
- **A margem é uma confiança grosseira.** Usa o primeiro frame de uma emissão repetida; a
  posterior da trajetória colapsada provavelmente separa melhor e **não foi comparada** (Unresolved
  Question 1 do protocolo).
- n=100, uma corrida. O IC cobre a variância entre locuções, não entre corridas — o decode é
  determinístico dado o modelo.

## Aprendizado para o loop

> **Um teste meu falhou por premissa errada, não por bug.** O fixture do bootstrap usava locuções
> onde toda palavra sinalizada estava errada — precisão 1,0 em qualquer reamostragem, degenerada
> por construção. Foi corrigido para misturar locuções com precisões diferentes, que é o que a
> reamostragem por utterance precisa capturar.

É a quarta vez nesta linha de trabalho que a expectativa estava errada e o código certo. O padrão
já é claro o bastante para virar hábito: **antes de acusar o código, verificar se o fixture
consegue exibir o fenômeno que o teste afirma medir.**
