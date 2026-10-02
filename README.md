# jvscribe — real-time Brazilian Portuguese transcription, on CPU

Transcribe Brazilian Portuguese customer-service calls **live, on the agent's own
laptop** — no GPU, no audio sent to the cloud, no per-hour transcription cost.

The bet is **specialization**: a model that only does telephone PT-BR fits in tens of
millions of parameters, where a 600M multilingual model cannot reach real time on CPU.

Scope of this repository: **the model** and **the inference engine**. Fleet platform,
LGPD compliance and UI are out of scope ([`ROADMAP.md`](ROADMAP.md) § Scope).

---

## Project status

The project runs as **continuous, evidence-driven discovery**: the architecture is not
chosen by conviction, it is measured. Progress is tracked by milestones (`ROADMAP.md`, M0–M9).

| Milestone | Status |
|---|---|
| M0 — Runtime foundation · M1 — Instrumentation | ✅ done |
| M2 — Architecture decision · M3 — Corpus | ✅ done |
| M4 — Comparative pilot | ✅ done |
| M5 — Model at scale | ⚠️ 2/3 DoDs — telephone audio was **deferred** for lack of data ([evidence](wiki/medicoes/m5-modelo-final.md)) |
| M9 — Artifact governance and reproducibility | ✅ done |
| M6 — Optimized runtime | 🔬 being measured ([per-operator profile](wiki/medicoes/m6-profile-por-operador.md), [live NFRs](wiki/medicoes/m6-rnf-ao-vivo.md)) |
| M7 — Product scope · M8 — Pilot | ⏳ next |

> This table mirrors `ROADMAP.md`, which is the source of truth. A test
> ([`test_readme_links.py`](jvscribe/tests/test_readme_links.py)) guarantees that every internal
> link here resolves — on 2026-07-30, 5 out of 5 pointed to files deleted by mistake.

### The architecture, decided by measurement

Out of 5 candidates evaluated against 8 criteria, the **CTC/transducer** family won the
CPU-speed criterion (M2). The M4 comparative pilot then **locked the finalist**:
**Zipformer-CTC `medium` (64M), int8, with an auxiliary phoneme head** —
[ADR 0003](wiki/decisoes/0003-finalista-medium.md), which supersedes the size axis of
[ADR 0002](wiki/decisoes/0002-zipformer-ctc-small.md) after soak and load measurements.

`[MEDIDO]` Head-to-head at equal parameter count: Zipformer beats Conformer on both accuracy
axes (WER 28.86% vs 31.57%, with the 95% CI of the delta excluding 0). The phoneme head took the
medium model to **27.49% WER** ([evidence](wiki/medicoes/m4-cabeca-de-fonema-no-medium.md)).

**The M2 finding that drove the choice of family** `[MEDIDO]`: on CPU, on the same machine and the
same 12 s clip, the transducer is **~2× faster** than AED at comparable size —
Zipformer 20M = 15.90 ± 2.06× real time vs Moonshine tiny 27M = 7.93 ± 0.72×
(n=10, clean statistical separation;
[full measurement](wiki/medicoes/m2-rtfx-candidatos.md)). The reason is
architectural: AED is autoregressive (cost grows with the generated tokens), while
transducer/CTC does a single pass (cost fixed by the audio frames).

> Honesty note: these numbers were measured on a **dev machine, not on the BYOD fleet's
> floor hardware** (still `[DESCONHECIDO]`) — what transfers is the *ratio between
> architectures*, not the absolute value. The "~2×" magnitude needs confirmation under
> soak with concurrent load in M4; reporting dispersion already lowered an earlier
> "~3×" estimate (the difference was CPU load).

---

## The shipped model

**`jvscribe-ptbr-zipformer-ctc-64m`** — 64M-parameter Zipformer-CTC, int8, with an auxiliary
phoneme head. Published at `paulohenriquevn/jvscribe` (Hugging Face, private).

| | value | condition |
|---|---|---|
| WER | **15.99%** | FLEURS pt_br `test[0:100]`, 2,552 words, greedy CTC |
| CER | **7.30%** | same |
| RTFx | **40.0×** | 12-core i7, ONNX int8, 4 threads, load average < 1 |

