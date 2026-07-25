# Blueprint: M2 — Decisão de Arquitetura (5 candidatos × 8 critérios)

> **Discovery cycle verdict:** SHIPPABLE (100/100 — research_coverage 100, reference_citations 100, blueprint_completeness 100, structural_risk 100; zero hard caps) — `knowledge-base/reviews/m2-architecture-decision-discover-confidence-2026-07-24.json`
> **Slug:** `m2-architecture-decision` · **Plan:** `knowledge-base/discoveries/plans/m2-architecture-decision-plan.md` · **Date:** 2026-07-24
> **Owner:** `asr-chief-scientist` (lidera) · `streaming-asr-scientist` · `cpu-inference-engineer` · `decoding-biasing-engineer`

## Context

M2 fecha a decisão de arquitetura que o "discover contínuo" existiu para sustentar (`.claude/rules/asr-evidence-discipline.md` § 0; `PRD.md` § 8.1 "⏸ PENDENTE"). A escolha oscilou três vezes na pesquisa original e uma versão do PRD chegou a fixar Zipformer **usando benchmarks do Moonshine** — a falácia §3 #2. Este blueprint avalia os 5 candidatos contra os 8 critérios com evidência rotulada: **RTFx `[MEDIDO]`** na CPU (via régua de M1) para os rodáveis, arquitetura/streaming/recipe `[FONTE-REPO]` (lido do código dos peers), WER `[LITERATURA]` (é M4). **Não trava a arquitetura nem nomeia o vencedor** (§ 0; D3) — produz os finalistas *a pilotar*.

## Objective

Sustentar o ADR de seleção: avaliar cada candidato nos 8 critérios com proveniência, propor 2 finalistas para o piloto de M4, e corrigir o PRD onde a leitura de código contradiz o que ele afirma.

## Coverage Corner 1 — Integration Tests

### Prova de equivalência batch↔streaming (a fronteira do critério 3, bloqueante) — Q6

**Nenhum peer clonado prova equivalência batch≡incremental** `[FONTE-REPO]`. `funasr/tests_models/test_paraformer_streaming.py:54-55` roda o caminho streaming chunk-a-chunk e faz **substring match** (`expected in all_text`) contra uma frase — é **smoke test**, não asserção de que o incremental reproduz o batch (não há `allclose` nem comparação com a saída offline). Confirma o checkpoint EC-3 do plano.

**Consequência:** o critério 3 é satisfeito ao nível de **mecanismo lido no código** (cache existe), mas **provar** que o streaming ≡ batch sob o corpus real 8 kHz é experimento novo de **M4** para o finalista escolhido — nenhum candidato entrega essa prova em M2. É o mesmo padrão de teste determinístico que M1 estabeleceu (`.claude/rules/testing.md` § 3): a equivalência precisa de fixture + tolerância, que o piloto de M4 constrói.

## Coverage Corner 2 — Dependencies

### Recipe de treino (crit. 7), exportabilidade ONNX (crit. 6), licença (crit. 8) — Q5

| Candidato | Recipe from-scratch (crit. 7) | Export ONNX (crit. 6) | Licença código (crit. 8) |
|---|---|---|---|
| **Zipformer+CTC** | ✅ **madura e aberta** `[FONTE-REPO]` — `icefall/egs/reazonspeech/ASR/zipformer/` tem `train.py, decode.py, ctc_decode.py, export-onnx.py, streaming_decode.py, streaming_beam_search.py`; treina os dois modos com `--causal` (`icefall/egs/reazonspeech/ASR/zipformer/train.py:35-42`) | ✅ `export-onnx.py:49-50,353-497` gera encoder/decoder/joiner ONNX; roda no sherpa | ✅ Apache-2.0 (`icefall/LICENSE:1-3`) |
| **Moonshine-AED** | ❌ **ausente para ASR** `[FONTE-REPO]` — o único `train.py` (`moonshine/micro/stt-training/stt_training/train.py:1-12`) é um **WordCNN command classifier para RP2350**, não o encoder-decoder ASR. Os modelos ASR são shipados como pesos; o método está no paper | ✅ `.ort` mmap (`moonshine/README.md:819-823`); runner no sherpa | ✅ MIT código (`moonshine/LICENSE:1-7`); ⚠️ pesos não-EN = Community License **non-commercial** |
| **FastConformer+CTC** | ⚠️ existe em NVIDIA NeMo, **não clonada** `[DESCONHECIDO-repo]` — `parakeet-rs` é só runtime de inferência | ✅ `encoder.onnx + decoder_joint.onnx` (`parakeet-rs/README.md:151-159`; sherpa nemo-ctc/transducer) | ✅ permissiva (NeMo Apache) `[DESCONHECIDO parcial]` |
| **Paraformer/NAR** | ⚠️ FunASR treina; recipe não lida em M2 `[FONTE-REPO parcial]` | ✅ sherpa offline+streaming (`sherpa-onnx/python-api-examples/simulate-streaming-paraformer-microphone.py`) | ✅ MIT código (`funasr/LICENSE:1`); MODEL_LICENSE separado p/ pesos |
| **LC-BiMamba/SSM** | `[DESCONHECIDO]` — sem peer | ❌ **inviável** (`onnxruntime#27796`) `[LITERATURA]` | `[DESCONHECIDO]` |

