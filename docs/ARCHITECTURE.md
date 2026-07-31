# Arquitetura — o modelo e o motor de inferência

Documento de referência do `jvscribe-ptbr-zipformer-ctc-64m` e do motor que o executa.
Todo número aqui foi **extraído do artefato ou do código**, não da memória de quem escreve:
os de estrutura vêm de `onnx.load` e do `state_dict` do checkpoint; os de custo, do profiler
por operador do ONNX Runtime (`jvscribe/results/m6-runtime-profile-2026-07-31.md`).

---

## Parte I — O modelo

### Visão geral

Zipformer-CTC de **64,29M parâmetros**, quantizado int8, com cabeça de fonema auxiliar usada
só no treino. Entra log-mel fbank, sai uma distribuição sobre 500 tokens BPE por frame.

```
áudio 16 kHz mono
   │
   ▼  fbank 80-bin (janela 25 ms, passo 10 ms, kaldi/HTK, snip_edges=False)
(T, 80)                                    T = 100 frames por segundo
   │
   ▼  encoder_embed — Conv2dSubsampling            0,61M par. (1,0%)   ← 22,0% do CUSTO
(T/2, 192)
   │
   ▼  encoder — Zipformer2, 6 stacks              63,38M par. (98,6%)  ← 75,6% do custo
(T/4, 512)                                 ~41 ms por frame de saída
   │
   ├─▶ ctc_output — Linear(512 → 500) + LogSoftmax  0,26M par. (0,4%)  ← 0,3% do custo
   │      (N, T/4, 500) log-probs
   │
   └─▶ phoneme_output — Linear(512 → 69)            0,04M par. (0,1%)
          SÓ NO TREINO — fora do grafo de inferência
```

### Taxa de subamostragem `[MEDIDO]`

Medida rodando o grafo com entradas de tamanho conhecido:

| entrada | duração | saída | fator | ms por frame de saída |
|---|---|---|---|---|
| 100 frames | 1,0 s | 23 | 4,3× | 43 ms |
| 200 frames | 2,0 s | 48 | 4,2× | 42 ms |
| 600 frames | 6,0 s | 148 | 4,1× | 41 ms |

O fator nominal é 4× (`Conv2dSubsampling` /2 × `output_downsampling_factor=2`); o desvio vem
das bordas. Na prática, **um frame de saída a cada ~41 ms** — é essa a granularidade máxima de
timestamp que o CTC pode dar.

### O encoder — Zipformer2

Seis stacks em U (dimensão sobe até o meio e desce), cada um com sua própria taxa de
amostragem interna:

| stack | camadas | dim | feedforward | downsampling | parâmetros |
|---|---|---|---|---|---|
| 0 | 2 | 192 | 512 | 1 | 2,06M |
| 1 | 2 | 256 | 768 | 2 | 3,83M |
| 2 | 3 | 384 | 1024 | 4 | 11,66M |
| 3 | **4** | **512** | **1536** | 8 | **30,34M** |
| 4 | 3 | 384 | 1024 | 4 | 11,66M |
| 5 | 2 | 256 | 768 | 2 | 3,83M |

**O stack 3 concentra 48% do encoder** (30,34M de 63,38M). Ele roda na taxa mais baixa
(downsampling 8), que é o que torna a profundidade acessível: mais parâmetros onde há menos
frames para processar.

Os fatores de downsampling **não são default assumido** — estão nos próprios pesos:
`encoder.encoders.{1,2,3,4,5}.downsample.bias` têm shapes `(2,)`, `(4,)`, `(8,)`, `(4,)`,
`(2,)`, e o stack 0 não tem módulo de downsample (fator 1). O `encoder.downsample_output.bias`
com shape `(2,)` é o `output_downsampling_factor=2` que fecha os 4× totais.

As flags que reconstroem esta configuração — obrigatórias para carregar o checkpoint, e que
**não estão dentro do `.pt`**:

```
--num-encoder-layers    2,2,3,4,3,2
--feedforward-dim       512,768,1024,1536,1024,768
--encoder-dim           192,256,384,512,384,256
--encoder-unmasked-dim  192,192,256,256,256,192
```

### O contraste que o profile revelou

