# What Is Actually Recoverable? A Measured Budget for Post-Decode Correction in a 64M CPU-Only CTC ASR for Brazilian Portuguese

**jvscribe — Technical Report / Negative-Results Paper (v1, 2026-07-31)**

> **Companion.** The architecture-selection report for the same system is at
> [`jvscribe-voice-cpu-asr.md`](./jvscribe-voice-cpu-asr.md). This paper assumes that system as
> given and asks a different question: once the model is fixed, how much of its remaining error is
> reachable, by what, and at what cost.
>
> **Reproducibility.** Every number carries a provenance label. `[MEASURED]` numbers were produced
> by scripts in this repository against the published artifact; the exact commands are in the
> per-phase records under `wiki/medicoes/`.

---

## Abstract

Retrieval-augmented and LLM-based post-processing of ASR output is an active area, with recent
work reporting 17–39% relative WER reductions on entity-heavy tasks. We ask what portion of those
techniques survives a hard deployment constraint — a **64M-parameter int8 CTC model running on a
15 W laptop CPU with no GPU and no network**, under a real-time factor requirement — and, more
importantly, **how much error is reachable at all**.

We contribute four measurements on Brazilian Portuguese. First, the error of the deployed model
decomposes into **three near-equal thirds** (non-word hypotheses 31.5%, real-word substitutions
36.6%, out-of-lexicon references 31.9%), each requiring a *different* remedy; no single
intervention exceeds one third. Second, a **confidence gate extractable at zero marginal cost**
(+0.31% of decode time) from the same forward pass flags 11.3% of words with 55.9% precision
[95% CI 49.4–62.0] against a 14.3% base rate. Third — and this refutes the natural design — the
gate and the language-model path are **anti-correlated**: the gate captures 69% of non-word errors
but only 32% of real-word errors, precisely the class an LM would fix. Conditioning beam search on
confidence, an appealing way to fit it in budget, would therefore discard most of its benefit.
Fourth, we measure a **ceiling of ~8% of errors** for dictionary-based post-hoc correction and
achieve **1.7% relative** WER reduction (0.27 pp, 95% CI 0.04–0.54) — a real but small effect that
**missed our pre-registered prediction**, which we report rather than revise.

We also find the standard cost objection to beam search to be empirically unfounded in the batch
path: beam-8 costs **15 ms against a 134 ms encoder**, leaving RTFx at 45.8×. The expensive thing
is cheap; the cheap thing pays little. We report what remains unknown with equal prominence.

---

## 1. Introduction

Three recent lines of work attack rare-word and domain errors in ASR by adding external knowledge
at inference: retrieval-augmented correction over an entity database [1], generative error
correction trained on synthetic rare-word data [2], and automatic context discovery by embedding
retrieval [3]. A fourth line adapts retrieval-augmented generation to small language models for
on-device use [4], and a fifth injects retrieved context directly into an autoregressive LLM
decoder [5].

All five assume compute we do not have. Our deployment target is an agent's own laptop: a
64.29M-parameter Zipformer-CTC exported to int8 ONNX, decoding without GPU or network under
RTFx ≥ 6× for the isolated ASR stage. The smallest language model in the cited work is 1.5B
parameters — roughly 23× our entire acoustic model, and generating tokens rather than consuming
them.

This paper does not propose a method. It asks a prior question that the literature, focused on
demonstrating gains, largely skips: **given a fixed small model, what fraction of its error is
reachable by any post-decode intervention, and what does each one cost?** We answer with
measurements, pre-registered predictions, and explicit kill criteria — and we report the
predictions that failed.

### 1.1 Contributions

1. An **error-composition taxonomy** measured on the deployed model, showing three near-equal
   classes with disjoint remedies (§3).
2. A **zero-cost confidence gate** derived from the same CTC collapse that produces the text,
   with precision/recall curve and bootstrap CIs (§4).
