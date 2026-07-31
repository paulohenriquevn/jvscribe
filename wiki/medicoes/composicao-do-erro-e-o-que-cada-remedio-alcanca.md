---
type: Medição
title: Composição do erro — e o que cada remédio alcança
description: O erro se divide em três terços quase iguais, e nenhuma intervenção isolada alcança mais que um deles.
tags: [medicao, erro, decoding, biasing, lm, hotwords, prior-art]
timestamp: 2026-07-31T00:00:00Z
---

# Composição do erro — e o que cada remédio alcança `[MEDIDO]` / `[LITERATURA]`

Data: 2026-07-31 · modelo `models/current/model.int8.onnx` (o entregue) · decode greedy ·
i7-1355U.

## Hipótese

A pergunta operacional não é *"o modelo erra?"* — é **onde está a massa do erro e qual ferramenta
alcança cada parte**. Sem isso, escolher entre lista de termos, modelo de linguagem, biasing ou
mais dado é chute caro: cada um custa diferente e ataca coisa diferente.

## Evidência — amostra não viciada

FLEURS pt_br, **n=100 utterances**, 2552 palavras de referência. WER agregado **16,07%** — bate
com os 15,99% publicados, o que valida o instrumento antes do resultado. **257 substituições**.
Classificação por `eval/analyze_error_composition`, IC95 por bootstrap sobre utterances.

| classe | n | fração | IC95 | o que é | ferramenta certa |
|---|---|---|---|---|---|
| `non_word_hyp` | 81 | **31,5%** | [25,0; 38,4] | hyp não é palavra, ref é | lista / léxico |
| `real_word_hyp` | 94 | **36,6%** | [29,9; 43,1] | ambas são palavras reais | **nenhum filtro lexical** |
| `rare_ref` | 82 | **31,9%** | [25,8; 38,8] | ref fora do dicionário | biasing / contexto |

**Um terço cada. Nenhuma intervenção isolada alcança mais que isso.**

### Os exemplos dizem o que as classes escondem

**Atacável por lista** — `incidente→inncidente`, `tragico→trajeco`,
`determinismo→terterinismo`, `goethe→golte`, e `nao→naostivesse` (uma **fusão**: "não estivesse"
colapsou numa palavra). Grafias inexistentes, 1–3 edições de distância.

**Inatacável por léxico** — `segundo→segunda`, `de→da`, `logo→longo`, `a→antes`. Isto é
**concordância, gênero e palavra funcional**: as duas formas existem, e nenhuma lista distingue.
Mas é precisamente o que um **modelo de linguagem no decode** resolve — a alavanca que o
`CLAUDE.md` já registra como não explorada (beam + LM, 10–20% relativo `[LITERATURA]`).

Ou seja: rotular esse terço de "inatacável" é verdade **para léxico** e falso para LM.

### O número que decide viabilidade de correção

**0,49%** das palavras **corretas** estão fora do dicionário (11 de 2249) — são os falsos
positivos em potencial de qualquer correção baseada em "não é palavra, conserta". Exemplos:
`internalizados`, `descertificacao`, `civitas`.

Contra 81 substituições atacáveis, a razão é ~**7:1** a favor da correção. Não é garantia; é o
primeiro sinal quantificado de que o remédio não seria pior que a doença.

## Evidência secundária — a sonda de termos de domínio, e o defeito dela

Uma primeira medição foi feita **plantando** 6 termos do domínio financeiro (BACEN, SELIC, PIX,
FEBRABAN, CNPJ, IPCA) em frases sintetizadas por 3 vozes neurais PT-BR (`edge_tts`), passadas
pela cadeia telefônica do projeto.

⚠️ **Ela não caracteriza o sistema, e reportá-la como se caracterizasse foi erro de método.**
Construir uma amostra contendo termos raros e depois concluir que "77,8% do erro é `rare_ref`"
mede o desenho da amostra, não o modelo. A tabela acima, em áudio não viciado, é a distribuição
real — e lá `rare_ref` é 31,9%.

O que a sonda plantada **legitimamente** mostra é o **mecanismo** de uma das classes:

| canal | recall do termo |
|---|---|
| 16 kHz limpo | 10/18 = 56% |
| telefônico 8 kHz | 11/18 = 61% |

| referência | saiu | distância ortográfica | distância fonética |
|---|---|---|---|
| `bacen` | `bacem` | 1 | **0** |
| `pix` | `pixa` | 1 | 2 |
| `febraban` | `fibrabao` | 2 | 4 |
| `selic` | `acelic` | 2 | 1 |