| módulo | % dos parâmetros | % do custo |
|---|---|---|
| `encoder_embed` | **1,0%** | **22,0%** |
| `encoder` | 98,6% | 75,6% |
| `ctc_output` | 0,4% | 0,3% |

`encoder_embed` tem 1% dos pesos e come 22% do tempo. O motivo é o regime em que opera: ele é
o único módulo que processa a entrada em **resolução plena** (100 frames/s × 80 bins), antes
de qualquer subamostragem. Suas convoluções custam 321 µs por nó — o operador mais caro do
grafo inteiro.

### A ativação Swoosh e o custo elementwise

O Zipformer usa ativações próprias, `SwooshL` e `SwooshR`:

```
SwooshL(x) = logaddexp(0, x − 4,0) − 0,08·x − 0,035
SwooshR(x) = logaddexp(0, x − 1,0) − 0,08·x − 0,313261687
```

No treino em GPU elas são kernels compilados do `k2`. **No export ONNX viram um composto** de
`Log` + `Exp` + `Sub` + `Where`. O profiler encontra exatamente **84 nós de `Log` e 84 de
`Exp`**, todos em `/encoder_embed/conv/{3,6,9}/`, e mais de 40% do custo total do grafo está
em operadores elementwise — contra 24,4% no `DynamicQuantizeMatMul`, que é a "conta" de
verdade do modelo.

### Vocabulário

| | |
|---|---|
| linhas em `tokens.txt` | 503 |
| dimensão de saída do modelo | **500** |
| diferença | `#0`, `#1`, `#2` — símbolos de desambiguação do lexicon FST, **não emitíveis** |
| id 0 | `<blk>` — o blank do CTC |
| ids 1, 2 | `<sos/eos>`, `<unk>` |
| demais | peças BPE (SentencePiece), com `▁` marcando início de palavra |

⚠️ **O par (modelo, vocabulário) não é intercambiável.** Dois artefatos deste projeto têm 500
tokens emitíveis cada e **492 dos 500 ids mapeiam para tokens diferentes**. Trocar o
`tokens.txt` produz português plausível e errado, sem erro algum. A validação correta é o
`vocab_fingerprint` do `model_card.json` — SHA-256 sobre os pares `(id, token)` ordenados —
nunca a contagem.

### O modelo NÃO é streaming

Três confirmações independentes:

| fonte | evidência |
|---|---|
| metadado do artefato | `comment = "non-streaming zipformer2 CTC"` |
| grafo ONNX | entradas `x`, `x_lens`; saídas `log_probs`, `log_probs_len` — **nenhum tensor de estado** |
| scripts de treino | `jvscribe/finetune/run_ft_*.sh` nunca passam `--causal`; o default do icefall é `False` |