3. The **anti-correlation** between gate coverage and error class, which refutes confidence-gated
   beam search — a design we ourselves proposed before measuring (§4.3).
4. A **measured ceiling and a measured achievement** for dictionary-based correction, including a
   pre-registered prediction that failed (§5), and a **cost measurement** that removes the
   standard objection to beam search in the batch path (§6).

---

## 2. Setup

**Model.** `jvscribe-ptbr-zipformer-ctc-64m`: 64.29M parameters, non-causal Zipformer encoder,
CTC head, exported to ONNX int8. Vocabulary of 500 emittable BPE tokens. Greedy CTC decoding.

**Data.** FLEURS pt_br test split, 100 utterances, 2 552 reference words. Aggregate WER
**16.07%** `[MEASURED]`, consistent with the 15.99% published for this artifact — the instrument
validates before the result.

**Hardware.** Intel i7-1355U (hybrid, 12 cores). All timing measurements report the machine load
at the time; this machine hosts a desktop and rarely idles, which we treat as a limitation
rather than hide.

**Statistics.** Every comparison uses percentile bootstrap. **The resampling unit is the
utterance, not the word**: words within an utterance share speaker, audio, and context, and
resampling them as independent narrows intervals artificially. We refuse to report an interval
below three utterances.

**Error classification.** Following the taxonomy we use throughout, each substitution is labelled
by consulting a 436 107-word Portuguese system dictionary:

- `non_word_hyp` — hypothesis is not a word, reference is → reachable by a lexicon
- `real_word_hyp` — both are real words → no lexical filter distinguishes them
- `rare_ref` — reference is not in the dictionary → needs biasing or context

---

## 3. Where the error mass actually is

`[MEASURED]` FLEURS pt_br, n=100, 257 substitutions, bootstrap CIs over utterances:

| class | n | fraction | 95% CI | remedy |
|---|---|---|---|---|
| `non_word_hyp` | 81 | **31.5%** | [25.0; 38.4] | lexicon / list |
| `real_word_hyp` | 94 | **36.6%** | [29.9; 43.1] | **no lexical filter** |
| `rare_ref` | 82 | **31.9%** | [25.8; 38.8] | biasing / context |

**Three near-equal thirds. No single intervention exceeds one.**

The examples are more informative than the counts. Reachable errors are misspellings 1–3 edits
away (`incidente→inncidente`, `tragico→trajeco`, `determinismo→terterinismo`) and merges
(`não estivesse→naostivesse`). Unreachable-by-lexicon errors are **agreement, gender and function
words** (`segundo→segunda`, `de→da`, `logo→longo`) — both forms exist, so no list distinguishes
them, but this is precisely what a language model fixes. Labelling that third "unreachable" is
true *for a lexicon* and false for an LM.

**A pilot that we report as a methodological error.** We first measured error composition on a
sample into which we had *planted* six domain terms (BACEN, SELIC, PIX, FEBRABAN, CNPJ, IPCA)
synthesised with three neural PT-BR voices and passed through an 8 kHz telephone channel. That
sample yielded 77.8% `rare_ref` — which measures the sample design, not the model. The table above,
on unrigged audio, gives 31.9%. We keep the pilot only for what it legitimately shows: the
*mechanism* of one class. `bacen` was transcribed `bacem`, **phonetic edit distance zero** by
`espeak-ng` — the acoustic model was right and the language prior chose the wrong spelling of the
same sound. 18 of 18 domain terms are spellable by the BPE vocabulary; the bottleneck is decoding,
not vocabulary.

**Over-correction risk.** 0.49% of *correct* words (11 of 2 249) fall outside the dictionary —
the false-positive exposure of any "not-a-word, fix it" rule. Against 81 reachable substitutions,
the ratio is ~7:1 in favour of correction.

---

## 4. A confidence gate that costs nothing

### 4.1 Definition and cost

For each emitted token we take the margin `log P(top-1) − log P(top-2)` in nats at the **first**
frame of the emission, and reduce to the **minimum** over the tokens of a word — the weakest link.
Both quantities come from the same array the argmax already traverses.