`bacen`/`bacem` têm distância fonética **zero** — `espeak-ng` dá o mesmo IPA. São **homófonos**:
o modelo ouviu certo e escolheu a grafia errada do mesmo som. E o vocabulário não é o gargalo —
18/18 dos termos são emitíveis pelo BPE (`bacen` → `▁ba ce n`).

**Recuperação top-1 contra uma lista de domínio de 16 entradas: 5/5 por distância ortográfica,
5/5 por distância fonética.** A paridade importa: em português, cuja ortografia é muito mais
transparente que a do inglês, a grafia já é um bom proxy do som — o passo de G2P pode não pagar
o próprio custo. É o mesmo achado de `arXiv:2409.06062` (ortografia ≈ fonema, < 1% de diferença)
por um caminho independente.

## Conclusão — e apenas isto

1. **O erro se divide em três terços**, e cada um exige uma ferramenta diferente. Um plano que
   ataque só um deles tem teto de ~1/3.
2. **"Inatacável" é relativo à ferramenta.** O terço de `real_word_hyp` é imune a léxico e é o
   alvo natural de LM no decode.
3. **O vocabulário nunca foi o gargalo.** Todo termo testado é emitível; o modelo não escolhe.
4. **A correção pós-hoc tem razão de custo favorável** (~7:1) — mas o número que a autoriza é o
   falso positivo, e ele precisa ser medido no domínio real, não em FLEURS.

## O que esta medição NÃO diz