**Correção necessária ao PRD (Regra 6):** `PRD.md` § 8.1 lista "receita completa publicada" como **força** do Moonshine. A leitura de código **refuta** — não há recipe de treino ASR from-scratch no repo Moonshine (só WordCNN de MCU). Para um projeto treino-do-zero (invariante `PRD.md` § 8.1), isso é material: Zipformer entrega a recipe pronta; Moonshine exigiria reimplementar o treino a partir do paper.

## Coverage Corner 3 — Tools

### RTFx MEDIDO na CPU via sherpa-onnx + régua de M1 (crit. 1, bloqueante) — Q4

Ferramenta de medição: `sherpa_onnx.OnlineRecognizer`/`moonshine_onnx` + a régua de M1 (`crates/macaw-audio/src/harness.rs` `RtfxMeter`), sobre 12 s de fala, 8 runs, 2 warmup, mediana. Evidência completa: `knowledge-base/measurements/m2-rtfx-candidates.md`.

| Arquitetura | Params | RTFx `[MEDIDO]` (média ± desvio, n=10) | min–max | Custo escala com |
|---|---|---|---|---|
| Zipformer (transducer) | ~20M | **15,90 ± 2,06×** | 11,72–18,04× | frames de áudio (fixo) |
| Moonshine tiny (AED) | ~27M | **7,93 ± 0,72×** | 6,52–8,58× | tokens gerados (193) |
| Moonshine base (AED) | ~62M | **12,10 ± 3,15×** | 7,10–15,19× | tokens gerados (49) |