`[MEDIDO]` 2026-07-31 and **reproduced from the Hugging Face download**, not from local
files ([evidence](wiki/medicoes/reprodutibilidade.md)): sha256 and
`vocab_fingerprint` match the model card, and the published checkpoint loads, encodes
PT-BR and accepts training.

Of the two M5 candidates that shared the artifact, the official one was chosen by **paired
bootstrap** — 95% CI of the delta in [−2.25, −0.43] pp, not crossing zero. `model_card.json` is
the authority on which weights run; a file name knows nothing about WER.

> The previous number in this README (27.49%) was the **M4** deliverable, one generation back.

**Honest limits:** WER on 8 kHz telephone audio and on spontaneous call-center speech remains
`[DESCONHECIDO]` — FLEURS is read news. And the model is **not streaming**: it is non-causal,
used live through a sliding window ([why](docs/ARCHITECTURE.md)).

## Running

```bash
pip install -r requirements-eval.txt        # onnxruntime, lhotse, soundfile
export JVSCRIBE_MODEL_DIR=/path/to/artifact # or let models/current point to it

# batch — a folder of audio files in any format
python3 jvscribe/batch/batch_transcribe.py --input-dir ./audios --out-dir ./output

# live, both sides of the call (ATENDENTE = mic · CLIENTE = loopback)
python3 jvscribe/realtime/live_transcribe.py --duracao 60 --relatorio evidence.md
```

Real time requires `pulseaudio-utils` (`parec`, `pactl`) — capture must bind each
stream to its own source, and `sounddevice` does not expose monitor sources.

| tool | purpose |
|---|---|
| [`jvscribe/bench/runtime_bench.py`](jvscribe/bench/runtime_bench.py) | ONNX configuration sweep with paired bootstrap |
| [`jvscribe/bench/stress_test.py`](jvscribe/bench/stress_test.py) | soak with the real model — minute-by-minute degradation |
| [`jvscribe/bench/finetune_smoke.py`](jvscribe/bench/finetune_smoke.py) | proves a checkpoint loads, encodes PT-BR and trains |
| [`jvscribe/eval/compare_models.py`](jvscribe/eval/compare_models.py) | compares two models on the same yardstick, with CIs |
| [`jvscribe/bench/calibrate.py`](jvscribe/bench/calibrate.py) | **calibrates the runtime for the target machine** — run it when you change CPUs |

---

## Finding your way around

The knowledge base under `wiki/` is written in Portuguese.

| Document | Role |
|---|---|
| [`docs/CALIBRATION.md`](docs/CALIBRATION.md) | **Calibration runbook** — what is portable across CPUs and what must be re-measured |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **How the model and the engine work** — graph, stacks, per-operator cost, batch and real-time pipelines |
| [`ROADMAP.md`](ROADMAP.md) | Milestones M0–M9 with Definition of Done, scope, constraints and open questions |
| [`wiki/medicoes/`](wiki/medicoes/) | Every measurement, with hypothesis, evidence and limitations kept separate |
| [`wiki/log.md`](wiki/log.md) | Project history in chronological order |
| [`wiki/`](wiki/index.md) | **Knowledge base** in Open Knowledge Format — model, engine, training, optimization, measurements and decisions |
| [`wiki/decisoes/`](wiki/decisoes/index.md) | ADRs — what was locked, with rationale and alternatives |
| [`wiki/disciplina/`](wiki/disciplina/index.md) | Evidence contract — every number carries a provenance label |

## Evidence discipline

Every number in this project carries a label: `[MEDIDO]` (measured: we ran the experiment),
`[LITERATURA]` (literature: reported by a third party), `[FONTE-REPO]` (source repo: a fact read
in the code of a cloned peer), `[ESTIMATIVA]` (estimate: derived by calculation) or
`[DESCONHECIDO]` (unknown). Without a label, the number does not exist. It is the vaccine against
deciding by a benchmark that does not transfer.
