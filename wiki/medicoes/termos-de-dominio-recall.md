---
type: Medição
title: Termos de domínio — recall e composição do erro
description: BACEN sai como "bacem", 1 caractere de distância. 61% de recall, e 77,8% do erro é alvo de biasing, não de léxico.
tags: [medicao, hotwords, biasing, dominio, decoding, sintese]
timestamp: 2026-07-31T00:00:00Z
---

# Termos de domínio — recall e composição do erro `[MEDIDO]` / `[LITERATURA]`

Data: 2026-07-31 · modelo `models/current/model.int8.onnx` (o entregue) · decode greedy ·
i7-1355U, load 3–7.

## Hipótese

Termos exclusivos do domínio financeiro brasileiro — **BACEN**, SELIC, PIX, FEBRABAN — são raros
nos corpora de treino e o modelo os erraria. A pergunta que decide o que fazer não é *se* erra,
é **como**: se o vocabulário não consegue soletrá-los, o caminho é retreinar; se consegue mas o
decode não os escolhe, o caminho é decoding; se sai quase certo, o caminho é correção.

## Evidência

### O vocabulário não é o gargalo

18 termos do domínio testados contra o `tokens.txt` do artefato canônico: **18/18 emitíveis**. O
BPE é subword (`bacen` → `▁ba ce n`), então qualquer string do português é representável. O
modelo **consegue** escrever BACEN — ele não escolhe.

### Recall sobre fala sintetizada

6 frases × 3 vozes neurais PT-BR (`edge_tts`: Antonio, Francisca, Thalita), transcritas pelo
modelo entregue. O canal telefônico é a cadeia do projeto (`common/audio/augment.sh`: 16k→8k +
banda 300-3400 + G.711 a-law).

| canal | recall do termo |
|---|---|
| 16 kHz limpo | 10/18 = **56%** |
| telefônico 8 kHz | 11/18 = **61%** |

### Como ele erra — o achado

| referência | saiu | distância de caractere |
|---|---|---|
| `bacen` | **`bacem`** | **1** |
| `pix` | **`pixa`** | **1** |
| `febraban` | `fibrabao` | 2 |
| `febraban` | `cebrabn` | 2 |

`cnpj` e `ipca` saem corretos nos dois canais — são soletrados letra a letra, e o modelo lida bem
com isso.

**O modelo acústico acertou.** Ouviu certo e escreveu errado no último caractere.

### Composição do erro pela sonda do projeto

`eval/analyze_error_composition`, n=18 utterances, canal 8 kHz, IC95 por bootstrap sobre
utterances:

| classe | n | fração | IC95 | ação que admite |
|---|---|---|---|---|
| `rare_ref` | 7 | **77,8%** | [50; 100] | **BIASING** |
| `non_word_hyp` | 1 | 11,1% | [0; 33] | atacável por léxico |
| `real_word_hyp` | 1 | 11,1% | [0; 36] | inatacável — passa no filtro |

`rare_ref` domina porque **o dicionário do sistema não contém termos de domínio**: nenhum de
`bacen`, `selic`, `pix`, `febraban` está nas 436.107 palavras de `/usr/share/dict/brazilian`.

## Conclusão — e apenas isto

