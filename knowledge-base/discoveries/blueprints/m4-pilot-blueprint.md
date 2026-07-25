# Blueprint: M4 — Piloto comparativo (treino dos finalistas + G2P + custo)

**Verdict:** SHIPPABLE (100 — `/discover-confidence`, zero hard caps)
**Slug:** `m4-pilot` · **Data:** 2026-07-25 · **Plano:** `knowledge-base/discoveries/plans/m4-pilot-plan.md` (SHIPPABLE 100)
**Executado por:** `asr-chief-scientist` (Q1/Q2/Q8) · `ptbr-phonetics-scientist` (Q3/Q5) · `ml-infra-engineer` (Q4/Q6/Q7) — 3 agentes em paralelo, disciplina de evidência `asr-evidence-discipline.md`.

## Context

M4 é o **primeiro milestone que testa a tese central** do projeto — decidir arquitetura/tamanho/supervisão fonética com dado próprio por fração do custo (`ROADMAP.md § M4`). Depende de M2 (2 finalistas) e M3 (corpus), concluídos. Esta discovery **não treina** (GPU fora de escopo); lê a recipe icefall clonada, mede o G2P em CPU, e deriva a estimativa de custo que decide a infraestrutura de M5. Três achados reenquadram o milestone (§ ADRs): a supervisão fonética não existe pronta na recipe; o ambiente de treino não reusa o torch da máquina; e o custo do piloto é de ordem de centenas de dólares (não milhares).

## Objective

Permitir **decidir o desenho do piloto de M4 e a infraestrutura de treino**, com a estimativa de GPU-horas/custo que fecha o orçamento de M5. Sucesso: `/discover-confidence` ≥ SHIPPABLE_WITH_CAVEATS.

## Coverage Corner 1 — Integration Tests

**Q8 — como a recipe icefall valida o treino (WER, decodificação CTC):**

`[FONTE-REPO]` (`icefall/egs/librispeech/ASR/zipformer/ctc_decode.py`):
- Dois métodos **auto-suficientes** (só modelo + `bpe.model`, sem léxico/LM/grafo): **`ctc-greedy-search`** (`:477-484`) e **`ctc-decoding`** (`:238,567-583`). São os corretos para o piloto — medem a capacidade acústica sem confundir com ganho de LM. Métodos com grafo/LM (`1best`, `nbest-rescoring`, `attention-decoder-rescoring`) exigem HLG/n-gram (`:247-271`).
- WER word-level via `write_error_stats` (`:812-825`), com dump de alinhamento por utterance (`errs-*.txt`, `:790-793`) para análise de erro por recorte.
- Seleção de checkpoint: `--epoch`/`--avg` (model averaging), `--use-ctc 1` (`:169-201`).

**Curva WER×RTFx — o que é medível onde:** ambos os eixos dependem do **checkpoint treinado (GPU)** — WER via `ctc_decode.py` sobre o test set 8 kHz do projeto, RTFx via a régua de M1 na CPU-alvo (i7-1355U) sob RNF-04/05. Sequência: (1) treinar cada tamanho em GPU; (2) WER sobre o test set de call center 8 kHz (não LibriSpeech); (3) exportar → RTFx CPU. **Ressalva § 3 #6:** os WERs do RESULTS.md (2,57/5,95 test-clean/other) são LibriSpeech EN banda larga — não transferem; servem só como sanidade de convergência.

## Coverage Corner 2 — Dependencies

**Q4 — ambiente de treino (k2+icefall+torch):** `[MEDIDO]` `import k2` falha nesta máquina — `k2 1.23.4` foi compilado com `PyTorch 1.13.1+cu117`, mas temos `torch 2.13.0+cpu` (instalado para o lhotse em M3). `train.py:64` faz `import k2` no topo → bloqueia até a inspeção. `[FONTE-REPO]` k2 é wheel pré-compilado **ABI-pinado a `(k2, torch, CUDA)` exatos** (`icefall/docs/source/installation/index.rst:208`; "não mude o torch depois de instalar k2", `:58`).

