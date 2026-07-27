# Blueprint: Zipformer-CTC causal streaming para M6 (como fechar RNF-02 + equivalência)

> Discover de M6 — **streaming causal**. De-risca a implementação de streaming do finalista de M4
> (**Zipformer-CTC small 22M**, hoje **offline/non-causal**), ancorado no CÓDIGO de **icefall** e
> **sherpa-onnx** (read-only, `knowledge-base/references/`). Todo número/afirmação carrega rótulo
> (`asr-evidence-discipline.md` § 1). **NÃO decide números que exigem treino** — marca `[DESCONHECIDO]`
> o que só M4/M5 mede. Não implementa nada; é documento.

## Context

O finalista de M4 é o Zipformer-CTC small 22M (ADR `0001-m2-architecture-finalists.md`; config
`num-encoder-layers 2,2,2,2,2,2` / `encoder-dim 192,256,256,256,256,256`, vocab 500, T=13 subsampling
4× — `training/results/m4-pilot-fleurs-results.md:18`, `training/results/m6-realtime-current-model.md:52`).
O runtime v0 já faz CTC greedy offline (`crates/macaw-asr/src/decode.rs`, RTFx int8 41-90× ocioso /
25-44× sob carga — `m6-realtime-current-model.md:63` `[MEDIDO]`).

**Dois critérios de real-time seguem ABERTOS** e ambos exigem um modelo **causal** que o atual não é
(`m6-realtime-current-model.md:66,74`):
- **RNF-02** — latência p99 (fim da fala → texto) ≤ 500 ms (`PRD.md:131`).
- **Equivalência batch≡streaming** — critério bloqueante nº 3 (`PRD.md:266`, § 8.1), que nenhum peer
  prova (ADR 0001:48).

O decode do icefall já expõe `causal`/`chunk-size`/`left-context-frames` — a recipe **suporta** causal;
o projeto ainda não explorou. Este blueprint fecha o "como" antes do `/to-plan` de M6-streaming.

## Objective

Provar com o código dos peers **como** o Zipformer-CTC causal treina, decoda, exporta e é servido em
streaming; qual **política de chunk × look-ahead × latência** respeita RNF-02 mantendo RTFx ≥ 6×; e
**como verificar** a equivalência batch≡streaming (DoD de M6). Separar o que é `[FONTE-REPO]` verificável
agora do que é `[DESCONHECIDO]` a-medir em M4/M5.

---

## Q1 — Como o icefall treina/decoda Zipformer causal e qual o contrato de estado (cache)

**Treino é o MESMO `train.py`, mudando só `--causal 1`** `[FONTE-REPO]`. Os args
(`egs/librispeech/ASR/zipformer/train.py:268-290`): `--causal` (default False), `--chunk-size`
default `"16,32,64,-1"` **medido em frames a 50 Hz** (`:279`), `--left-context-frames` default
`"64,128,256,-1"` (`:284-289`). São passados ao encoder em `:665-667`.

**Chave da equivalência-por-construção — o treino já vê contexto limitado.** No `forward` (treino/offline,
`zipformer.py:300-368`), `get_chunk_info()` (`:272-298`) escolhe um `chunk_size` **aleatório da lista a
cada batch** (`random.choice`, `:283`), e `_get_attn_mask()` (`:370-411`) constrói uma **máscara de atenção
bloco-diagonal com left-context limitado** (`attn_mask = src_c > tgt_c OR src_c < tgt_c - left_context_chunks`,
`:408`). Ou seja: o modelo é **treinado sob o mesmo campo receptivo** que verá em inferência streaming — não
é um modelo global adaptado depois. Treinar multi-chunk (lista de tamanhos) produz **um artefato que serve
várias latências** (o `-1` na lista treina também o modo full-context).