**Achado `[MEDIDO]` decisivo:** em tamanho comparável (~20-27M), o **Zipformer transducer é ~2× mais rápido** que o Moonshine AED na mesma CPU (15,90× vs 7,93×), com **separação limpa** — o pior Zipformer (11,72×) supera o melhor tiny (8,58×), intervalos não sobrepõem. A razão é arquitetural — AED é autoregressivo (custo ∝ tokens; a variância tiny-vs-base prova a content-dependência); transducer/CTC faz um passe (custo ∝ frames, independente do texto). Para áudio longo de call center, a vantagem do transducer *tende a ampliar* (`[ESTIMATIVA]`, a-medir M4). Isto **corrige** o viés do PRD que favorecia Moonshine "por ter benchmark CPU" — o benchmark publicado (69ms/34M, `moonshine/README.md:113-117`) é `[LITERATURA]` de outra CPU, em clips curtos, que não transfere (falácia §3 #1/#4). *(Nota de dispersão: a medição inicial deu 20,45× → ~2,9×; a re-medição N=10 na mesma clip deu ~2,0× — a diferença é carga de CPU, ver measurement § Leitura honesta / F1.)*

**Não medidos** (honesto): Paraformer/NAR e FastConformer — `[LITERATURA]` (FunASR: 16 streams/4vCPU, doc de projeto; FastConformer é família transducer/CTC, RTFx esperado próximo do Zipformer — a medir em M4). LC-BiMamba: `[DESCONHECIDO]` por impossibilidade ONNX (já exclui pelo crit. 6).

## Coverage Corner 4 — Techniques

### Q1 — Estrutura encoder/decoder por candidato

| Candidato | Topologia | Citação |
|---|---|---|
| **Zipformer+CTC** | Encoder U-Net (downsampling/upsampling), atenção com máscara que serve batch e streaming; **7 categorias de cache tipadas por encoder** (`7 * num_encoders` tensores) | `icefall/egs/reazonspeech/ASR/zipformer/zipformer.py:428` |
| **Moonshine-AED** | Encoder-decoder com RoPE + SwiGLU; pipeline `frontend→encoder→adapter→memory→cross_kv→decoder_kv`; custo ∝ duração real | `moonshine/README.md:141,1024-1025`, `moonshine/docs/word-level-timestamps.md:169-177` |
| **Paraformer/NAR** | Non-autoregressive com predictor CIF; artefato offline distinto do streaming | `funasr/tests_models/test_paraformer.py:12` |
| **FastConformer+CTC** | Conformer com subsampling agressivo; TDT (Token-and-Duration Transducer) | `parakeet-rs/README.md:29,155-157` |
| **LC-BiMamba/SSM** | SSM bidirecional, tempo constante `[LITERATURA]` | `PRD.md` § 8.1 |

### Q2 — Streaming nativo com cache (crit. 3, bloqueante)

- **Zipformer** — o mais forte `[FONTE-REPO]`: cache tipado com **7 categorias por encoder** (`7 * num_encoders` tensores: `cached_len, cached_avg, cached_key, cached_val, cached_val2, cached_conv1, cached_conv2`) mantido entre chunks; **um encoder, dois modos** — `forward` (batch, `:487`) e `streaming_forward` (incremental, `:573`) distintos; treino `--causal 1`. Cache: `icefall/egs/ksponspeech/ASR/pruned_transducer_stateless7_streaming/zipformer.py:62-69`.
- **Moonshine** — nativo, cache de encoding + estado do decoder (`moonshine/README.md:141`; "Ergodic Streaming Encoder" no paper v2).
- **Paraformer** — streaming é **artefato separado** do NAR offline (`chunk_size=[0,10,5]`, `encoder_chunk_look_back=4`); divergência estrutural com Zipformer. `funasr/tests_models/test_paraformer_streaming.py:24-26`.
- **FastConformer** — cache-aware (Nemotron) via ONNX `[FONTE-REPO]` (`parakeet-rs/README.md:58,64-66`); mecanismo não lido.
- **LC-BiMamba** — dual-mode reivindicado, não observável `[LITERATURA]`.

### Q3 — Timestamps por palavra (crit. 4) + hotwords (crit. 5)

- **Timestamps:** todos os 4 observáveis dão, por dois mecanismos: **Moonshine** por DTW de cross-attention (pós-processo, decoder especial de 6 saídas, overhead ~0-12%; `moonshine/docs/word-level-timestamps.md:129-190`); **Zipformer/FastConformer/Paraformer** por alinhamento nativo da decodificação (CTC-frame / CIF).
- **Hotwords:** **CTC/transducer forte** — `ContextGraph` (Aho-Corasick/trie com boost na beam) no `icefall/icefall/context_graph.py:81-100`, hotwords em runtime no sherpa. **Moonshine AED fraco no ASR** `[FONTE-REPO]`: o repo **não** expõe biasing/context-boost na transcrição (`moonshine/README.md:1309-1310` é intent-embedding, não boost de token). Confirma a hipótese do PRD — biasing por token favorece CTC/transducer; nome próprio raro em AED é estruturalmente mais difícil (RF-08b hotword fonética).

## Cross-cutting Comparison — Matriz 5 × 8

| Candidato | 1 RTFx | 2 WER 8k | 3 Streaming | 4 Timestamps | 5 Hotwords | 6 ONNX | 7 Recipe | 8 Licença |
|---|---|---|---|---|---|---|---|---|
| **Zipformer+CTC** | **15,90 ± 2,06× `[MEDIDO]`** | `[LITERATURA]`/M4 | ✅† nativo, cache tipado | ✅ CTC nativo | ✅ forte (ContextGraph) | ✅ export completo | ✅ **madura/aberta** | ✅ Apache-2.0 |
| **Moonshine-AED** | 7,93× (tiny)/12,10× (base) `[MEDIDO]` | `[LITERATURA]`/M4 | ✅† cache enc+dec | ✅ DTW cross-attn | ⚠️ **fraco no ASR** | ✅ `.ort`/sherpa | ❌ **ausente p/ ASR** | ✅ MIT; ⚠️ pesos ñ-EN NC |
| **FastConformer+CTC** | `[ESTIMATIVA]` (≈Zipformer p/ analogia de decoder; encoders diferem; a medir M4) | `[LITERATURA]`/M4 | ✅† cache-aware | ✅ TDT | ✅ forte | ✅ ONNX | ⚠️ NeMo, ñ clonada | ✅ Apache |
| **Paraformer/NAR** | `[LITERATURA]` (16 str/4vCPU) | `[LITERATURA]`/M4 | ⚠️ artefato separado | ✅ CIF | ⚠️ média (NAR) | ✅ sherpa | ⚠️ ñ lida | ✅ MIT |
| **LC-BiMamba/SSM** | `[DESCONHECIDO]` (ñ roda ONNX) | `[DESCONHECIDO]` | ⚠️ reivindicado | `[DESCONHECIDO]` | `[DESCONHECIDO]` | ❌ **inviável** | `[DESCONHECIDO]` | `[DESCONHECIDO]` |

> **†** Coluna **3 Streaming**: `✅` = mecanismo de cache/streaming **lido no código** (`[FONTE-REPO]`), **não** a equivalência batch≡streaming — essa é experimento novo de **M4** (§ Q2 e ADR D3). Nenhum candidato prova equivalência em M2.

## ADRs

### D1 — RTFx é agnóstico a idioma; WER não (a fundação do método)

**Decisão:** medir RTFx de modelos ONNX de referência (inglês) é evidência válida do critério 1 para a arquitetura+tamanho, porque o encoder faz o mesmo compute independente da língua; WER é dependente de idioma e fica `[LITERATURA]`/M4.

**Rationale:** sem isso, a matriz de RTFx seria maçã-com-laranja ou atacável por "é modelo inglês". Contém as falácias §3 #8 (tamanho≠velocidade — por isso medimos em faixa comparável ~20-27M) e #2 (não extrapola entre arquiteturas — mede cada uma). **Alternativa rejeitada:** esperar o modelo PT-BR treinado — mas isso é M3+; a decisão de arquitetura precisa da evidência de RTFx agora, e o RTFx transfere.

### D2 — O achado medido reordena a preferência do PRD

**Decisão:** registrar que, medido na mesma CPU, **transducer/CTC (Zipformer) > AED (Moonshine) no critério 1** (~2×, separação limpa), invertendo o viés do PRD que favorecia Moonshine "por ter benchmark CPU".

**Rationale:** o benchmark do Moonshine é `[LITERATURA]` de outra CPU em clips curtos; medindo na mesma CPU com a régua, o transducer ganha — e a razão (custo ∝ frames vs ∝ tokens) **amplia** para áudio longo de call center. Somado à vantagem lida do Zipformer em streaming (crit. 3), hotwords (crit. 5) e recipe (crit. 7), a evidência converge. **Alternativa considerada:** manter Moonshine como favorito pela tese monolíngue — mas a tese (monolíngue pequeno vence) vale para AMBOS (Zipformer também é monolíngue pequeno treinado do zero); não é exclusiva do Moonshine.

### D3 — M2 nomeia finalistas a pilotar, não o vencedor

**Decisão:** o blueprint recomenda 2 finalistas para o ADR de seleção medir em M4; **não trava a arquitetura** (§ 0).

**Rationale:** critério 2 (WER 8 kHz call center) e a equivalência batch≡incremental (crit. 3, Q6) só se medem com o modelo treinado do zero (M4). A decisão final é do ADR + piloto. **Consequência:** o DoD de M2 é "2 finalistas + blueprint + ADR + PRD atualizado", não "arquitetura X escolhida".

## Recommendations for the project

1. **Finalistas propostos para o piloto de M4: Zipformer+CTC e FastConformer+CTC.** Ambos CTC/transducer — fortes nos critérios 3/4/5/6, com RTFx medido (Zipformer) ou esperado próximo (FastConformer, mesma família). A diferença entre eles (crit. 7: Zipformer recipe clonada/madura vs FastConformer recipe NeMo não-clonada) é o que o piloto de M4 resolve.
2. **Moonshine-AED não avança como finalista primário**, mas fica como **braço de controle** no piloto (valida a tese monolíngue e tem timestamps sem 2º passe). Ônus medidos/lidos: RTFx ~2× pior, hotword fraco no ASR, ausência de recipe ASR.
3. **LC-BiMamba e Paraformer/NAR descartados como finalistas:** LC-BiMamba falha o crit. 6 (ONNX inviável — bloqueia a própria medição do crit. 1); Paraformer tem streaming como artefato separado (crit. 3 mais frágil) e hotwords médio.
4. **Corrigir o PRD § 8.1** (Regra 6): "receita completa publicada" do Moonshine é impreciso — é WordCNN de MCU, não recipe ASR. E referenciar este blueprint em vez de fixar arquitetura (DoD de M2).
5. **Experimento de M4 (o mais barato que decide):** treinar/pilotar Zipformer-CTC e FastConformer-CTC em faixa ~30-80M, medir WER 8 kHz + RTFx sob RNF-04/05 (soak+carga) + equivalência batch≡incremental. A régua de M1 já está pronta para isso.

## Blocked questions (if any)

Nenhuma bloqueada. Fronteiras honestas registradas: crit. 2 (WER) é `[LITERATURA]`/M4; RTFx de Paraformer/FastConformer não medido no ambiente (`[LITERATURA]`, a medir M4); mecanismo de cache do FastConformer e recipe do Paraformer não lidos (`[DESCONHECIDO parcial]`); LC-BiMamba tudo `[LITERATURA]`/`[DESCONHECIDO]` (sem peer, ONNX inviável).

## Halt-loop progress (audit trail)

| Q | Corner | Evidência | Status |
|---|---|---|---|
| Q1 | Techniques | `moonshine/README.md`, `icefall/egs/reazonspeech/ASR/zipformer/zipformer.py:428`, `funasr/tests_models/test_paraformer.py` | done `[FONTE-REPO]` |
| Q2 | Techniques | `icefall/egs/ksponspeech/ASR/pruned_transducer_stateless7_streaming/zipformer.py:62-69`, `funasr/tests_models/test_paraformer_streaming.py:24-26` | done `[FONTE-REPO]` |
| Q3 | Techniques | `moonshine/docs/word-level-timestamps.md:129-190`, `icefall/icefall/context_graph.py:81-100` | done `[FONTE-REPO]` |
| Q4 | Tools | `knowledge-base/measurements/m2-rtfx-candidates.md` (RTFx `[MEDIDO]` Zipformer 15,90± vs Moonshine 7,93×, n=10) | done `[MEDIDO]` |
| Q5 | Deps | `icefall/egs/reazonspeech/ASR/zipformer/export-onnx.py:49-50`, `moonshine/micro/stt-training/stt_training/train.py:1-12`, `moonshine/LICENSE:1-7`, `funasr/LICENSE:1` | done `[FONTE-REPO]` |
| Q6 | Tests | `funasr/tests_models/test_paraformer_streaming.py:54-55` (smoke, não equivalência) | done `[FONTE-REPO]` |

## Related

- Plano: `knowledge-base/discoveries/plans/m2-architecture-decision-plan.md`
- Edge cases: `knowledge-base/reviews/m2-architecture-decision-edge-cases-2026-07-24.md`
- RTFx medido: `knowledge-base/measurements/m2-rtfx-candidates.md`
- Régua de M1 usada: `crates/macaw-audio/src/harness.rs`, `knowledge-base/measurements/m1-harness-measurement.md`
- Âncoras: `PRD.md` § 8.1 (8 critérios, candidatos, invariantes), § 7.1 (custo 8 kHz); `.claude/rules/asr-evidence-discipline.md` (§ 0, § 1, § 3 falácias)