`[MEASURED]`, isolated from the ONNX session (which varies 2× on this machine and would mask a
0.3% effect), nine blocks of 200 repetitions: the collapse goes from 0.032 ms to 0.400 ms, i.e.
**+0.368 ms absolute = +0.31%** of a 119 ms decode. We report the absolute number rather than the
ratio: the function itself is 12.5× more expensive, which is irrelevant at 0.03% of the pipeline
and would stop being irrelevant in a hot loop with small inputs.

**An implementation note that cost us a near-miss.** We intended the existing text-producing
function to become a thin wrapper over the new one. Inspecting the artifact's vocabulary first
revealed token id 7 to be exactly the word-start marker `▁`; emitted, it becomes a bare space, and
the two detokenisation paths then differ by one space. With six production callers, that would
have silently changed every published WER. The contract became
`words(x) == text(x).split()`, verified over **300 real utterances with zero divergences**, and
the text function was left untouched.

### 4.2 Separation

`[MEASURED]` n=100, 2 623 words, 374 wrong → **base rate 14.3%**. Bootstrap over utterances,
2 000 resamples, fixed seed:

| τ (nats) | flagged | recall | precision | 95% CI | lift | separates? |
|---|---|---|---|---|---|---|
| 0.25 | 3.8% | 18.2% | **68.7%** | [59.4; 77.3] | 4.8× | ✅ |
| 0.50 | 6.8% | 29.1% | 61.2% | [53.5; 68.4] | 4.3× | ✅ |
| **1.00** | **11.3%** | **44.4%** | **55.9%** | **[49.4; 62.0]** | **3.9×** | ✅ |
| 2.00 | 18.3% | 62.6% | 48.6% | [43.2; 54.0] | 3.4× | ✅ |
| 3.00 | 24.2% | 73.0% | 43.0% | [38.2; 47.8] | 3.0× | ✅ |

At every threshold the lower CI bound exceeds the base rate. At τ=1.0 it sits **3.5× above** it.

### 4.3 The anti-correlation, and the design it refutes

Coverage of the gate is **not uniform across error classes** `[MEASURED]`:

| class | median margin | caught at τ=1.0 |
|---|---|---|
| `non_word_hyp` | 0.49 | **69.1%** |
| `rare_ref` | 0.97 | 51.2% |
| `real_word_hyp` | **1.85** | **31.9%** |

The two classes an external knowledge base can fix are exactly the classes where the model
**flags itself**. The class it does not flag is the one where it is **confidently wrong** — the
signature of a *prior* error: the acoustics do not discriminate, so the language prior decides.

This has a sharp design consequence. Gating an expensive language-model pass by confidence, to
fit it inside a real-time budget, is an appealing move — **it was our own first proposal**. The
measurement refutes it: such a gate would miss 68% of the class the LM exists to fix. The gate
should route to the *external-knowledge* path; the LM path must run unconditionally.

---

## 5. Correction: a measured ceiling and a failed prediction

### 5.1 Ceiling

Chaining the measured factors, with a **perfect** corrector:

```
63%  of errors are substitutions   (the rest are insertions/deletions; no word-level
                                    corrector touches merges such as "não estivesse"→"naostivesse")
× 50%  are flagged by the gate
× 26%  are within reach of the mechanisms
────
≈ 8%  of all errors
```

The 26% comes from an oracle comparison of two candidate sources. **The model's own alternatives
saturate**: top-2 recovers 19.4% of flagged errors, top-5 only 21.7% — the correct token is
generally *not* nearby. A dictionary neighbour within edit distance 2 reaches 26.4%. We note the
oracle bounded candidate generation to at most three low-margin positions; a wider search would
recover more at higher false-positive cost.

### 5.2 Result