**Contrato de estado (cache) entre chunks** `[FONTE-REPO]` (`zipformer.py:428-489`, `get_init_states`
`:492-541`): por camada de encoder, **6 tensores** — `(cached_key, cached_nonlin_attn, cached_val1,
cached_val2, cached_conv1, cached_conv2)` (`:442-444`, `:499-500`). `streaming_forward` fatia
`states[i*6:(i+1)*6]` por camada (`:466`) e devolve `new_states` (`:472,489`). Estado inicial = **zeros**
(`:514-539`), dimensionado por `left_context_frames[0] // downsampling_factor` (`:510`) e pelos dims da
camada. **Fato decisivo para RNF-03:** a forma do cache depende só de `left_context` e dims — **NÃO cresce
com a duração da chamada**. Estado é **bounded**; trabalho por chunk é constante → backlog = 0 é
arquiteturalmente atingível (não uma promessa de marketing).

**Decode simulado (offline, mascarado):** `decode.py --causal 1 --chunk-size N --left-context-frames M`
(`decode.py:817-826`) roda o `forward` com máscara — é o "simulated streaming". **Decode real
(chunk-a-chunk com cache):** `streaming_decode.py` (`:380-411`) usa `streaming_forward` + `DecodeStream`
(`:44`). As duas vias são os dois lados do teste de equivalência (Q4).

---

## Q2 — sherpa-onnx: online/streaming Zipformer-CTC, cache tensors no ONNX

**O ONNX streaming-CTC exporta os cache tensors como I/O** `[FONTE-REPO]`
(`egs/librispeech/ASR/zipformer/export-onnx-streaming-ctc.py`). O export troca `forward` por
`streaming_forward` (`:348`), define `decode_chunk_len = chunk_size*2` e `T = decode_chunk_len + pad_length`
com `pad_length = 7+2*3 = 13` (`:257,350-353`), e declara **cada cache tensor como input `cached_*_{i}` e
output `new_cached_*_{i}`** (`:367-416`), mais **2 estados extra**: `embed_states` (left-pad do ConvNeXt,
`:454-460`) e `processed_lens` (`:463-468`). Os eixos dinâmicos são só o batch `N` (`:373` etc.) — as
demais dimensões são fixas ⇒ **estado de forma fixa**. `meta_data` grava `decode_chunk_len`, `T`,
`left_context_len`, dims por encoder (`:429-443`) — o runtime lê isso para saber como alimentar chunks.

**sherpa consome exatamente esse contrato** `[FONTE-REPO]`
(`sherpa-onnx/csrc/online-zipformer2-ctc-model.cc`): lê o `meta_data` (`T_`, `decode_chunk_len_`,
`left_context_len_` — `:288-291`); constrói `initial_states_` com **`m*6 + 2`** tensores (`:333`, formas
em `:343-407`); `Forward(features, states)` empilha `[features] + states` e devolve `[log_probs] + new
states` (`:60-74`); expõe `ChunkLength() = T_` (`:76`) e `ChunkShift() = decode_chunk_len_` (`:78`).
`StackStates`/`UnStackStates` (`:97-168`) tratam batching de streams com a mesma partição `(n-2)/6`.

**Loop de serving (grounds RNF-02 + RNF-03)** `[FONTE-REPO]`
(`sherpa-onnx/csrc/online-recognizer-ctc-impl.h`):
- `IsReady`: chunk pronto quando `num_processed_frames + ChunkLength() < NumFramesReady()` (`:114-116`)
  — a **espera de encher o chunk é a fonte da latência algorítmica**.
- `DecodeStream`: lê `chunk_length` frames, roda `Forward`, **avança `num_processed_frames += chunk_shift`**
  (`:128-148`). Como `ChunkLength (T=45) > ChunkShift (decode_chunk_len=32)`, há **13 frames de sobreposição
  = right-context/padding** consumidos por chunk (o único "look-ahead", pequeno e fixo).
- `IsEndpoint` (silêncio de cauda, `:213-230`) + `Reset` (`:234-252`) — o `Reset` re-inicializa **estado do
  encoder E do decoder**: é o gancho do teste "reset entre chamadas".

