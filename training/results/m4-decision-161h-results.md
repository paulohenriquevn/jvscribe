# M4 — Piloto de DECISÃO: Zipformer-CTC em MLS-PT 161h (WER × RTFx)

**Corpus:** train = MLS-PT ~161h (37.533 cuts, CC-BY humano), dev/test = FLEURS held-out humano.
**Recipe:** icefall real `zipformer/train.py --use-ctc 1 --use-transducer 0` (Regra 9). **Hardware:**
vast.ai RTX 3090 (imagem `k2fsa/icefall`). **Decode:** `ctc-greedy-search`. Este é o run de
DECISÃO (não o piloto de 10h) — corpus adequado, comparação justa das arquiteturas no mesmo test set.

## WER held-out (FLEURS test, 21.471 palavras de ref) `[MEDIDO]`

| Arquitetura | Tamanho | avg=1 | **avg=10** | erros (avg=10) |
|---|---|---|---|---|
| Zipformer-CTC | **small (22,1M)** | 33,99% | **29,97%** | 915 ins, 729 del, 4791 sub, **15.951 corretos** |
| Zipformer-CTC | medium (64,3M) | 35,04% | **28,86%** | 939 ins, 630 del, 4628 sub, 16.213 corretos |
| Zipformer-CTC | large (147M) | ⏳ | ⏳ | (treinando epoch 15/30) |
| **Conformer-CTC (icefall)** | (a treinar) | ⏳ | ⏳ | **2º finalista** — ver nota de divergência |

> **Divergência de blueprint registrada (2026-07-26, decisão do dono).** O 2º
> finalista era **FastConformer-CTC (NeMo)** (`m4-pilot-blueprint.md`). Após **4+
> falhas honestas de provisionamento na vast.ai** — `pip nemo_toolkit[asr]` corrompendo
> o download (hash mismatch com pypi oficial + `--no-cache`, 3×) e o container
> `nvcr.io/nvidia/nemo:24.12` (40GB) travando no pull sem subir container (2×) — o NeMo
> é **un-provisionable** neste ambiente `[MEDIDO — 4+ tentativas]`. Substituído por
> **Conformer-CTC na recipe icefall**: mesma stack, mesmo corpus (`cv-pt_cuts` 161h),
> mesmo decode (`ctc-greedy-search`), mesmo test (FLEURS). **Serve melhor a intenção
> científica** (família Conformer vs Zipformer como 2º finalista) por **eliminar os
> confounds de framework** que o NeMo introduziria (features, loop de treino, tokenizer
> diferentes). O ADR de M4 fará a comparação Zipformer-CTC vs Conformer-CTC no mesmo
> eixo WER×RTFx. Não é o FastConformer exato — o ADR registra isso como limite.
>
> **Setup do Conformer-CTC pronto e validado `[MEDIDO — dry-run CPU]`** (recipe
> `conformer_ctc3` do icefall = CTC puro, análogo do Zipformer-CTC): datamodule
> adaptado ao commonvoice-PT (reusa o mesmo `data/pt/lang_bpe_500`), **64,718M params**
> (casa com o Zipformer-medium 64,3M, dif 0,65%). Dry-run em CPU (GPU intocada, Zipformer
> seguiu treinando): carrega cuts PT reais + forward `k2.ctc_loss` → loss finito. Patch
> reprodutível: `prep_conformer_ctc.py` na instância. **Lançar quando o large liberar a
> GPU** (OOM: só ~9,5GB livres com o large rodando):
> ```bash
> cd /workspace/icefall/egs/commonvoice/ASR
> env OMP_NUM_THREADS=8 ./conformer_ctc3/train.py --world-size 1 --num-epochs 30 \
>   --start-epoch 1 --use-fp16 1 --enable-musan 0 --exp-dir conformer_ctc3/exp-medium-ctc \
>   --language pt --cv-manifest-dir data/pt --lang-dir data/pt/lang_bpe_500 --max-duration 300
> ```
> Depois: adaptar `ctc_decode.py` (mínimo, análogo ao zipformer) → WER held-out FLEURS.

## Curva WER × RTFx (o tradeoff que decide o finalist) `[MEDIDO]`

| Tamanho | WER (avg=10) | RTFx @ 2 threads (i7-1355U) | veredito |
|---|---|---|---|
| **small (22M)** | 29,97% | **49-90×** | **domina** — quase mesmo WER, 2× mais rápido |
| medium (64M) | 28,86% | 17-38× | −1 p.p. de WER por 2× o compute |
| large (147M) | (treinando) | (a medir) | tende a WER≈, RTFx pior |

**Conclusão parcial da curva:** medium compra só ~1 p.p. de WER por ~2× o custo de CPU → **o `small`
é o forte candidato a finalist** para o objetivo CPU real-time (RNF-07). O `large` deve confirmar
os retornos decrescentes.

## RTFx na CPU-alvo i7-1355U (fase 5) `[MEDIDO]`

Export do small para ONNX (`export-onnx-ctc.py` → `model.int8.onnx`, 27MB, int8 quantizado
automaticamente) + benchmark `training/bench_rtfx.py` na **i7-1355U de referência** (esta máquina).
RTFx = duração_áudio ÷ wall (definição do blueprint M1). Sustentado, descarta warmup.

| Áudio | RTFx @ 1 thread | RTFx @ 2 threads (orçamento RNF-06) |
|---|---|---|
| 5 s | 67,8× | 90,1× |
| 10 s | 62,1× | 78,8× |
| 20 s | 48,5× | 65,7× |
| 30 s | 41,2× | 48,9× |

**RNF-07 exige ASR isolado ≥ 6×. Medido: 41-68× (1 thread) / 49-90× (2 threads) — 7-15× de folga.**
O RTFx cai com áudio mais longo (atenção O(T²) do Zipformer); em streaming (contexto limitado) o
custo/frame é constante → RTFx próximo do número de clip curto. Mesmo o pior caso (30s, 41×) tem
6,8× de margem sobre o piso.

**Caveats (Regra 3):** é inferência **offline** (áudio inteiro, batch), não streaming chunk-a-chunk;
é um clip, não o **soak sustentado** de 10min sob throttle térmico (RNF-04); é o encoder+CTC cru, sem
VAD/log-mel/decode (mas RNF-07 mede ASR isolado). A magnitude da folga (7-15×) absorve todos esses.

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

**0. Retornos decrescentes com tamanho (favorece small p/ CPU).** small (22M) = 29,97% vs
medium (64M) = 28,86% — **3× os params compram só −1,1 p.p. de WER** em 161h. Regime data-bound
(capacidade não é o limite). Para o objetivo CPU real-time isto é decisivo: o `small` dá quase o
mesmo WER a uma fração do compute → forte candidato a finalist. O `large` (147M) tende a ganho
ainda menor e RTFx pior.

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