1. **O gargalo é decoding/correção, não vocabulário.** Medido, não inferido.
2. **Léxico genérico é a ferramenta errada.** Ele classifica os próprios alvos como palavras
   inexistentes. O instrumento certo é uma **lista de domínio** — a *rare word list* de
   [`arXiv:2505.17410`](https://arxiv.org/abs/2505.17410), obtida de manual, site, cadastro do
   cliente ou termos registrados pelo usuário.
3. **A correção mais barata cabe primeiro.** Distância 1 entre `bacem` e `bacen` significa que
   uma correção por distância de edição contra a lista de domínio resolve, **sem beam search,
   sem LLM e sem tocar o modelo** — degrau 5 da escada de parcimônia.

## O que esta medição NÃO diz

- **n=18, 9 substituições.** O IC de `rare_ref` vai de 50 a 100. Direção clara, magnitude não.
- **É fala sintética.** TTS pronuncia limpo demais; conversa espontânea ao telefone tem
  hesitação, sobreposição e ruído. O recall real do domínio segue `[DESCONHECIDO]`.
- **6 termos.** Não é uma lista de domínio, é uma sonda.
- **Uma corrida.** § 3 regra 3 — não conclua de uma só. Isto direciona, não decide.
- O recall ser **maior** no canal telefônico (61% contra 56%) está dentro do ruído com n=18. Não
  sustenta "8 kHz não atrapalha".

## Prior art — dois artigos lidos, e o que transfere

### RASR — `[LITERATURA]`, **não se aplica**

> Shen, Lu, Kawai (NICT). *Retrieval-Augmented Speech Recognition Approach for Domain
> Challenges*. [`arXiv:2502.15264`](https://arxiv.org/abs/2502.15264), 2025-02-21.

Injeta contexto recuperado por RAG **no decoder autoregressivo do LLM**:
`P(yₜ | y<ₜ, I, Encoder(x), D)`. Somos **CTC puro** — a cabeça emite distribuições por frame,
condicionalmente independentes dado o encoder. **Não há onde colocar um prompt.** O decoder deles
é um Llama-2 de 7B; o orçamento aqui é RTFx ≥ 6× em CPU. A família de correção pós-ASR com LLM
grande já havia sido avaliada e recusada neste projeto pelo mesmo motivo.

### GER com dados sintéticos — `[LITERATURA]`, **transfere em parte**

> Yamashita, Yamamoto, Kokubo, Kawaguchi (Hitachi). *LLM-based Generative Error Correction for
> Rare Words with Synthetic Data and Phonetic Context*.
> [`arXiv:2505.17410`](https://arxiv.org/abs/2505.17410), 2025-05-23. Listas de termos raros
> publicadas pelos autores: <https://github.com/natsuooo/llm-ger>.

O ganho **não vem do LLM corretor**. Pelos números do próprio artigo, CSJ eval1:

| método | CER | recall de termo raro |
|---|---|---|
| Whisper large-v3-turbo | 15,5% | 44,5% |
| + N-best (baseline) | 15,6% | 47,5% |
| **+ dados sintéticos** | 14,2% | **81,1%** |

No MedTxt o recall vai de 27,6% para **85,0%**. **~90% do ganho é a geração sintética**, não o
corretor.

**O reenquadramento que faz isso caber aqui:** eles sintetizam para treinar um *corretor* de 70B;
nós sintetizaríamos para treinar o *reconhecedor* de 64M. Mesma geração, consumidor diferente — e
o nosso não muda nada na inferência. Alinha com o que o projeto já mediu: *o gargalo é dado, não
arquitetura*; o finetune de M5 faz **overfitting**, ou seja, sobra capacidade.

E temos algo que o artigo não tem: a **cadeia telefônica**. A fala sintética deles é de estúdio; a
nossa passa por 8 kHz + banda + a-law, casando com o canal de produção.

### ⚠️ O resultado negativo de `arXiv:2505.17410` é um aviso direto para nós

Adicionar **IPA** ao contexto **piorou** o CER de 14,2% para **27,3%** no CSJ eval1 — quase
dobrou. A representação fonética complexa fez o modelo sobreajustar aos termos raros e destruir o
resto. Vencedor foi a representação **simplificada** (LSP), não a fonética formal.

Isto importa porque temos uma **cabeça de fonema auxiliar** com inventário IPA
(`phoneme_targets.json`: 69 fones, `ɛ`, `ɾ`, `ʊ`), hoje **fora do grafo de inferência**
(confirmado: as saídas do ONNX são só `log_probs` e `log_probs_len`). Religá-la para um passe de
rescoring é tentador e este número tem de estar na mesa antes.

## Ordem sugerida

| # | ação | custo | por quê |
|---|---|---|---|
| 1 | Lista de domínio + correção por distância de edição **limitada** | horas, CPU | `bacem→bacen` é 1 edição; nada muda na inferência |
| 2 | Dados sintéticos de termos raros → **finetune** | GPU | onde estava 90% do ganho em `arXiv:2505.17410` |
| 3 | Beam search | medir contra RNF-07 | destrava biasing real e fusão com LM — só se 1 e 2 não bastarem |
| ❌ | LLM na inferência · cabeça de fonema em rescoring | — | não cabe no orçamento; o IPA de `arXiv:2505.17410` é bandeira vermelha |

O risco do passo 1 é a **over-correction** que `arXiv:2505.17410` nomeia: transformar palavra legítima em
termo de domínio. É mensurável — `Composicao.risco_de_falso_positivo()` já existe para isso.

## Reprodução

```bash
# 1. sintetizar (3 vozes pt-BR do edge_tts) e aplicar o canal telefônico
python3 -c "import asyncio, edge_tts; asyncio.run(edge_tts.Communicate(
    'o bacen divulgou a nova taxa nesta quarta feira', 'pt-BR-AntonioNeural').save('bacen.mp3'))"
ffmpeg -i bacen.mp3 -ar 16000 -ac 1 bacen_16k.wav
bash jvscribe/common/audio/augment.sh bacen_16k.wav bacen_tel.wav

# 2. transcrever com o artefato canônico
python3 jvscribe/batch/batch_transcribe.py --input-dir <dir> --out-dir <out>
```

Ferramentas: `edge_tts` (3 vozes pt-BR), `espeak-ng` (G2P pt-BR → IPA), a cadeia de augmentação e
a sonda de composição — **todas já instaladas**.
