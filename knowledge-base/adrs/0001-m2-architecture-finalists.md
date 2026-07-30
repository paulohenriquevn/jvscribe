# ADR 0001 — Finalistas de arquitetura ASR para o piloto de M4

**Status:** Aceito (M2) · **Data:** 2026-07-24 · **Milestone:** M2 (Decisão de arquitetura)
**Autor:** `asr-chief-scientist` · **Decide:** Zipformer+CTC e FastConformer+CTC como os **2 finalistas a pilotar em M4** — não o vencedor.

## Contexto

`PRD.md` § 8.1 manteve encoder/decoder/tamanho `⏸ PENDENTE` porque a escolha oscilou três vezes na pesquisa original (FastConformer → Zipformer → Moonshine) e uma versão do PRD chegou a fixar Zipformer **usando benchmarks do Moonshine** — a falácia §3 #2 de `.claude/rules/asr-evidence-discipline.md` (generalizar entre arquiteturas sem parentesco), que invalidou os números originais.

O ciclo de descoberta de M2 produziu o blueprint `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md` (SHIPPABLE 100), que avaliou os 5 candidatos contra os 8 critérios do PRD § 8.1 com evidência rotulada: **RTFx `[MEDIDO]`** na CPU (via a régua de M1) para os rodáveis, arquitetura/streaming/recipe `[FONTE-REPO]` (código dos peers), WER `[LITERATURA]` (é M4).

## Decisão

**Finalistas para o piloto comparativo de M4: Zipformer+CTC e FastConformer+CTC.**

Ambos são da família CTC/transducer, fortes nos critérios bloqueantes lidos (streaming, timestamps, hotwords). O RTFx é **`[MEDIDO]`** para o Zipformer (15,90 ± 2,06×, n=10) e apenas **`[ESTIMATIVA]`** para o FastConformer — "esperado próximo" por analogia de *decoder*, com a ressalva de que os *encoders* diferem (Zipformer U-Net/k2 vs FastConformer Conformer + subsampling 8×/NeMo). É o **elo mais fraco** da decisão: o FastConformer é mensurável agora na mesma régua (`parakeet-rs` expõe `encoder.onnx`/`decoder_joint.onnx` no sherpa), e o piloto de M4 deve medi-lo antes de tratá-lo como par do Zipformer — a inclusão dele como finalista repousa nos critérios não-RTFx lidos no repo, não numa velocidade medida. **Não é a escolha do vencedor** — os finalistas são *a-medir* em M4 (`asr-evidence-discipline.md` § 0). O que decide entre eles e valida a escolha é o piloto de M4: WER 8 kHz call center (crit. 2, `[LITERATURA]` até lá), equivalência batch≡streaming (crit. 3, nenhum peer prova), e RTFx sob RNF-04/05 (soak + carga).

### Evidência que sustenta a decisão (por critério)

| Critério | Evidência | Rótulo |
|---|---|---|
| 1 — RTFx (bloqueante) | Zipformer transducer 20M = **15,90 ± 2,06×**; Moonshine tiny 27M = **7,93 ± 0,72×** (n=10, mesma CPU/clip de 12s; `knowledge-base/measurements/m2-rtfx-candidates.md`). O transducer é **~2× mais rápido** em tamanho comparável, com separação limpa (intervalos min–max não sobrepõem) | `[MEDIDO]` |
| 3 — Streaming+cache (bloqueante) | Zipformer: cache tipado com **7 categorias por encoder** (`7 * num_encoders` tensores: `cached_len/avg/key/val/val2/conv1/conv2`), `icefall/egs/ksponspeech/ASR/pruned_transducer_stateless7_streaming/zipformer.py:62-69`; **um encoder em dois modos** — `forward` (batch, `:487`) e `streaming_forward` (incremental com cache, `:573`) no mesmo módulo | `[FONTE-REPO]` |
| 4 — Timestamps (bloqueante) | CTC/transducer dão timestamps por alinhamento nativo da decodificação | `[FONTE-REPO]` |
| 5 — Hotwords (alto) | ContextGraph (Aho-Corasick) no `icefall/icefall/context_graph.py:81-100` — biasing por token, propriedade de CTC/transducer | `[FONTE-REPO]` |
| 6 — Export ONNX (alto) | `icefall/egs/reazonspeech/ASR/zipformer/export-onnx.py:49-50` gera encoder/decoder/joiner; rodam no sherpa | `[FONTE-REPO]` |
| 7 — Recipe (médio) | Zipformer: recipe from-scratch madura/aberta (`icefall/egs/reazonspeech/ASR/zipformer/train.py:35-42`) | `[FONTE-REPO]` |