- **FLEURS é leitura de notícias.** A composição do erro em conversa telefônica espontânea segue
  `[DESCONHECIDO]` (falácia § 3 #6). A distribuição dos três terços pode ser outra lá.
- **n=100.** Os IC de ~13 p.p. de largura não separam os três terços entre si com confiança.
- **Uma corrida** (§ 3 regra 3).
- O alinhamento por `zip` dentro do bloco substituído é aproximação: quando ref e hyp têm
  tamanhos diferentes, o excedente não é classificado. **Subestima** o total.
- A sonda de termos de domínio usa **fala sintética**, que pronuncia limpo demais, com 6 termos e
  3 vozes.

## Prior art — três artigos, mapeados nas três classes

| artigo | mecanismo | classe que ataca | aplica-se? |
|---|---|---|---|
| [`arXiv:2409.06062`](https://arxiv.org/abs/2409.06062) | retrieval por similaridade **acústica** + LLM corretor sobre texto | `non_word_hyp` + `rare_ref` | **parcialmente** |
| [`arXiv:2505.17410`](https://arxiv.org/abs/2505.17410) | dados **sintéticos** de termos raros no treino | `rare_ref` na origem | **parcialmente** |
| beam + LM (`CLAUDE.md`) | fusão com modelo de linguagem no decode | `real_word_hyp` | sim, não explorado |
| [`arXiv:2502.15264`](https://arxiv.org/abs/2502.15264) | RAG no decoder do LLM | — | **não** |

### `arXiv:2409.06062` — o mais próximo de nós

> Pusateri, Walia, Kashi, Bandyopadhyay, Hyder, Mahinder, Anantha, Liu, Gondala (Apple).
> *Retrieval Augmented Correction of Named Entity Speech Recognition Errors*, 2024-09-09.

É o **único dos três cujo ASR também é CTC**, e cuja correção opera **só sobre o texto** — não
precisa do áudio. Arquitetonicamente compatível.

Os dois achados que mais importam, e ambos reduzem o custo:

- **Similaridade acústica bate semântica com folga.** Recall top-1 no conjunto *head*: Okapi BM25
  53,5% · T5 semântico 80,7% · **Acoustic Neighbor ortográfico 84,8%** · AN fonema 85,6%. A
  tarefa é acústica, não semântica.
- **Top-1 é tão bom quanto top-5.** Os autores concluem que *"o LLM adaptado não tem inteligência
  que o ajude a distinguir entidades acusticamente similares"* — a melhor estratégia é usar o
  vizinho mais próximo e ponto. **Se o LLM não discrimina, ele pode não ser necessário** para a
  parte de recuperar-e-substituir.

E a ablação deles fecha o argumento: LLM **sem** as entidades recuperadas move o WER de 6,98 para
6,90 (nada); **com** elas, para 4,68 (−33%). **O ganho é o retrieval, não o LLM.**

### `arXiv:2505.17410` — o ganho é o dado, não o corretor

> Yamashita, Yamamoto, Kokubo, Kawaguchi (Hitachi). *LLM-based Generative Error Correction for
> Rare Words with Synthetic Data and Phonetic Context*, 2025-05-23. Listas publicadas em
> <https://github.com/natsuooo/llm-ger>.

Pelos números do próprio artigo (CSJ eval1): N-best sozinho move o CER de 15,5% para 15,6% —
**nada**. Com dados sintéticos, recall de termo raro vai de 44,5% para **81,1%**; no MedTxt, de
27,6% para **85,0%**. ~90% do ganho é a geração sintética.

**O reenquadramento que faz isso caber aqui:** eles sintetizam para treinar um *corretor* de 70B;
nós sintetizaríamos para treinar o *reconhecedor* de 64M. Mesma geração, consumidor diferente, e
o nosso não muda nada na inferência. Alinha com o que o projeto já mediu — *o gargalo é dado, não
arquitetura*; o finetune de M5 faz **overfitting**, ou seja, sobra capacidade.

E temos algo que o artigo não tem: a **cadeia telefônica**. A fala sintética deles é de estúdio;
a nossa passa por 8 kHz + banda 300-3400 + a-law, casando com o canal de produção.

### ⚠️ O resultado negativo de `arXiv:2505.17410`

Adicionar **IPA** ao contexto **piorou** o CER de 14,2% para **27,3%** no CSJ eval1 — quase
dobrou. Representação fonética complexa fez o modelo sobreajustar aos termos raros e destruir o
resto; venceu a representação **simplificada**, não a formal.

Importa porque temos uma **cabeça de fonema auxiliar** com inventário IPA
(`phoneme_targets.json`: 69 fones, `ɛ`, `ɾ`, `ʊ`), hoje **fora do grafo de inferência**
(confirmado: as saídas do ONNX são só `log_probs` e `log_probs_len`). Religá-la para rescoring é
tentador, e este número — somado à paridade ortografia/fonema medida acima — sugere que ela
custaria mais do que renderia.

### `arXiv:2502.15264` — não se aplica

> Shen, Lu, Kawai (NICT). *Retrieval-Augmented Speech Recognition Approach for Domain
> Challenges*, 2025-02-21.

Injeta o contexto recuperado **no decoder autoregressivo do LLM**: `P(yₜ | y<ₜ, I, Enc(x), D)`.
Somos **CTC puro** — a cabeça emite distribuições por frame, condicionalmente independentes dado
o encoder. **Não há onde colocar um prompt.** O decoder deles é um Llama-2 de 7B contra um
orçamento de RTFx ≥ 6× em CPU. A família de correção pós-ASR com LLM grande já havia sido
avaliada e recusada neste projeto pelo mesmo motivo.

## Ordem sugerida

| # | ação | alcance | custo |
|---|---|---|---|
| 1 | Medir a composição do erro em **áudio real do domínio** | define tudo abaixo | bloqueado por LGPD |
| 2 | Correção pós-hoc por distância contra lista, com falso positivo medido | ~31% (`non_word_hyp`) | horas, CPU |
| 3 | Beam search + LM | ~37% (`real_word_hyp`) | medir contra RNF-07 |
| 4 | Dados sintéticos de termos raros → finetune | ~32% (`rare_ref`) | GPU |
| ❌ | LLM na inferência · cabeça de fonema em rescoring | — | fora do orçamento; IPA é bandeira vermelha |

O passo 1 vem primeiro porque **esta medição é sobre FLEURS**, e a distribuição dos três terços
no domínio real pode ser outra. Ordenar 2–4 sem ela é otimizar contra a régua errada.

## Reprodução

```bash
# composição do erro sobre FLEURS (a medição principal)
python3 - <<'EOF'
import sys; sys.path.insert(0,"jvscribe"); sys.path.insert(0,"jvscribe/common")
from eval.analyze_error_composition import Composicao, analisar, load_lexicon
# ... transcrever N utterances com Motor.carregar() e classificar cada par (ref, hyp)
EOF

# sonda de termos de domínio (secundária)
python3 -c "import asyncio, edge_tts; asyncio.run(edge_tts.Communicate(
    'o bacen divulgou a nova taxa', 'pt-BR-AntonioNeural').save('t.mp3'))"
ffmpeg -i t.mp3 -ar 16000 -ac 1 t16.wav && bash jvscribe/common/audio/augment.sh t16.wav t8.wav
```

Ferramentas usadas, todas já instaladas: `edge_tts` (3 vozes pt-BR), `espeak-ng` (G2P pt-BR →
IPA), a cadeia de augmentação e a sonda de composição.
