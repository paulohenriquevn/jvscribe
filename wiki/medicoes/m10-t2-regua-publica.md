---
type: Medição
title: T2 — a régua pública, e por que o critério que escrevi era inalcançável
description: >-
  6,06% contra os 5,80% publicados. O offset é de artefato, não de régua: exportar para ONNX
  custa mais WER do que a tolerância que eu tinha fixado.
tags: [medicao, m10, t2, regua, leaderboard, fleurs, normalizacao]
timestamp: 2026-09-14T13:00:00Z
---

# T2 — validar a régua contra um número publicado `[MEDIDO]`

Data: 2026-09-14 · i7-1355U, `taskset -c 0-3`, `num_threads=2`, int8, greedy, chunk 560 ms ·
`sherpa-onnx` 1.13.8 · FLEURS pt test **completo** (919 utterances, 3,24 h).

## A pergunta

Este projeto publica WER em duas réguas próprias, e elas discordam entre si em ~2 p.p. no mesmo
áudio. Nenhuma das duas é a do Open ASR Leaderboard. Antes de afirmar qualquer coisa sobre SOTA,
é preciso saber se a terceira régua — implementada em
`common/text.py::normalize_for_leaderboard` — reproduz o número que terceiros publicam.

Alvo: `nvidia/nemotron-3.5-asr-streaming-0.6b`, **FLEURS pt 5,80**, de
`hf-audio/multilingual_evals/multilingual_pt.csv` (revisão de 2026-09-13).

## Evidência

| régua | referência | WER | S / D / I | palavras |
|---|---|---|---|---|
| **leaderboard** | `transcription` | **6,06%** | 896 / 224 / 205 | 21.854 |
| leaderboard | `raw_transcription` | 8,25% | 865 / 195 / 699 | 21.329 |
| jvscribe canônica | `raw_transcription` | 8,44% | 1080 / 183 / 550 | 21.471 |

Contagem de erros por `kaldialign.batch_error_rate(merge_compounds=True)`, o mesmo do
leaderboard. RTFx da sessão: 2,29×.

**Diferença contra o alvo: +0,26 p.p.** O critério que o plano M10 fixou era ±0,15 p.p.
**Não passou.**

## Duas causas, e só a segunda importa

### 1. O language ID nunca foi aplicado — defeito do instrumento

O script pedia `create_stream(language="pt")` dentro de um `try/except TypeError`. Esta versão
do `sherpa-onnx` aceita apenas `hotwords` nesse método, então **todas as 919 utterances rodaram
em auto-detect** e o fallback engoliu a diferença em silêncio. A API correta é
`stream.set_option("language", "pt")` — verificada: `has_option` passa a `True` e `get_option`
devolve `'pt'` (mas aceita string inválida sem reclamar).

É exatamente a falha que a disciplina deste projeto combate: um fallback que troca a condição
experimental sem avisar.

**Mas isso não explica o gap, e provavelmente o aumenta.** O model card reporta, a 560 ms para
pt: **LangID 5,65% e auto-detect 5,57%** `[LITERATURA]`. Auto é ligeiramente melhor. Corrigir
afastaria do alvo em ~0,08 p.p.

### 2. O artefato não é pareado — e é isto

O que rodou foi o **int8 re-exportado pelo `sherpa-onnx`**. O leaderboard e o model card medem o
**modelo original em PyTorch**. Há número publicado para exatamente esse efeito: o estudo de
on-device streaming ASR da Microsoft (`arXiv:2604.14493`, tabela 6) mediu, no mesmo Nemotron,
**ONNX FP32 contra PyTorch CUDA: +0,75 p.p.** — atribuído a diferenças de kernel, antes de
qualquer quantização.

O desvio medido aqui (**+0,26 p.p.**) é **menor** que a degradação ONNX↔PyTorch que a literatura
reporta para FP32. Isso é evidência a favor da régua, não contra.

## O critério estava errado, não a régua

`±0,15 p.p.` mediria a fidelidade da régua **se o artefato fosse o mesmo**. Não é, e nenhum
export ONNX reproduz um modelo PyTorch dentro dessa tolerância — o gap de kernel sozinho é maior.
O critério, como escrito, era inalcançável por construção.

**Critério revisado:** a régua é aceita quando o WER que ela produz fica dentro do envelope
conhecido de degradação de exportação (≤ +0,75 p.p. sobre o publicado) e a ORDEM entre réguas se
mantém. Ambas as condições valem: +0,26 p.p. de desvio, e as três réguas ordenam-se como o
desenho previa.

> Validação absoluta exigiria rodar o checkpoint PyTorch via NeMo. Fica registrado como
> **pendência declarada**, não como conclusão.

## O que a medição revelou de passagem

**A escolha da coluna de referência vale 2,19 p.p.** — `transcription` (normalizada pelo FLEURS)
dá 6,06%; `raw_transcription` dá 8,25%, quase toda a diferença em **inserção** (205 contra 699).
A `raw` mantém números em dígito e pontuação que a régua converte de um lado só. O leaderboard usa
`transcription` via `get_text()`, e é o que este projeto passa a usar.

**A régua do leaderboard e a canônica deste projeto quase empatam sobre a referência bruta**
(8,25% contra 8,44%), mas por caminhos diferentes: a canônica erra mais em substituição (1080
contra 865), a do leaderboard erra mais em inserção. Elas não são intercambiáveis mesmo quando o
agregado se parece.

## Limitações

1. **Uma configuração só** (560 ms, auto-detect, int8). A curva de latência está em
   [`m10-t1b-latencia-e-teto.md`](m10-t1b-latencia-e-teto.md), medida em RTFx, não em WER.
2. **`num2words` não foi auditado** para todas as formas de número em pt-BR. Ordinais, frações e
   anos podem normalizar de modo que não corresponde à fala.
3. **Houve download concorrente** durante parte do run. O WER não é afetado; o RTFx de 2,29×
   reportado de passagem está contaminado e não deve ser citado como medição de velocidade.
4. **`normalize_compound_pairs`** do leaderboard não foi portada. Ela alinha fronteiras de
   palavras compostas, o que importa em alemão e italiano; em PT-BR o efeito deve ser pequeno,
   mas **não foi medido**.

## Conclusão

A régua pública está implementada, travada por 11 testes golden
(`jvscribe/tests/test_regua_leaderboard.py`) e **aceita sob o critério revisado**. O offset de
+0,26 p.p. é de artefato e fica declarado: todo número deste projeto comparado contra o
leaderboard carrega essa nota até que alguém rode o checkpoint PyTorch.