## Alternativas descartadas (com motivo)

### Moonshine-AED — rebaixado a braço de controle (não finalista primário)
- **RTFx ~2× pior medido** na mesma CPU (7,93× tiny vs 15,90× Zipformer, n=10) — a razão é arquitetural: AED é autoregressivo (custo ∝ tokens; a variância tiny-vs-base de 193→49 tokens prova a content-dependência), transducer/CTC faz um passe (custo ∝ frames). O gap ~2× em 12 s é `[MEDIDO]` (separação limpa: intervalos não sobrepõem); a *ampliação* para áudio longo é `[ESTIMATIVA]` (mecanismo: custo AED ∝ tokens + self-attention O(n²) do decoder), a-medir em M4 — a clip de 12 s não a demonstra. Além disso, o gap medido é um **teto** da vantagem real: modelo AED inglês em áudio pt_br pode inflar tokens (measurement § 4).
- **Hotword fraco no ASR** `[FONTE-REPO]`: o repo Moonshine não expõe biasing/context-boost na transcrição (`moonshine/README.md:1309-1310` é intent-embedding, não boost de token). Nome próprio raro em AED é estruturalmente mais difícil (RF-08b).
- **Sem recipe ASR from-scratch** `[FONTE-REPO]`: o único `train.py` do repo (`moonshine/micro/stt-training/stt_training/train.py:1-12`) é um WordCNN de MCU, não o encoder-decoder ASR — para um projeto treino-do-zero, exigiria reimplementar do paper.
- **Permanece como braço de controle** no piloto: valida a tese monolíngue e dá timestamps sem 2º passe (`moonshine/docs/word-level-timestamps.md:129-190`).

### Paraformer/NAR — descartado
- **Streaming é artefato separado** do NAR offline `[FONTE-REPO]`: o streaming carrega um modelo `-online` distinto (`funasr/tests_models/test_paraformer_streaming.py:13` → `iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online`) do modelo offline (`funasr/tests_models/test_paraformer.py:12` → `...vocab8404-pytorch`), enfraquecendo o critério 3 (bloqueante) vs o "um encoder dois modos" do Zipformer.
- **Hotwords médio**: o CIF paralelo do NAR dificulta o boost por token. `[LITERATURA]`

### LC-BiMamba/SSM — descartado (falha critério bloqueante-indireto)
- **Inviável via ONNX** (`onnxruntime#27796`, `PRD.md` § 8.1) `[LITERATURA]` — falha o critério 6 (exportabilidade) e, por consequência, impossibilita medir o critério 1 (RTFx) no runtime alvo. Sem peer clonado, tudo `[LITERATURA]`/`[DESCONHECIDO]`. Reavaliar apenas se surgir runtime SSM próprio antes de M4.

## O que este ADR NÃO decide (a-medir em M4)

- **Não trava a arquitetura nem escolhe o vencedor** (`asr-evidence-discipline.md` § 0). Zipformer vs FastConformer é decidido pelo piloto.
- **Critério 2 (WER 8 kHz call center)** é `[LITERATURA]` até M4 — nenhum WER de banda larga inglês transfere (custo 8 kHz 2-3×, `PRD.md` § 7.1).
- **Equivalência batch≡streaming** (crit. 3) não é provada por nenhum peer (`funasr/tests_models/test_paraformer_streaming.py:54-55` é smoke test) — é experimento novo de M4.
- **RTFx sob RNF-04/05** (soak ≥10 min + carga) dos finalistas — a régua de M1 já está pronta para medir.

## Consequências

- M4 pilota **dois** finalistas (Zipformer, FastConformer) + Moonshine como controle, medindo WER 8 kHz + RTFx sob carga + equivalência streaming. O piloto pode **refutar** esta ordenação — os finalistas são hipótese medida, não conclusão travada.
- `PRD.md` § 8.1 passa a **referenciar** este ADR + o blueprint em vez de fixar arquitetura, e corrige a alegação "receita completa publicada" do Moonshine.
- Risco de ancoragem (o piloto "confirmar" o esperado) mitigado por manter Moonshine como controle e listar explicitamente o que falta medir.

## Referências

- Blueprint: `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md`
- Medição RTFx: `knowledge-base/measurements/m2-rtfx-candidates.md`
- 8 critérios + candidatos: `PRD.md` § 8.1
- Disciplina de evidência: `.claude/rules/asr-evidence-discipline.md` (§ 0, § 1, § 3)
