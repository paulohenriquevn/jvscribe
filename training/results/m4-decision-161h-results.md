# M4 — Piloto de DECISÃO: Zipformer-CTC em MLS-PT 161h (WER × RTFx)

**Corpus:** train = MLS-PT ~161h (37.533 cuts, CC-BY humano), dev/test = FLEURS held-out humano.
**Recipe:** icefall real `zipformer/train.py --use-ctc 1 --use-transducer 0` (Regra 9). **Hardware:**
vast.ai RTX 3090 (imagem `k2fsa/icefall`). **Decode:** `ctc-greedy-search`. Este é o run de
DECISÃO (não o piloto de 10h) — corpus adequado, comparação justa das arquiteturas no mesmo test set.

## WER held-out (FLEURS test, 21.471 palavras de ref) `[MEDIDO]`

| Arquitetura | Tamanho | avg=1 | **avg=10** | erros (avg=10) |
|---|---|---|---|---|
| Zipformer-CTC | **small (22,1M)** | 33,99% | **29,97%** | 915 ins, 729 del, 4791 sub, **15.951 corretos** |
| Zipformer-CTC | medium (64,3M) | ⏳ | ⏳ | (treinando) |
| Zipformer-CTC | large (147M) | ⏳ | ⏳ | |
| FastConformer-CTC (NeMo) | — | ⏳ | ⏳ | (fase 4) |

## Penalidade telefônica MEDIDA (experimento #1 do asr-chief-scientist) `[MEDIDO]`

Re-decode do checkpoint de 161h JÁ treinado no held-out FLEURS **degradado pela cadeia
telefônica do M3** (banda 300-3400 Hz + G.711 A-law, resample de volta a 16 kHz para casar
o pipeline de features — isola o dano do canal). `training/make_telephone_test.py`.

| Domínio | WER (avg=10) | corretos |
|---|---|---|
| Clean (FLEURS 16 kHz) | 29,97% | 15.951 / 21.471 |
| **Telefônico (banda + A-law)** | **38,60%** | 14.277 / 21.471 |

**Penalidade = 1,29× (+8,6 p.p.)** — muito mais branda que o fator 2-3× da literatura
(PRD § 7.1). Era o MAIOR risco identificado; medido, é favorável. Projeção honesta: se M5
levar o clean a ~15%, o telefônico fica ~19% antes de augmentação — dentro do alvo 15-25%.

**Caveats obrigatórios:** isola band-limiting + A-law com features casadas em 16 kHz. NÃO
inclui resolução nativa 8 kHz, ruído acústico real, nem codec além do A-law. É o **piso** da
penalidade de deploy; o número real pode ser maior. E é **antes** de treino com augmentação
telefônica (que recuperaria a maior parte até desse 1,3×).

## Achados `[MEDIDO]`

**1. Tese data-bound plenamente confirmada.** Zipformer-CTC small: **10h → 96% WER** (piloto,
colapso-para-blank) vs **161h → 30% WER** (este run). 16× mais dados leva de inútil a usável. O
gargalo do projeto é corpus, não arquitetura (PRD R9).

**2. Modelo saudável, erros balanceados.** Diferente do piloto (100% deletions = colapso para
blank), aqui os erros são ins/del/sub balanceados com **74% das palavras corretas** — um modelo ASR
funcional de verdade.

**3. Model-averaging inverteu como a teoria prevê.** No piloto (10h, não-convergido, loss ainda
caindo) o avg-N **degenerava** o modelo (100% vazio). Aqui (161h, **convergido**, val loss 0,23
estável) o averaging **ajuda**: avg=10 = 29,97% < avg=1 = 33,99%. Confirma os dois regimes — não usar
avg cego em run curto; usar em run convergido.

**4. Convergência.** val ctc_loss: epoch 1 = 4,49 → epoch 2 = 0,64 → epoch 30 = 0,23 (o piloto de 10h
platôou em 0,82 após 30 épocas). 161h generaliza muito melhor.

## Metodologia / reprodução

- Corpus: `training/prep_mls.py --out data/pt` (MLS-PT via `lhotse.prepare_mls` + FLEURS dev/test).
- Treino+decode: `training/run_zipformer_ctc.sh <small|medium|large> 30`.
- Flags de tamanho copiados do `RESULTS.md` do icefall (small/medium/large = 22/64/147M).
- Decode: epoch 30, avg=1 e avg=10, `ctc-greedy-search`, lang-dir completo (`prepare_lang_bpe`).

## O que falta para a decisão do finalista (DoD M4)

- [ ] Zipformer-CTC medium + large (curva WER×RTFx) — medium treinando
- [ ] FastConformer-CTC (2º finalista, NeMo) no mesmo corpus/test — fase 4
- [ ] Ablação da supervisão fonética (≥3% relativo) — fase 3
- [ ] **RTFx na i7-1355U** (export ONNX + régua `RtfxMeter`/`LatencyHistogram`) — fase 5
- [ ] ADR decidindo o finalista por WER×RTFx medido