**Timestamps (RF-06)** vêm do modo streaming, não do batch: o decoder online carrega `frame_offset` e
emite `timestamps.push_back(t + r.frame_offset)` (`online-ctc-greedy-search-decoder.cc:52`).

---

## Q3 — Política de chunk × look-ahead × latência (RNF-02 p99 ≤ 500 ms, RTFx ≥ 6×)

**Mapa chunk → latência algorítmica, publicado no próprio repo** `[FONTE-REPO]`
(`egs/librispeech/ASR/RESULTS.md:821-837`, modelo causal 66M LibriSpeech inglês 16 kHz):

| chunk-size (50 Hz) | decode_chunk_len (100 Hz) | latência rotulada | left-context |
|---|---|---|---|
| 16 | 32 (= 320 ms) | **320 ms** (`:823`) | 128 |
| 32 | 64 (= 640 ms) | **640 ms** (`:829`) | 256 |

Aritmética confirmada: 16 frames × 20 ms (50 Hz) = 320 ms; `decode_chunk_len = chunk_size*2`
(`export-onnx-streaming-ctc.py:350`). A latência rotulada = tempo de encher o chunk (`IsReady`).

**WER × chunk (mesmo repo, mesma tabela)** `[FONTE-REPO]` — greedy test-other: 320 ms → **7.81/7.79**;
640 ms → **7.15/7.16** (`:823-824,829-830`). Chunk maior ⇒ WER menor (~0,6 p.p. abs em test-other de 320
p/ 640 ms). **Direção transfere; magnitude e absoluto NÃO** (LibriSpeech inglês banda larga 66M ≠ PT-BR
call center 8 kHz 22M — falácia § 3 #6). O **valor absoluto de WER por chunk do NOSSO modelo é
`[DESCONHECIDO]` até M4/M5.**

**Leitura contra RNF-02 (`[ESTIMATIVA]`, fórmula explícita):** RNF-02 = fim-da-fala → texto ≤ 500 ms p99 =
latência algorítmica (espera do chunk) + compute do último chunk.
- **chunk-16 (320 ms):** deixa ~180 ms de orçamento de compute p/ p99 — **cabe** com folga plausível dada
  a folga de RTFx atual (41-90× ocioso, 25-44× sob carga `[MEDIDO]`, `m6-realtime-current-model.md:63`).
- **chunk-32 (640 ms):** **estoura RNF-02 na latência algorítmica sozinha**, antes de qualquer compute.

⇒ **Ponto de operação recomendado: chunk-size 16 (~320 ms), left-context 128** — o maior chunk que ainda
respeita RNF-02 p99 com margem. chunk-32 é a alternativa "mais WER" que **viola RNF-02** e só entra se o
produto renegociar a latência. **Custo de estado por stream** (`[ESTIMATIVA]`, formas de `get_init_states`):
Σ_camadas 6 tensores ~ `left_context//ds × dims` — bounded por left-context, **constante na duração**; os
bytes exatos p/ o 22M são `[DESCONHECIDO]` até exportar (deriva de dims × left_context × dtype).

> ⚠ **Atraso algorítmico ≠ latência medida.** As duas colunas acima são atraso **algorítmico** `[FONTE-REPO]`.
> A **latência efetiva p99** (com compute int8, carga concorrente RNF-05 e throttling RNF-04) é `[DESCONHECIDO]`
> — só a régua de M1 sob soak mede. Reportar as duas separadas, com p50/p95/p99, é entrega de M6.

---

## Q4 — Como VERIFICAR equivalência batch≡streaming (DoD de M6)

**O icefall JÁ demonstra a equivalência e dá o protocolo** `[FONTE-REPO]` (`RESULTS.md:821-837`): a mesma
tabela roda **duas vias** sobre o mesmo checkpoint causal —
- `simulated streaming` = `decode.py` (utterance inteira, máscara de atenção limitada, `:836`);
- `chunk-wise` = `streaming_decode.py` (chunks com cache, `:837`).

**Deltas medidos entre as vias (greedy, mesmo chunk):** 320 ms → 7.81 vs **7.79** (Δ 0,02); 640 ms → 7.15
vs **7.16** (Δ 0,01) (`:823-824,829-830`). Modified/fast beam idem (Δ ≤ 0,06). ⇒ **batch (mascarado) ≡
streaming (cache) por construção**, com tolerância < 0,1 p.p. no WER de bancada. É a evidência de que o
critério bloqueante nº 3 é **satisfazível** pela família — não uma hipótese ("deveria ser equivalente").

**Protocolo de verificação para o NOSSO modelo (a rodar em M4/M6):**
1. **Nível numérico (o mais forte):** o padrão do repo é `torch.allclose(..., atol=1e-05)` sobre a saída do
   encoder (`onnx_check.py:141-142` compara torch↔onnx). **Adaptar:** rodar o mesmo áudio via `forward`
   (máscara, chunk=16) e via `streaming_forward` (cache, chunk=16, left=128) e assertar `allclose` na saída
   do encoder com **tolerância declarada** (partir de `atol=1e-4`, justificar edge de padding). Este é o
   teste de "equivalência por construção" — determinístico, não estatístico.
2. **Nível WER (produto):** decodar o test set 8 kHz call center pelas duas vias e reportar `|WER_batch −
   WER_stream|` com IC (`asr-evidence-discipline` § 3 #12). Alvo de tolerância a **declarar antes** (âncora:
   < 0,1 p.p. de bancada do repo; o valor 8 kHz é `[DESCONHECIDO]`).
3. **Nível estado (suite dedicada):** deriva de estado em áudio **> 30 min** (RNF-03), backlog=0 em 99,9%,
   e **reset entre chamadas** (`online-recognizer-ctc-impl.h:234-252`) — provar que `Reset` zera encoder+decoder
   e a chamada N+1 não vaza estado da N. **Nunca validar streaming em áudio curto** (§ 3 #4).

**Ressalva honesta `[DESCONHECIDO]`:** a equivalência do repo é em **fp32**. Se o int8 quantizado **alarga**
o gap batch≡streaming (a quantização interage com o cache), é experimento novo — medir int8 pelas duas vias,
não assumir que a equivalência fp32 transfere.

---

## Q5 — FLToP / blank layer-skipping em streaming; interação com biasing (DISC-04)

**O que existe no repo é `blank_penalty`, e ele já está no caminho STREAMING** `[FONTE-REPO]`:
`egs/librispeech/ASR/zipformer/streaming_beam_search.py:75-76` (`logits[:,0] -= blank_penalty` no decode
por chunk) e `sherpa-onnx/csrc/online-transducer-greedy-search-decoder.cc:126-127`. É uma modificação de
**logit por-frame no momento do decode** — **ortogonal ao cache/chunking do encoder**, logo **compatível
com chunk streaming por construção** (opera na saída, não no estado). ✔ resposta a "compatível com chunk
streaming".

**FLToP nomeado (o 10,5× de `PRD.md:250`) é `[LITERATURA]`, não `[FONTE-REPO]`** — o repo não tem um artefato
"FLToP"; tem o primitivo (blank penalty / poda por dominância de blank) que a técnica usa. Honesto: o
mecanismo streaming-safe está no código; o ganho 10,5× específico é literatura a reproduzir.

**Interação com biasing (DISC-04, `backlog.md:42-100`):** blank-skipping e context-graph biasing operam
ambos no **decode dentro do chunk** (logit/score de caminho) — compatíveis em princípio, MAS há um
**trade-off real**: poda agressiva de frames blank pode **descartar frames onde uma hotword receberia
boost**, derrubando recall de nome próprio (o mesmo risco de falso-positivo/negativo que `backlog.md:99`
já registra). ⇒ se M8 acender biasing sobre CTC beam, **medir recall de hotword COM e SEM blank-skipping**.
Nota de escopo: hotwords/beam são **M8/v1.1** (`backlog.md:86`), fora do streaming v0 — o v0 causal é
**greedy** (herda o achado de `m6-runtime-blueprint.md` D1: greedy não tem score de caminho p/ boost).

---

## Q6 — Custo de re-treino: causal do zero ≈ offline? adaptar o checkpoint offline?

**Do zero: custo ≈ o run offline** `[FONTE-REPO]` — o comando de treino causal é o offline + `--causal 1`
(`RESULTS.md:842-851`; `train.py:44`), mesmo corpus/épocas. O nosso run offline do 22M levou **~6 h**
`[ESTIMATIVA]` (âncora: `m6-realtime-current-model.md:75` usa "~6h" para o causal, = o run offline; o corpus
de M3 já existe). ⇒ re-treinar causal do zero **não adiciona custo de dados**, só uma passada de treino.

**Adaptar (warm-start) do checkpoint offline: PARCIAL, não drop-in** `[FONTE-REPO]`. `finetune.py:761-804`
suporta carga parcial via `init_modules` + `strict`, mas assere `set(src_keys)==set(dst_keys)` por módulo
(`:800`). **Barreira arquitetural:** o módulo de convolução difere entre modos —
`ConvolutionModule.depthwise_conv` é `nn.Conv1d` no offline vs **`ChunkCausalDepthwiseConv1d` no causal**
(`zipformer.py:2288-2298`), que "**has a little more than twice the parameters**" (dois convs:
`causal_conv` + `chunkwise_conv`, `scaling.py:580-581,610,619`). ⇒ os pesos de atenção/FF/embed/proj
**transferem** (mesmos nomes/formas); os **conv depthwise NÃO** (nomes/estrutura distintos) e precisam
reinicializar. Warm-start é **possível** (carregar os módulos compartilhados via `init_modules`, non-strict),
mas **se acelera convergência ou iguala a qualidade do-zero é `[DESCONHECIDO]`** — os pesos de atenção foram
treinados p/ contexto global e precisam re-adaptar ao mascaramento causal. Decidir por medição em M4/M5, não
por conveniência.

---

## Coverage Corners (mapeamento para a régua de discovery)

### Coverage Corner 1 — Integration Tests
Equivalência batch≡streaming (Q4) é o teste de integração central: `onnx_check.py:141-142`
(`allclose atol=1e-05`, padrão de tolerância declarada) + as duas vias `decode.py` / `streaming_decode.py`
(`RESULTS.md:836-837`). Suite de estado: deriva > 30 min, backlog=0 (RNF-03), reset entre chamadas
(`online-recognizer-ctc-impl.h:234-252`). Todos `[FONTE-REPO]`.

### Coverage Corner 2 — Dependencies
Zero dep nova além do runtime v0. O modelo causal exporta os **cache tensors** como I/O ONNX
(`export-onnx-streaming-ctc.py:367-468`) e o `ort` já presente os alimenta (contrato `Forward(features,
states)` — `online-zipformer2-ctc-model.cc:60-74`). `meta_data` (`:429-443`) carrega
`decode_chunk_len/T/left_context_len` que o runtime lê. `[FONTE-REPO]`.

### Coverage Corner 3 — Tools
Treino: `egs/librispeech/ASR/zipformer/train.py --causal 1` (`:44`). Decode simulado: `decode.py`
(`:817-826`). Decode real: `streaming_decode.py` (`:380-411`). Export: `export-onnx-streaming-ctc.py`.
Verificação torch↔onnx: `onnx_check.py`. Serving de referência: sherpa `online-recognizer-ctc-impl.h`.
`[FONTE-REPO]`.

### Coverage Corner 4 — Techniques
Máscara de atenção chunk-limitada no treino (`zipformer.py:370-411`) = equivalência por construção; cache
de 6 tensores/camada bounded (`:492-541`); overlap ChunkLength>ChunkShift = look-ahead fixo de 13 frames
(`online-recognizer-ctc-impl.h:128-148`); `blank_penalty` streaming-safe (`streaming_beam_search.py:75-76`).
`[FONTE-REPO]`.

---

## Cross-cutting Comparison — icefall (treino/export) vs sherpa-onnx (serving)

| Aspecto | icefall (`egs/.../zipformer/`) | sherpa-onnx (`csrc/`) | Consequência para o Macaw |
|---|---|---|---|
| Ativar causal | `train.py --causal 1 --chunk-size 16 --left-context-frames 128` (`:44,276-289`) | consome `meta_data` (`online-zipformer2-ctc-model.cc:288-291`) | um artefato multi-chunk serve várias latências |
| Contrato de cache | 6 tensores/camada + embed + processed_lens (`zipformer.py:442-444`, `export...ctc.py:454-468`) | `m*6+2`, StackStates/UnStackStates (`:97-168`) | espelho exato; portar o loop do sherpa |
| Estado inicial | zeros, bounded por left-context (`:514-539`) | idem, formas de `meta_data` (`:343-407`) | **backlog=0 arquitetural** (RNF-03) |
| Chunk feed | `streaming_decode.py:380-411` | `IsReady`/`DecodeStream` (`impl.h:114-148`) | latência = encher chunk; overlap=13 frames |
| Decoder state | greedy/beam por frame | `prev_id`/`num_trailing_blanks`/`frame_offset` cross-chunk (`online-ctc-greedy...:30-63`) | colapso CTC correto na fronteira + timestamps |
| Equivalência | simulated vs chunk-wise Δ<0,1 WER (`RESULTS.md:823-834`) | — (roda o exportado) | protocolo de DoD pronto (Q4) |
| Reset entre chamadas | — | `Reset` zera encoder+decoder (`impl.h:234-252`) | teste de vazamento entre streams |

---

## Recommendations

1. **Re-treinar o small 22M causal do zero** com `--causal 1 --chunk-size "16,32" --left-context-frames
   "128,256"` (multi-chunk → um artefato, dois pontos de latência), mesmo corpus/recipe de M4
   (`train.py:44`, `RESULTS.md:842-851`). Custo ≈ o run offline (~6 h `[ESTIMATIVA]`). **Não** contar com
   warm-start do offline como caminho garantido (Q6: conv difere; ganho `[DESCONHECIDO]`) — do-zero é o
   plano base, warm-start é experimento paralelo opcional.
2. **Ponto de operação de produção: chunk-size 16 (~320 ms), left-context 128** — o maior chunk que respeita
   RNF-02 p99 ≤ 500 ms com margem de compute; chunk-32 (640 ms) **viola RNF-02 algoritmicamente** e só entra
   se o produto renegociar latência por WER (Q3).
3. **Exportar streaming-CTC** via `export-onnx-streaming-ctc.py` (cache tensors + `meta_data`) e **portar o
   loop de serving do sherpa** (`online-recognizer-ctc-impl.h`) para o `macaw-asr`: `IsReady` → `Forward
   (features,states)` → avança `chunk_shift`, decoder greedy com `prev_id`/`frame_offset` cross-chunk.
4. **Plano de verificação de equivalência (DoD nº 3), 3 níveis (Q4):** (a) numérico `allclose(atol=1e-4)`
   encoder `forward` vs `streaming_forward`; (b) WER das duas vias no test set 8 kHz com IC e **tolerância
   declarada antes**; (c) suite de estado > 30 min + reset entre chamadas. Rodar em **fp32 E int8** — não
   assumir que a equivalência fp32 transfere ao int8.
5. **Relatório de latência com p50/p95/p99** por config de chunk, **atraso algorítmico e latência efetiva
   rotulados e separados** (`asr-evidence-discipline` § 3 #3), sob RNF-04 (soak ≥ 10 min) + RNF-05 (carga).
6. **Blank-skipping/`blank_penalty` é streaming-safe** e independente (Q5) — pode entrar cedo; **hotwords/beam
   ficam M8/v1.1** e exigem medir recall COM/SEM blank-skipping (interação com biasing).

---

## ADRs

### D1 — Re-treinar causal do zero é o plano base; warm-start é experimento, não pré-requisito
**Decisão:** M6-streaming treina o 22M causal do zero (mesma recipe + `--causal 1`), não depende de adaptar
o checkpoint offline.
**Rationale:** `[FONTE-REPO]` o `ConvolutionModule` causal (`ChunkCausalDepthwiseConv1d`, `zipformer.py:2288`,
`scaling.py:580`) tem estrutura/parâmetros distintos do offline (`nn.Conv1d`) — warm-start é parcial e o
ganho é `[DESCONHECIDO]`. Custo do-zero ≈ o run offline (~6 h, corpus já existe), então o risco/benefício não
justifica bloquear em cima de um warm-start não medido.
**Alternativa rejeitada:** warm-start obrigatório — economiza compute só se funcionar, e introduz um
`[DESCONHECIDO]` no caminho crítico de M6. Mantido como experimento paralelo opcional.
**Consequência:** M6-streaming carrega um run de treino próprio; o offline segue como o modelo de bancada.

### D2 — chunk-size 16 (~320 ms) é o ponto de operação; chunk-32 não fecha RNF-02
**Decisão:** produção usa chunk-16/left-128; treinar multi-chunk `"16,32"` para reter chunk-32 como opção.
**Rationale:** `[FONTE-REPO]` RESULTS.md mapeia chunk-16→320 ms, chunk-32→640 ms; `[ESTIMATIVA]` 640 ms
estoura RNF-02 (≤500 ms) na latência algorítmica sozinha, enquanto 320 ms deixa ~180 ms p/ compute — coerente
com a folga de RTFx medida (25-90×).
**Alternativa rejeitada:** chunk-32 como padrão (menor WER ~0,6 p.p. em LibriSpeech) — viola o critério
bloqueante RNF-02; WER absoluto PT-BR 8 kHz é `[DESCONHECIDO]` e não justifica quebrar a latência sem dado.
**Consequência:** a curva atraso×WER do NOSSO modelo (M4/M5) pode refutar isto se chunk-16 degradar WER
demais — então é decisão de produto (latência vs WER), registrada, não silenciada.

### D3 — Equivalência batch≡streaming é verificada, não presumida; em fp32 E int8
**Decisão:** o DoD nº 3 só é dado por satisfeito após o teste de 3 níveis (numérico + WER + estado) rodar,
com tolerância declarada antes, nas duas precisões.
**Rationale:** `[FONTE-REPO]` o repo prova a equivalência em fp32 (Δ<0,1 WER, `RESULTS.md:823-834`) — mas isso
é evidência da *família*, não do *nosso* modelo int8. "Deveria ser equivalente por construção" é hipótese
(`asr-evidence-discipline` § 2); a interação da quantização int8 com o cache é `[DESCONHECIDO]`.
**Alternativa rejeitada:** herdar a equivalência do repo como conclusão — é a falácia § 3 #2/#6 (generalizar
entre condições sem medir).
**Consequência:** M6 entrega a suite de equivalência como artefato versionado; sem ela, o critério bloqueante
nº 3 permanece ABERTO por definição.

---

## O que este blueprint NÃO decide (`[DESCONHECIDO]` — só M4/M5/M6 mede)
- **WER absoluto** do 22M causal PT-BR 8 kHz por chunk-size (e a curva atraso×WER real).
- **Latência efetiva p99** streaming sob RNF-04/05 (só atraso *algorítmico* é `[FONTE-REPO]` aqui).
- **Penalidade de WER** causal vs offline para o nosso modelo/corpus.
- **Bytes de estado por stream** do 22M (formula conhecida; número exige export).
- **int8 preserva a equivalência** dentro da tolerância? (medir as duas vias em int8).
- **Warm-start** do checkpoint offline acelera/iguala o causal do-zero?

## Blocked questions
Nenhuma — as 6 questões foram respondidas com citação `[FONTE-REPO]` verificável; os limites estão
explicitamente marcados `[DESCONHECIDO]` (a-medir), não omitidos.