The corrector acts only where the class admits it — hypothesis not in the dictionary — with an
edit budget growing as `max(1, len/4)`, and **abstains on ties**. Pre-registered prediction:
reduction of **0.3–1.3 pp**, fixed/broken ratio ≥ 3. Kill criterion: CI crossing zero, or broken ≥
fixed.

`[MEASURED]`, convention: reduction in pp, positive is better.

| τ | reduction | 95% CI | crosses zero? | fixed | broken | ratio |
|---|---|---|---|---|---|---|
| 0.50 | 0.16 | [−0.04; 0.38] | **yes** ❌ | 4 | 1 | 4.0 |
| **1.00** | **0.27** | **[0.04; 0.54]** | no ✅ | **6** | **1** | **6.0** |
| 2.00 | 0.31 | [0.04; 0.61] | no ✅ | 8 | 2 | 4.0 |
| 3.00 | 0.39 | [0.08; 0.70] | no ✅ | 9 | 2 | 4.5 |

WER 16.07% → 15.79% at the pre-registered operating point: **1.7% relative**.

**The prediction failed and we do not revise it.** 0.27 pp is below the predicted 0.3–1.3 pp
range. The effect is real — the CI excludes zero — and the ratio prediction held at 6.0, but the
magnitude was one third smaller than we expected.

**We also decline the tempting number.** Reduction grows monotonically with τ and reaches 0.39 pp
at τ=3.0, which *is* inside the predicted range. Reporting that would mean selecting the threshold
after seeing the outcome, on the same set — selection on the test set. Choosing τ requires a held-
out split, which we did not do.

The kill criterion fired at τ=0.5, where the CI crosses zero: too tight a gate flags too little
and the effect becomes indistinguishable from noise.

### 5.3 The single failure is instructive

```
fixed    dividades→divindades · filalactelistas→filatelistas · lagatos→lagartos
         radeo→radio · musquitos→mosquitos · openacao→operacao
broken   tmz→tez
```

**TMZ** is a media outlet — a `rare_ref` proper noun absent from the dictionary, converted into a
real word. This is over-correction [2] caught in the act, and it is why the corrector's
precondition is a class test rather than a distance test alone. The corrector abstained on 93% of
flagged words (22 edits over ~296 flags).

---

## 6. The cost objection to beam search does not survive measurement

`real_word_hyp` is the largest class (36.6%) and the only one no other intervention touches. Its
remedy is an LM in the decode, which requires beam search. The standing objection is cost.

We measure cost **before** gain, deliberately: if it does not fit, the gain is irrelevant. A
textbook CTC prefix beam search (per-frame pruning to 12 candidates) over one 6.8 s utterance,
169 frames, vocabulary 500 `[MEASURED]`:

| decode | decode ms | total ms | RTFx | fits (≥6×)? |
|---|---|---|---|---|
| greedy | 0.05 | 134.3 | **50.95×** | ✅ |
| beam 2 | 4.29 | 138.5 | 49.39× | ✅ |
| beam 4 | 8.08 | 142.3 | 48.07× | ✅ |
| beam 8 | 15.23 | 149.4 | **45.77×** | ✅ |

The **encoder dominates**: 134 ms against 0.05 ms of collapse, consistent with our published
operator profile in which the CTC head is 0.3% of model cost. Searching over the output of a head
that costs nothing continues to cost nothing, even at eight times the work. Beam-8 adds **11%** of
wall time and leaves RTFx 7.6× above the requirement.

**This is a batch-path component benchmark, and the real-time requirement lives elsewhere.** Our
streaming design reprocesses a 6 s window every 0.5 s hop — 121 ms per hop against 11 ms of new
audio, a measured 10.6× rework — and live RTFx is 2.5–4.6× against a ≥3× requirement for the
two-channel pipeline. **Twelve percent on top of 3.0× falls below the line.** We have paid for
confusing component with system before: CPU affinity measured 25% better in isolation and 46%
worse in the running pipeline. Real-time cost is `[UNKNOWN]`.