**Distinção crítica (evita falácia § 3 #1):** (1) **compatibilidade de wheel** — trocar o torch (o que fizemos para o lhotse) quebra o k2, mesmo em CPU; (2) **throughput** — o toy `yesno` roda em CPU (`k2-with-cuda:True, torch-cuda-available:False → device:cpu`, `index.rst:441-468`; fallback `train.py:1281-1284`), mas treinar 500 h+ em CPU é inviável em prazo (`[ESTIMATIVA]`). **Consequência de infra:** o ambiente de treino é uma **imagem GPU própria e versionada** (CUDA + torch pinado + k2 casado), **separada** do ambiente de dev (torch 2.13 cpu do lhotse). `[DESCONHECIDO]`: o par `(torch, CUDA, k2)` disponível hoje nos wheels — validar `import k2` na imagem candidata antes de gastar GPU-hora.

**Q5 — deps do G2P (achado de licença):** phonemizer-fork 3.3.2 = **GPLv3+**; espeak-ng 1.50 = **GPLv3** (`[FONTE-REPO]` PyPI classifier + `/usr/share/doc/espeak-ng/copyright`; acoplamento via `ctypes.cdll.LoadLibrary`, não subprocess — `phonemizer/backend/espeak/api.py:61,87`). Risco para produto proprietário (Regra 9), **mitigado**: o G2P é ferramenta de **treino offline**, nunca distribuída no artefato de produção (a saída de fonemas não é obra derivada; consistente com o design travado — fonética auxiliar descartada em produção). **Ressalva formal:** se algum dia embarcar G2P/espeak-ng no runtime, a análise de licença muda — deve passar por revisão antes. Deps transitivas não verificadas (`[DESCONHECIDO]` — rodar `pip-licenses`).

## Coverage Corner 3 — Tools

**Q6 — ambiente reprodutível barato:** `[FONTE-REPO]` `PRD.md § 9` já escolheu vast.ai — on-demand para o piloto (~$100-200), interruptible/spot para o treino completo (~$1.500-2.000/run). icefall suporta **checkpoint/resume nativo** (por época `--start-epoch` + intra-época `--save-every-n`, salvando model/optimizer/scheduler/scaler/sampler — `icefall/checkpoint.py`, `train.py:508-513`). **NÃO testado** ("backup não testado = inexistente") — smoke de kill+resume é passo obrigatório de M4 antes de run interruptible. Preços spot `[LITERATURA]` (allowlist web vazio, ordem de grandeza): A100 ~$0,65/h central.

**Q7 — estimativa de GPU-horas/custo (o número da decisão):** `[ESTIMATIVA]` com fórmula `FLOPs_época ≈ 6 × params × tokens_por_época`, `GPU-h = FLOPs / throughput_efetivo / 3600`. Premissas rotuladas: ~100 frames/s (entrada bruta, conservador), MFU 40% de A100 (312 TFLOPS pico), overhead de dataloader **1,5-3×** (`[ESTIMATIVA]` a virar `[MEDIDO]` no 1º run — o gargalo pode ser dataloader, não GPU; PRD R7).

| Tamanho | GPU-h/época (c/ overhead) | Custo/combinação (30 épocas) |
|---|---|---|
| ~30M | 0,11–0,22 h | ~$1,30–$6,49 (central ~$3,16) |
| ~80M | 0,29–0,58 h | ~$3,46–$17,31 (central ~$8,44) |
| ~123M | 0,44–0,89 h | ~$5,32–$26,61 (central ~$12,97) |

**Grade completa do piloto** = 2 finalistas × 3 tamanhos × 2 (ablação com/sem) = 12 combinações ≈ **~$98** (bate com o $100-200 do PRD Fase 2). **Fase 3 (8.972 h, 174 épocas):** ~$329 (30M) – $1.350 (123M) por run — bate com o $1.500-2.000 do PRD. **Maior alavanca de custo: nº de épocas até convergência (30 vs 174, fator ~5,8×), não o tamanho.**

## Coverage Corner 4 — Techniques

**Q1 — treinar Zipformer-CTC do zero:** `[FONTE-REPO]` a recipe é **um `train.py` paramétrico** (`icefall/egs/librispeech/ASR/zipformer/train.py`). CTC puro: `--use-ctc 1 --use-transducer 0` (`:293-304`; `ctc_loss_scale` forçado a 1.0, `:1294-1296`). Otimizador **ScaledAdam** + scheduler **Eden** (`:1349-1355`, base_lr 0.045). Tamanho por flags `--num-encoder-layers`/`--encoder-dim` (`:138-170`). Alvos = BPE SentencePiece de `SupervisionSegment.text` (`:919-921`). Checkpoint nativo (`--start-epoch`/`--save-every-n`). **EC-3:** os 3 tamanhos (~30/80/123M) são **derivados por escala**, não configs prontas — há 3 pontos de referência medidos (22,1M/64,3M/147M, `RESULTS.md`) dos quais os alvos são aproximados. **Manifests de M3 compatíveis** (Lhotse CutSet `.jsonl.gz`) mas o **datamodule tem nomes LibriSpeech hardcoded** (`asr_datamodule.py:416-483`) → precisa adaptar (não drop-in).

**Q2 — supervisão fonética auxiliar (ACHADO CRÍTICO):** `[FONTE-REPO]` a "cabeça CTC auxiliar" do icefall opera sobre **subword (BPE), NÃO fonema** — `vocab_size = params.vocab_size`, alvos = `sp.encode(text)` (`model.py:110-117,445-447`; `train.py:919-921`). Multi-task: `loss += ctc_loss_scale × ctc_loss` (`--ctc-loss-scale` default 0.2, `:971-972`). **A supervisão FONÉTICA que o DoD de M4 pede NÃO existe pronta** — exigiria (a) 2º tokenizador/vocabulário fonético (do G2P Q3), (b) 2ª cabeça linear `encoder_dim → num_phones`, (c) alvos fonéticos por utterance. É **desenvolvimento, não flag**. Consequência: a "ablação da supervisão fonética (ganho ≥ 3% WER)" **não é medível** com a recipe atual sem construir a cabeça de fonema primeiro.

**Q3 — G2P PT-BR medido (Q-08):** `[MEDIDO]` sobre 400 sentenças FLEURS pt_br: cobertura (taxa de resposta) **100%** (0/400 falhas), determinismo **100%** (entre execuções/processos/njobs), pt-br diverge de pt-europeu em **100%** (aplica regras próprias, não é alias). Falhas **sistemáticas e localizáveis** (inspeção qualitativa): code-switching PT/EN (aportuguesa "home office"→"ófici"), símbolos numéricos (hífen de CEP → "menos", R$ ambíguo). **PER absoluto = `[DESCONHECIDO]`** — exige gold fonético humano (inexistente localmente; não fabricado). Veredito: bom o bastante para alvos de treino auxiliares **com ressalva** — a cabeça é descartada em produção (ruído no alvo custa menos que em produção), as falhas são filtráveis por classe, e a ablação decide se ajuda.

## Cross-cutting Comparison

| Dimensão | Zipformer (icefall clonado) | FastConformer (parakeet-rs) |
|---|---|---|
| Recipe de treino | `train.py` paramétrico `[FONTE-REPO]` | NeMo, não clonado → `[LITERATURA]`/esboço |
| CTC puro | `--use-ctc 1 --use-transducer 0` | TDT (transducer) — a validar |
| Supervisão fonética | **não existe pronta** (só CTC subword) — construir | idem, a validar |
| Ambiente | k2 pinado a torch/CUDA (imagem GPU própria) | ONNX runtime (parakeet-rs) |
| Custo piloto/tamanho (30 ép.) | $3–13 central | assumido similar (mesma ordem de FLOPs) |

**Divergência a resolver por experimento (§ 4):** o DoD diz "ablação da supervisão **fonética**", mas a recipe entrega CTC auxiliar de **subword**. Ou o projeto (a) redefine "supervisão fonética" como "CTC auxiliar de subword" (medível já, sem desenvolvimento) — perdendo o alvo fonético do G2P; ou (b) constrói a cabeça de fonema (desenvolvimento antes da ablação) para testar o alvo fonético de verdade. É uma decisão de escopo do ADR do piloto, não dissolvível.

## ADRs (síntese — o desenho do piloto de M4)

### D1 — Treino via icefall Zipformer-CTC, 3 tamanhos por escala, datamodule adaptado

**Decisão:** treinar CTC puro (`--use-ctc 1 --use-transducer 0`) na recipe icefall, parametrizando os 3 tamanhos por escala de `num_encoder_layers`/`encoder_dim` (ancorados nos pontos 22M/64M/147M do RESULTS.md), consumindo os manifests Lhotse de M3 via um datamodule adaptado (os nomes LibriSpeech são hardcoded).

**Rationale:** reusar a recipe madura (`parsimony-ladder` rung 4) em vez de reimplementar; CTC puro é o alvo do projeto (transducer é o outro finalista). **Alternativa rejeitada:** escrever recipe própria — reinventa o icefall.

### D2 — Supervisão fonética exige construir a cabeça de fonema (não existe pronta)

**Decisão:** registrar que a recipe só tem CTC auxiliar de subword; a supervisão **fonética** (alvos do G2P) exige desenvolvimento (2º tokenizador fonético + cabeça linear + alvos). O ADR do piloto de M4 deve escolher: (a) medir a ablação da CTC-subword já (sem alvo fonético), ou (b) construir a cabeça de fonema antes da ablação.

**Rationale:** honestidade (Regra 3) — o DoD assume um recurso que não existe; fingir que `--use-ctc` é "supervisão fonética" seria falso. **Consequência:** o critério "≥ 3% relativo de WER" só se aplica ao que for de fato construído/medido.

### D3 — Ambiente de treino é imagem GPU própria (torch pinado + k2 casado), separada do dev

**Decisão:** o treino roda numa imagem de container versionada (CUDA + torch específico + k2 ABI-casado + lhotse), **não** reusa o `torch 2.13+cpu` desta máquina. Validar `import k2` na imagem antes de gastar GPU-hora.

**Rationale:** `[MEDIDO]` k2 quebrou com o torch atual; `[FONTE-REPO]` k2 é ABI-pinado. **Alternativa rejeitada:** reusar o ambiente de dev — impossível (k2 incompatível).

### D4 — Custo do piloto ~$98–200; a decisão de investir GPU é do dono

**Decisão:** o piloto completo (grade de 12 combinações) custa **~$98–200** em GPU `[ESTIMATIVA]` (fórmula explícita, bate com PRD Fase 2); M5 completo ~$1.350–2.000/run. A decisão de provisionar GPU e gastar é do dono do projeto — a discovery entrega o número, não a autorização.

**Rationale:** `asr-evidence-discipline § 1` — `[ESTIMATIVA]` que decide investir; o número exato vira `[MEDIDO]` no 1º run (substituindo o overhead 1,5-3× por profiling real GPU-vs-dataloader).

## Recommendations

Para o `/to-plan` de M4 (uma proposta por questão, separando CPU-factível de GPU):

1. **CPU-factível agora (implementável em M4 sem GPU, com evidência real):**
   - **G2P Q-08:** promover o `g2p_measure.py` para `scripts/corpus/` (versionado) + testes; entregar cobertura/determinismo `[MEDIDO]` + inventário de falhas. (Q3)
   - **Estimativa de custo:** um script/documento que calcula GPU-horas/custo pela fórmula (Q7) — a evidência que decide a infra.
   - **Adaptação do datamodule** (renomear cuts de M3 / editar métodos) — código, testável, sem GPU. (Q1)
   - **Gerador de alvos fonéticos** (G2P → sequência de fonemas por utterance) — offline, CPU, versionado. (Q2/Q3)
2. **Exige decisão de infra + GPU (a apresentar ao dono com o número de D4):**
   - Treinar os 2 finalistas × 3 tamanhos (D1), a ablação (D2), a curva WER×RTFx (Q8), o smoke de checkpoint/resume (Q6).
3. **Decisão de escopo (ADR do piloto):** resolver a divergência D2 — CTC-subword já vs construir cabeça de fonema.

## Blocked / pendências abertas

- **PER absoluto do G2P** — `[DESCONHECIDO]` até anotação humana de ~100-200 palavras (M4/M5).
- **Par `(torch, CUDA, k2)` disponível hoje** — `[DESCONHECIDO]` (web); validar ao provisionar.
- **Overhead real de dataloader** — `[ESTIMATIVA]` 1,5-3× → `[MEDIDO]` no 1º run (profiling).
- **Épocas até convergência PT-BR** — `[DESCONHECIDO]` (30 vs 174 documentados); domina o custo de M5.
- **Cabeça de fonema** — não existe; desenvolvimento (D2).
- **Deps transitivas do phonemizer** — `[DESCONHECIDO]` (rodar `pip-licenses`).
- **FastConformer recipe** — NeMo não clonado; `[LITERATURA]`.

## Referências (todas resolvem em disco / URL)

- Plano: `knowledge-base/discoveries/plans/m4-pilot-plan.md`
- icefall treino: `knowledge-base/references/icefall/egs/librispeech/ASR/zipformer/train.py:64,138-170,293-304,919-921,1281-1284,1294-1296,1349-1355`
- icefall multi-task/CTC: `knowledge-base/references/icefall/egs/librispeech/ASR/zipformer/model.py:110-117,445-447`
- icefall decode/WER: `knowledge-base/references/icefall/egs/librispeech/ASR/zipformer/ctc_decode.py:238,477-484,812-825`
- icefall datamodule: `knowledge-base/references/icefall/egs/librispeech/ASR/transducer/asr_datamodule.py:416-483`
- icefall checkpoint: `knowledge-base/references/icefall/icefall/checkpoint.py`
- icefall install (k2 pin): `knowledge-base/references/icefall/docs/source/installation/index.rst:58,208,441-468`
- icefall RESULTS: `knowledge-base/references/icefall/egs/librispeech/ASR/RESULTS.md:146,206,257`
- G2P: `phonemizer 3.3.2` + `espeak-ng 1.50`; `phonemizer/backend/espeak/api.py:61,87`
- corpus M3: `scripts/corpus/build_manifest.py:18,44-55`
- infra: `PRD.md § 9`
