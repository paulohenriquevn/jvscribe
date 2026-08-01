---
type: medicao
title: E8 — a composição do erro na régua corrigida, e o balde que ninguém tinha visto
description: >-
  Split S/D/I medido pela primeira vez no projeto. Os "três terços" são terços das substituições,
  não do erro. Inserção é o terceiro maior balde (18,5%) e o viés de blank não o alcança.
tags: [medicao, composicao-do-erro, insercao, delecao, blank, regua, e8]
timestamp: 2026-08-01T00:00:00Z
---

# E8 — recontando o erro depois que a régua foi consertada

## Por que refazer

Toda decisão sobre "qual terço atacar" vinha de `composicao-do-erro-e-o-que-cada-remedio-alcanca.md`
— medido em **n=100** e com a **régua defeituosa**, na qual a classe `número` marcava 99% de erro
por artefato e carregava 12,4% da massa. Continuar a decidir sobre aqueles números seria decidir
sobre contaminação conhecida.

Além disso, o projeto **nunca reportou o split substituição/deleção/inserção**. Sem ele, "os três
terços" parecem uma partição do erro. Não são.

## Evidência

`[MEDIDO]` FLEURS pt_br test **completo** (n=919), greedy, léxico PT-BR de 436.107 formas
(`/usr/share/dict/brazilian` ∪ hunspell).

| | régua publicada | **régua corrigida** |
|---|---|---|
| WER | 15,02% | **12,72%** |
| erros / palavras | 3.224 / 21.471 | 2.779 / 21.853 |
| **substituição** | 63,1% | **68,6%** |
| **deleção** | 10,1% | **12,9%** |
| **inserção** | 26,8% | **18,5%** |

E a composição das substituições, agora expressa também como fração do erro **total**:

| classe | % das substituições | **% do erro TOTAL** |
|---|---|---|
| `real_word_hyp` | 38,3% | **26,3%** |
| `non_word_hyp` | 35,9% | **24,6%** |
| `rare_ref` | 25,8% | **17,7%** |

## Conclusão

### 1. Os "três terços" são terços de 68,6% do erro, não do erro

Somados, os três valem **68,6%** da massa. Os outros **31,4% são inserção e deleção** — e nenhuma
técnica de *substituição* (corretor lexical, reparo fonético, biasing por palavra) os alcança. Para
consertar uma inserção é preciso **apagar**, não trocar; e o portão de confiança, por construção,
**não enxerga deleção**.

Isso reprecifica todo teto calculado sobre os três terços. O teto de um corretor perfeito de
substituição não é 100% do erro — é 68,6% dele.

### 2. A régua quebrada distorcia exatamente as duas coisas que guiavam decisão

- `rare_ref` caiu de 34,2% para **25,8%** das substituições. Um dígito não está no léxico, então
  toda referência com número era classificada como "palavra rara" — a classe alvo do *biasing*
  estava inflada por artefato de normalização.
- Inserção caiu de 26,8% para **18,5%**. `2005` → `dois mil e cinco` conta como 1 substituição
  **mais 3 inserções**; o artefato fabricava inserções em massa.

Ou seja: a régua não inflava o WER de forma neutra. Ela inflava **seletivamente** as duas classes
sobre as quais o projeto vinha decidindo onde investir.

### 3. Inserção é o terceiro maior balde, e o remédio óbvio não funciona

`[MEDIDO]` validação (n=200), régua corrigida, viés somado ao logit de blank antes do argmax:

| viés | WER | subs | deleções | inserções |
|---|---|---|---|---|
| −1,0 | 14,09% | 431 | 54 | 129 |
| **0,0** | **13,47%** | 409 | 78 | 100 |
| +0,5 | 13,58% | 418 | 91 | 83 |
| +1,0 | 13,97% | 426 | 110 | 74 |
| +2,0 | 15,08% | 457 | 142 | 58 |

**O mecanismo funciona e a troca é desfavorável.** Aumentar o viés reduz inserção exatamente como
previsto (100 → 58), mas cobra em deleção (78 → 142) e substituição (409 → 457) mais do que
economiza. **β=0 já é o ótimo** — a calibração de blank do modelo não tem folga a explorar.

Isto refuta a alavanca mais barata contra o balde recém-descoberto. Fica registrado como refutação
com mecanismo visível, não como "não funcionou".

## Limitações

- **O split S/D/I sai de `difflib.SequenceMatcher`, que não é alinhamento de Levenshtein.** Ele
  maximiza blocos casados em vez de minimizar edições, então a partição é **aproximada** — o WER
  por ele (12,72%) fica acima do WER canônico por `word_edit_distance` (12,54%) na mesma corrida.
  As proporções servem para decidir onde olhar; não são o número publicável de WER.
- **A classificação em três classes só cobre substituições**, por construção do classificador. Não
  há classe para inserção nem para deleção — que é justamente o ponto do § 1.
- **FLEURS é leitura de notícias.** No regime do produto (call center 8 kHz espontâneo) a
  proporção entre inserção, deleção e substituição pode inverter, e com ela a ordem das apostas.
- **Uma corrida, greedy.** O viés de blank foi varrido só na validação e só com decode greedy; com
  beam + LM a interação é `[DESCONHECIDO]`.