O encoder é **não-causal**: a atenção enxerga o contexto inteiro nos dois sentidos. Um modelo
streaming teria tensores de cache entrando e saindo do grafo — é o `GetEncoderInitStates()`
que o `sherpa-onnx` usa ([`csrc/online-zipformer2-transducer-model.h:32`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/online-zipformer2-transducer-model.h#L32),
commit `116a44e7`).

Consequência direta e medida: reprocessar uma janela de 6 s custa **121 ms**; processar só os
0,5 s novos custaria **11 ms**. São **10,6× de retrabalho por atualização** — o piso de
latência do desenho atual, e não uma ineficiência de implementação.

---

## Parte II — O motor de inferência

Dois caminhos partilham o mesmo núcleo. Nenhum deles usa GPU.

### Resolução do artefato — quem decide qual peso roda

`jvscribe/common/artifact.py` é o **único** resolvedor; todos os entrypoints o consomem.

```
MACAW_MODEL_DIR  >  models/current  >  diretório de trabalho
        │
        ▼  em cada candidato, nesta ordem:
   model_card.json → campo "model_file"        ← AUTORIDADE
   senão, nomes conhecidos (model.int8.onnx, …)  ← degradação
```

Isto existe porque escolher peso por nome de arquivo já entregou o modelo pior em silêncio:
dois pesos M5 coabitavam o diretório canônico com WER 15,99% e 17,32%, e a ordem alfabética
selecionava o segundo. Nada falhava — a transcrição só ficava mensuravelmente pior.

### Caminho A — lote (`jvscribe/batch/batch_transcribe.py`)

```
pasta de áudios
   │  ffmpeg  (mp3/m4a/aac/flac/ogg/opus/mp4/webm → f32le 16 kHz mono)
   ▼
segmentação por VAD de energia
   │  RMS por janela de 30 ms; corta em silêncios ≥ 350 ms
   │  teto de 28 s: trechos sem pausa são cortados no frame de menor energia
   ▼
fbank por segmento (paralelo, ThreadPoolExecutor — I/O-bound)
   ▼
ordenação por comprimento  → batches de tamanho similar (padding eficiente)
   ▼
ONNX Runtime — inferência em batch
   ▼
CTC greedy por linha  → remonta na ordem original → .txt por arquivo + transcripts.json
```

A ordenação por comprimento antes do batch é o que torna o padding barato: agrupar segmentos
de duração parecida evita preencher uma matriz majoritariamente com zeros.

### Caminho B — tempo real (`jvscribe/realtime/`)

```
   microfone                        loopback da placa
 (ATENDENTE)                          (CLIENTE)
      │                                   │
      └──────── DualCapture ──────────────┘
             (um `parec --device=` por stream)
                      │  s16le 16 kHz, latência 32 ms
                      ▼
              read() DRENA a fila, teto POR STREAM
                      │
                      ▼
              backpressure: atraso > 2 s → descarta o áudio ANTIGO
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
  StreamingCTC (mic)         StreamingCTC (loopback)
        │                           │
        │  FeatureCache — fbank incremental
        │  janela deslizante + ONNX (sessão COMPARTILHADA)
        │  ctc_words → (palavras, tempos)
        │  LocalAgreement-2 → confirma o que se repetiu
        ▼                           ▼
        └────────► Transcricao (turnos) ◄──────┘
                      │
                      ▼
              MetricasRNF → veredito contra PRD § 6
```

#### Por que não há diarização

No caso 1:1 — o dominante — ela não precisa existir. O microfone **é** o atendente por
construção da captura, e o loopback **é** o cliente. Roteamento de stream: custo zero,
acurácia 100%. Um modelo de diarização só entra no caso de 3 falantes (M7).

`sounddevice` não serve para isto: verificado, `sd.query_devices()` lista 8 entradas e **zero**
monitor sources. Por isso a captura usa `parec` com `--device=` explícito, um processo por
stream — mesmo mecanismo do libpulse, via subprocesso.

#### `FeatureCache` — o fbank incremental

Cada amostra é featurizada **uma vez**. A sutileza que o torna correto:

- o offset de extensão tem de ser **múltiplo do frame shift** (160 amostras). Com
  `snip_edges=False` o Kaldi centra os frames e preenche as bordas; offset desalinhado
  desloca o centro de todos os frames — divergência medida de **6,57**;
- o lhotse conta frames por `round(L/shift)`, não `//` — 1.680 amostras dão 11 frames, não 10.
  Predizer a contagem desalinha o cache em silêncio;
- os **2 últimos frames de cada extração são retidos**: o frame *i* abrange
  `[i·160 − 200, i·160 + 200]`, logo um buffer de tamanho *L* deixa até 1,75 frames
  incompletos na cauda. Sem essa margem, divergiam exatamente os frames 49, 99, 149… — o
  último de cada pedaço.

Com as três regras, a extração incremental converge a **9,5 × 10⁻⁷** da completa — ruído de
float32. Coberto por `jvscribe/tests/test_streaming_features.py`.

#### `StreamingCTC` — janela deslizante + LocalAgreement-2

O modelo é offline; a ilusão de streaming vem do algoritmo. A cada `hop`:

1. o áudio novo entra no buffer e no `FeatureCache`;
2. a **janela inteira** é redecodificada (é aqui que mora o retrabalho de 10,6×);
3. o caminho greedy vira `(palavras, tempos de início)` via colapso CTC — remove repetições,
   remove blanks, `▁` marca início de palavra;
4. **LocalAgreement-2**: confirma o maior prefixo comum entre o resultado atual e o anterior.
   Uma palavra só é dada como final quando **duas decodificações consecutivas concordam** com
   ela — é o que evita o texto piscar na tela;
5. o buffer é aparado até a última palavra confirmada, menos o left-context.

É a técnica do Whisper-Streaming. O preço é latência (nada é final antes de dois ciclos) e o
retrabalho da redecodificação; o ganho é poder usar um modelo não-causal ao vivo.

Estado do motor é **limitado por construção**: `committed` guarda no máximo 64 palavras — só
a última é consultada, e o histórico do diálogo é responsabilidade de `Transcricao`. Sem esse
teto, uma ligação de 40 min acumulava ~28 mil tuplas no caminho quente.

#### Backpressure

Quando o consumidor fica para trás, o áudio **antigo** é descartado, preservando a cauda: numa
ligação, o que o cliente acabou de dizer importa mais que o de 15 s atrás. Sem isso, o laço
atrasado nunca recuperava — o atraso medido subiu de 392 ms para 18.798 ms e ficou lá.

A perda é real e aparece no relatório. Preferir texto recente a texto completo é uma **troca**,
não um conserto grátis.

### Configuração do ONNX Runtime

Segue o `sherpa-onnx` ([`csrc/session.cc:149,156`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/session.cc#L149), commit
`116a44e7`), o runtime CPU de referência:

| opção | valor | por quê |
|---|---|---|
| `enable_cpu_mem_arena` | **`True`** | estava desligada sem justificativa; sozinha custava −6,7% [IC95% −18,3; −3,9] ms |
| `inter_op_num_threads` | `threads / 2` | o sherpa configura; nós deixávamos no default |
| `intra_op_num_threads` | `min(8, cores/2)` | medido nesta máquina; **não extrapolar** para a frota BYOD |
| `graph_optimization_level` | *default* | baixar para `BASIC` **piora** +6,6% [IC95% +0,2; +20,8] ms |

Combinado: **−17,1%** de tempo de inferência, IC95% pareado [−36,9; −17,8] ms.

---

## Parte III — Envelope operacional `[MEDIDO]`

Custo de decode por tamanho de janela e ocupação de CPU com 2 canais a cada 0,5 s:

| janela | decode | ocupação | |
|---|---|---|---|
| 2 s | 86 ms | 34,5% | |
| 4 s | 142 ms | 56,8% | |
| **6 s** | **172 ms** | **69,0%** | ← default |
| 8 s | 218 ms | 87,3% | satura |
| 10 s | 262 ms | **104,9%** | satura |

A janela default era 10 s e pedia mais de 100% da CPU. Passou para 6 s **por medição**.

A latência tem piso estrutural `hop + decode(própria) + decode(do outro canal)`, porque os
canais decodificam em série. Na melhor configuração com texto ainda utilizável — janela de
2 s — o p99 chega a **513 ms** contra o alvo de 500 ms do RNF-02.

**Fechar o RNF-02 exige remover o termo `decode(janela)`**, o que só um modelo com cache de
estado faz. Isso é treino com `--causal 1`, não ajuste de runtime.

---

## O que este documento não cobre

- **WER em 8 kHz e em fala espontânea de call center**: `[DESCONHECIDO]`. Todos os números de
  acurácia são banda larga 16 kHz sobre FLEURS (leitura de notícias).
- **Piso da frota BYOD** (Q-01): tudo aqui é de um i7 12-core. Contagem de threads e ocupação
  de CPU não se transferem para máquinas mais fracas.
- **RNF-04 (térmica) e RNF-05 (carga concorrente)**: nunca exercitados em condição válida —
  exigem 30 min de soak com softphone ativo.

## Referências cruzadas

| assunto | onde |
|---|---|
| Profile por operador e prior art | `jvscribe/results/m6-runtime-profile-2026-07-31.md` |
| Medição de RNF ao vivo | `jvscribe/results/m6-live-dual-channel.md` |
| Reprodutibilidade do artefato | `jvscribe/results/reproducibility-2026-07-30.md` |
| Como retomar o treino | `models/current/finetune/README.md` |
| Model card | `models/current/README.md` |
| Requisitos RF/RNF | `PRD.md` § 5, § 6 |
