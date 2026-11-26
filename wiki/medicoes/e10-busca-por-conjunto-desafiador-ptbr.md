---
type: medicao
title: E10 — procurando um conjunto público PT-BR que seja difícil, e medindo três
description: >-
  Varredura da API do HF (205 datasets), do catálogo falabrasil e do SE&R 2022. Três candidatos
  baixados e medidos. O rotulado "ruidoso" é o mais FÁCIL; o difícil é NURC-SP, com 49,2% no
  recorte de baixa qualidade.
tags: [medicao, dataset, benchmark, nurc, lapsbm, coddef, licenca, e10]
timestamp: 2026-08-01T00:00:00Z
---

# E10 — existe conjunto público PT-BR mais difícil que o nosso?

## Motivação

O critério de ship é **≤25% em call center 8 kHz** e esse conjunto **não existe** (64 cortes,
8,4 min, campo de transcrição vazio). Enquanto ele não for construído, um conjunto público difícil
é o melhor proxy disponível — e proxy que exista hoje vale mais que um alvo perfeito que não existe.

## Como a busca foi feita

1. **API do HuggingFace por tag de idioma** (`language:pt` × modalidade áudio): **205** datasets,
   filtrados por sinais de dificuldade (espontâneo, telefone, ruído, patologia, sotaque, jargão) →
   **33** candidatos.
2. **Catálogo `falabrasil/speech-datasets`** (GitHub), que a API do HF não indexa: revelou LapsBM
   e Código de Defesa do Consumidor, ambos migrados ao HF em 2025 com licença **MIT**.
3. **SE&R 2022 / PROPOR** — shared task de ASR para fala espontânea, construído sobre o CORAA que
   já usamos.

Descartados na inspeção, antes de baixar: `juliasdata/medical-audio-sample-brazilian-portuguese`
(**sem áudio nenhum** — só README e LICENSE), `AxonData/portuguese-contact-center-voice-recognition`
(**um** mp3 de vitrine), `UsergyAI/Global-Conversational-Speech` (acesso manual).

## Evidência — três conjuntos baixados e medidos

`[MEDIDO]` modelo entregue, greedy, CPU. "Estrita" = com acento e forma falada nos dois lados.

| conjunto | licença | n | duração | WER canônica | **WER estrita** |
|---|---|---|---|---|---|
| **LapsBM** (rotulado "ambiente não-controlado") | MIT | 700 | 54,0 min | 8,95% | **9,71%** |
| **CodDef** (Código de Defesa do Consumidor, jargão jurídico) | MIT | 25 | 8,8 min | 12,20% | **11,28%** |
| FLEURS pt_br (referência) | CC-BY-4.0 | 919 | — | 14,83% | **12,75%** |
| CORAA espontâneo | CC-BY-NC-ND | 12.676 | — | 22,94% | — |
| **NURC-SP** (espontâneo, anos 1970) | **MIT** | 500 | 42,6 min | 35,68% | **36,88%** |

### O rótulo "ruidoso" não prediz dificuldade

**LapsBM é o mais FÁCIL de todos** — 9,71%, melhor que o FLEURS — apesar de o catálogo o descrever
como gravado em ambiente não-controlado com ruído de fundo. São frases **curtas e lidas**, e frase
curta continua fácil com ruído.

**O que separa fácil de difícil neste modelo não é ruído: é espontaneidade.** LapsBM (lido) 9,7% ·
FLEURS (lido) 12,8% · CORAA (espontâneo) 22,9% · NURC-SP (espontâneo) 36,9%.

E jargão jurídico sozinho também não dificulta: o CodDef ficou **abaixo** do FLEURS.

### NURC-SP traz um eixo de dificuldade embutido

`[MEDIDO]` split de validação, régua estrita, usando os metadados do próprio dataset:

| recorte | n | min | WER |
|---|---|---|---|
| `quality=high` | 371 | 31,0 | 32,63% |
| **`quality=low`** | **129** | **11,6** | **49,22%** |
| `speech_genre=interview` | 167 | 14,0 | 33,27% |
| `speech_genre=dialogue` | 166 | 13,8 | 38,53% |
| `speech_genre=lecture and talks` | 167 | 14,8 | 38,73% |
| TOTAL | 500 | 42,6 | **36,88%** |

O recorte `quality=low` — **129 utterances, 11,6 minutos, 49,22% de WER** — é o conjunto público
mais difícil que este projeto mediu, e é pequeno o bastante para iterar rápido.

## Recomendação

**Adotar NURC-SP como conjunto de dificuldade**, com o recorte `quality=low` como caso extremo.
Três razões, e a terceira é a que quase ninguém checa:

1. **É difícil de verdade** — 36,9% no total, 49,2% no recorte ruim.
2. **É espontâneo** — diálogo e entrevista, muito mais perto de call center que leitura de notícias.
3. **É MIT** — permite uso comercial, ao contrário do CORAA (CC-BY-NC-ND) e do TAGARELA
   (CC-BY-NC-SA), que hoje sustentam boa parte da nossa avaliação e **proíbem uso comercial**.

## Limitações

- **A degradação do NURC-SP não é a do produto.** São gravações analógicas dos anos 1970 — fita,
  chiado, sala. O nosso canal é **codec telefônico 8 kHz**. WER alto aqui não prova WER alto lá, e
  vice-versa. Falácia § 3 #6 se tratado como equivalente.
- **Sotaque único** — NURC-SP é paulistano por construção. Não diz nada sobre Nordeste ou Sul.
- **Medimos o split de validação (500), não o de teste.** Se este conjunto for adotado como alvo,
  o split de teste deve ser selado e aberto uma vez só.
- **A convenção de transcrição não foi auditada.** Corpora de fala espontânea costumam marcar
  hesitação, truncamento e sobreposição; se essas marcas estiverem no texto, parte do WER medido é
  convenção de anotação, não erro de reconhecimento. **Isto precisa ser verificado antes de o
  número virar alvo.**
- `[DESCONHECIDO]` como o beam+LM se comporta aqui — o LM é de Wikipédia, e fala espontânea dos
  anos 1970 é o pior domínio possível para ele.