The beam here carries **no language model**, and pure-CTC beam without an LM recovers little: the
conditional independence between frames lets the search rediscover the greedy path. Measuring cost
without the LM is a **one-sided test**, and valid: the LM only adds cost.

---

## 7. Related work, and what transfers

| work | mechanism | class attacked | applies here? |
|---|---|---|---|
| Pusateri et al. [1] | acoustic-similarity retrieval + adapted LLM over text | non-word + rare-ref | **partly** |
| Yamashita et al. [2] | synthetic rare-word data for training | rare-ref at source | **partly** |
| Siskos et al. [3] | embedding-based automatic context discovery | rare-ref | retrieval yes, biasing no |
| Fan et al. [4] | graph-indexed RAG for small LMs | — | **no** — different task |
| Shen et al. [5] | RAG into an autoregressive LLM decoder | — | **no** |

**A pattern across three independent groups: the external knowledge does the work; the LLM is
expensive packaging.** Their own ablations say so. Pusateri et al. report their adapted LLM moving
WER from 6.98 to 6.90 without retrieved entities and to 4.68 with them. Yamashita et al. report
N-best-only correction moving CER from 15.5 to 15.6 — nothing — while synthetic data lifts rare-
word recall from 27.6% to 85.0%. Siskos et al. find cheap embedding retrieval achieving *better*
WER than LLM-based context generation at **1/5 the latency**, despite substantially *lower*
context overlap (8.8–21.4% vs 42.6–56.1%) — precision of retrieval is not what drives the gain.

Fan et al. [4] give the general form: replacing graph-structured indexing with semantic
description indexing halves accuracy (≈53% → ≈26%) for small models. **Structure compensates for
semantic capacity, and the advantage grows as the model shrinks.** We are at the extreme of that
line — 64M parameters, and not a language model at all. Our own measurement agrees by an
independent route: top-1 retrieval against a domain list succeeded 5/5 using **orthographic**
distance and 5/5 using phonetic distance, and Portuguese orthography is transparent enough that
the G2P step may not pay for itself. Pusateri et al. reach the same conclusion for English, where
orthographic and phonemic acoustic-neighbour embeddings differ by under 1%.

**Two warnings we adopt.** Yamashita et al. report IPA context *doubling* CER (14.2% → 27.3%) —
relevant because our model carries a trained auxiliary phoneme head with an IPA inventory,
currently outside the inference graph. And Fan et al. show LLM-designed pipelines do not degrade
gracefully when the model shrinks: GraphRAG fails outright with all four small models tested.
Adopting [1]'s design with a smaller LLM is not a saving; it is a different system requiring
measurement from zero.

---

## 8. Method: pre-registration with kill criteria

Each phase declared, **before execution and in version control**, a numeric prediction and the
value that would terminate it. We report two consequences that would not exist otherwise.

**A prediction failed and is reported as failed** (§5.2). Had we set the target after seeing 0.39
pp at τ=3.0, the hypothesis would have been "confirmed" and the fact that the effect at the
pre-chosen point is one third smaller would have disappeared.

**A kill criterion fired** at τ=0.5. A phase whose trigger was the failure of §5 was **not
executed**, because §5 did not fail — complexity unbought by a number.

We consider this the transferable part of the work. In a literature where reported gains cluster
above 15% relative, a measured 1.7% with a stated ceiling of ~8% is a data point about *where the
ceiling is*, not a weak result to be improved by tuning until it publishes.

---

## 9. Limitations

Stated with the same prominence as the results.

1. **Everything is FLEURS — read news, not spontaneous telephone speech.** The three-thirds
   distribution may invert in the deployment domain, and the ordering of interventions with it.
   Domain audio is unavailable to us for data-protection reasons. This is the single largest
   limitation and it bounds every number above.
2. **n=100, single run.** Bootstrap CIs cover between-utterance variance, not between-run
   variance; decoding is deterministic given the model.
3. **Real-time cost of beam search is unmeasured** (§6), and the real-time requirement is the
   binding one.
4. **Only the dictionary correction path was exercised.** The domain-list path needs a domain,
   which FLEURS lacks.
5. **The corrector buckets candidates by (first letter, length)**, so an error in the first
   character is invisible to it — recall traded for time.
6. **Fixed/broken attribution is positional** and misassigns when a correction changes alignment;
   the WER delta does not depend on it, the counts do.
7. **Insertions and deletions (37% of errors) are outside every mechanism studied.**
8. **The confidence measure is coarse** — first-frame margin. The posterior of the collapsed path
   likely separates better and was not compared.
9. **τ was not selected on a held-out split** (§5.2).

---

## 10. Conclusion

For a 64M CPU-only CTC ASR, the error is not one problem but three of roughly equal size, and the
tools that address them are disjoint. A confidence signal sufficient to locate half the errors is
already present in the forward pass at 0.31% additional cost, and it points at exactly the two
classes external knowledge can fix — while systematically missing the class a language model would
fix, which forbids the natural design of gating the LM by confidence.

Post-hoc correction over the located errors is real and small: **1.7% relative against a measured
ceiling near 8% of errors**. Beam search, long deferred on cost grounds, costs 11% of wall time in
the batch path — the expensive thing is cheap, and the cheap thing pays little.

The next investment follows from the numbers rather than from the literature: an LM in the decode,
after measuring its cost where the requirement actually binds. And the honest caveat is that all
of it rests on read speech, while the product runs on telephone conversation.

---

## References

[1] E. Pusateri, A. Walia, A. Kashi, B. Bandyopadhyay, N. Hyder, S. Mahinder, R. Anantha, D. Liu,
S. Gondala. *Retrieval Augmented Correction of Named Entity Speech Recognition Errors*.
[arXiv:2409.06062](https://arxiv.org/abs/2409.06062), 2024-09-09.

[2] N. Yamashita, M. Yamamoto, H. Kokubo, Y. Kawaguchi. *LLM-based Generative Error Correction for
Rare Words with Synthetic Data and Phonetic Context*.
[arXiv:2505.17410](https://arxiv.org/abs/2505.17410), 2025-05-23.

[3] D. Siskos, S. Papadopoulos, P. Peso Parada, J. Zhang, K. Saravanan, A. Drosou. *Retrieval
Augmented Generation based context discovery for ASR*.
[arXiv:2509.19567](https://arxiv.org/abs/2509.19567), 2025-09-23.

[4] T. Fan, J. Wang, X. Ren, C. Huang. *MiniRAG: Towards Extremely Simple Retrieval-Augmented
Generation*. [arXiv:2501.06713](https://arxiv.org/abs/2501.06713), 2025-01-12.

[5] P. Shen, X. Lu, H. Kawai. *Retrieval-Augmented Speech Recognition Approach for Domain
Challenges*. [arXiv:2502.15264](https://arxiv.org/abs/2502.15264), 2025-02-21.

---

## Appendix — reproduction

| section | record | command |
|---|---|---|
| §3 | `wiki/medicoes/composicao-do-erro-e-o-que-cada-remedio-alcanca.md` | `eval/analyze_error_composition.py` |
| §4.1 | `wiki/medicoes/e0-instrumento-de-confianca.md` | `common/ctc.greedy_palavras` |
| §4.2 | `wiki/medicoes/e1-portao-de-confianca.md` | `probes/portao_correcao_probe.py --curva --n 100` |
| §5 | `wiki/medicoes/e2-correcao-com-portao.md` | `probes/portao_correcao_probe.py --corrigir --n 100 --tau 1.0` |
| §6 | `wiki/medicoes/e4-custo-do-beam.md` | `probes/beam_ctc_probe.py --larguras 2 4 8` |
| protocol | § 8 of this paper | pre-registered predictions and kill criteria |
| decision | `wiki/decisoes/0005-orcamento-da-correcao-pos-decode.md` | what the numbers decided |
