# System Design Audit — `training/` (Macaw Voice, milestone M4)

- Target: `/home/paulo/Projetos/jvscribe/training`
- Date: 2026-07-25 · Mode: `full` (phases 1–6) · Severity gate: `medium`
- Auditor: chief-system-designer (Staff-level system design review)
- Scale: 5 Python files, 571 LOC (+ runbook 81, tests 74) — **small, offline batch tooling**

---

## 1. Executive summary

`training/` is the M4 corpus-preparation tooling for an on-CPU PT-BR ASR pilot. It
contains **exactly one production artifact** — `prep_icefall.py`, the corpus adapter —
surrounded by a **superseded / smoke cluster** (`prep_fleurs.py`, `train_ctc.py`,
`decode_ctc.py`, `gen_phonemes.py`). The central architectural decision (reuse the real
icefall training recipe, own only the data prep — Unbreakable Rule 9) is **correct and
well documented**, and is the strongest thing about this codebase.

These are one-shot batch scripts run on a rented GPU instance. There is **no request
path, no server, no live database, no hot-path concurrency**. Accordingly, Phase 3
(data-flow resilience) and Phase 4 (request-path scaling) are **honestly recorded as
low-relevance / Not Applicable** rather than padded with fabricated circuit-breaker or
N+1 findings. The load-bearing dimensions here are **Boundaries** and **Deletion +
Trade-offs**.

**Overall health: healthy for its stage, with one clear cleanup theme.** 0 critical, 0
high findings. The debt is concentrated in *deletion readiness*: the smoke/superseded
code is entangled with the production surface and duplicates its logic.

### Top 3 system-design risks

1. **A confirmed-buggy smoke trainer lives beside the only production file, guarded only
   by a docstring** (`train_ctc.py:1`). Nothing structural stops a future contributor
   from copying it as "the trainer". Its infra-proof value is already captured in
   `results/m4-smoke-results.md` + CHANGELOG, so it is a net liability. *(Boundaries B1 +
   Deletion D3, medium.)*
2. **Two overlapping prep implementations with a divergent, unversioned filename
   contract.** Production `prep_icefall.py` emits `cv-*_cuts_*`; every smoke consumer
   (`train_ctc`, `decode_ctc`, `gen_phonemes`) reads `fleurs_*_cuts_*` — the output of
   the *superseded* `prep_fleurs.py`. The local tools are wired to the old prep, not the
   pilot's. *(Boundaries B2 + Deletion D1, medium.)*
3. **The PT-BR normalization business rule is duplicated** across the two prep scripts
   (`prep_icefall.py:51`, `prep_fleurs.py:33`) and has already drifted (None-handling).
   A change to the orthography rule must be made in lock-step or training targets
   silently diverge. *(Deletion D2, medium — DRY on a business rule.)*

---

## 2. Scope & methodology

- **Analyzed:** all 5 `.py` files in `training/`, the runbook, the test file, and the
  smoke results. Cross-referenced CHANGELOG and git history for provenance.
- **Modes run:** full (phases 1–6). Quality gates recorded for phases 2–5 (all passed).
- **Tooling:** `scc` was unavailable (config error) — LOC via `wc`; dependency edges and
  unused imports via `grep`/read (the graph is trivial at 5 files).
- **Discipline:** per the project's `asr-evidence-discipline.md`, every finding carries
  `file:line` evidence and no conclusion exceeds it. Per the audit's own Crying-Wolf
  rule, N/A dimensions were recorded as such instead of fabricated.

### Quality-gate history

| Phase | Score | Status | Note |
|---|---|---|---|
| 2 Boundaries | 0.88 | passed | file:line + prod/smoke distinction; B3 downgraded to low |
| 3 Data Flow | 0.90 | passed | scoped low-relevance; resilience recorded N/A |
| 4 Scaling | 0.90 | passed | request-path N/A; only real note is serial fbank |
| 5 Deletion+Trade-offs | 0.87 | passed | load-bearing output; Rule 9 credited, not criticized |

---

## 3. Module inventory

| Module | Path | LOC | domain_tag | boundary_type | Role |
|---|---|---|---|---|---|
| prep_icefall | training/prep_icefall.py | 141 | corpus_prep | bounded_context | **PRODUCTION** — only pilot code |
| prep_fleurs | training/prep_fleurs.py | 131 | corpus_prep | generic_subdomain | superseded prep (still feeds smoke) |
| train_ctc | training/train_ctc.py | 176 | model_training | generic_subdomain | SMOKE ONLY, confirmed bugs |
| decode_ctc | training/decode_ctc.py | 71 | evaluation | generic_subdomain | smoke decode (imports train_ctc) |
| gen_phonemes | training/gen_phonemes.py | 52 | phonetics | generic_subdomain | G2P targets util |

---

## 4. Findings by severity

**Critical: 0 · High: 0 · Medium: 6 · Low: 5 · Info/positive: several.** For a 571-LOC
offline batch tool, the absence of critical/high is the honest, expected result.

### Medium

| ID | Dimension | Finding | Evidence |
|---|---|---|---|
| B1 | Boundaries | Production artifact + smoke cluster share a flat dir, guarded only by docstrings | `train_ctc.py:1`, all 5 flat in `training/` |
| B2 | Boundaries | Divergent unversioned filename contracts (`cv-*` prod vs `fleurs_*` smoke) | `prep_icefall.py:132` vs `decode_ctc.py:51` |
| D1 | Deletion | `prep_fleurs` superseded but not excisable — feeds 3 smoke files | `prep_fleurs.py:108` → `:28/:142/:51` |
| D2 | Deletion | `normalize_ptbr` business rule duplicated + drifted | `prep_icefall.py:51`, `prep_fleurs.py:33` |
| D3 | Deletion | Confirmed-buggy smoke trainer kept beside production | `train_ctc.py:1`, `results/m4-smoke-results.md` |
| T3 | Trade-offs | "Keep smoke trainer as record" — documented but weakly isolated | `train_ctc.py:15` |

### Low

| ID | Dimension | Finding | Evidence |
|---|---|---|---|
| B3 | Boundaries | `decode_ctc` imports `train_ctc` internals → transitively smoke-only | `decode_ctc.py:20` |
| S1 | Data/State | Inter-stage handoff is an unversioned filename convention, no schema check | `prep_icefall.py:132` |
| SC1 | Scaling | Serial fbank (`num_jobs=1`) / `num_workers=0` — wall-clock cost for 500 h prep | `prep_icefall.py:126` |
| D4 | Deletion | Unused imports `numpy`, `glob` in both prep files | `prep_icefall.py:20,28`; `prep_fleurs.py:16,22` |
| D5 | Deletion | Latent bug: `prep_fleurs` overwrites `transcript_words.txt` per split (test wins) | `prep_fleurs.py:110` |

---

## 5. Findings by dimension

### 5a. Boundaries (score 3/5)

The conceptual boundary — "our owned surface is the prep; training is an external
recipe" — is a good decision. It is **not enforced structurally**: the single production
file and four smoke/superseded files share one flat directory (B1), and the smoke
consumers speak a different on-disk contract (`fleurs_*`) than the production producer
(`cv-*`) (B2). `decode_ctc` binds to `train_ctc`'s model internals (B3, low, acceptable
inside the smoke unit). No circular dependencies; the dependency graph is a shallow DAG.

### 5b. Data Flow & State (score 4/5 — offline-batch context)

Two file-based pipelines (see `figures/data_flow_map.svg`). The production pipeline even
has sensible retry (`curl --retry 3`, `prep_icefall.py:63`). **Resilience patterns
(circuit breaker, backpressure, rate limiter) are Not Applicable** — one-shot batch, no
live consumer; recorded explicitly. The one honest state note (S1): the producer↔consumer
contract is an unversioned filename convention with no schema assertion, which combined
with B2 allows a stale `fleurs_*` file to silently feed the smoke tools.

### 5c. Scaling Readiness (score 4/5 — offline-batch context)

The **request-path scaling checklist (N+1, connection pooling, pagination, rate limiting)
does not apply** — no DB, no server, no hot path. Correctly **vertical**: a single GPU
node, no premature distribution. Only real note (SC1, low): `num_jobs=1` fbank +
`num_workers=0` are serial; fine for the 1 h smoke, a multi-hour wall-clock (billed) cost
for the real ~500 h prep — parametrize `num_jobs` for that run.

### 5d. Deletion Safety (score 3/5)

Where the real debt sits. **Positive:** deprecation is *well-marked* (`train_ctc.py`
docstring is explicit and honest; CHANGELOG records the course-correction). **Negative:**
excisability is poor — `prep_fleurs` is superseded yet feeds three files (D1);
`normalize_ptbr` is duplicated business logic (D2); the buggy smoke trainer persists
beside production (D3); unused imports (D4) and a latent overwrite bug in the superseded
prep (D5) are minor confirmations that the smoke path should be retired rather than
maintained.

### 5e. Trade-offs & Pragmatism (score 4/5)

The **best dimension.** The reuse-real-recipe decision (T1) is documented in runbook +
CHANGELOG + docstring, justified by *measured* evidence (the smoke overfit lesson), and
is textbook Unbreakable-Rule-9 + YAGNI. The "own surface = prep only" isolation (T2) is
likewise sound. The one weak trade-off (T3): keeping the buggy smoke trainer "as a
record" when the record already lives in `results/` — documented, but a copy-paste
hazard. No over-engineering, no premature complexity anywhere.

---

## 6. Scoring card

| Dimension | Score (0–5) | Weight | Rationale |
|---|---|---|---|
| Boundaries | 3 | 0.25 | good intent, not structurally enforced; divergent contracts |
| Data Flow & State | 4* | 0.10 | clean file handoff; resilience N/A (offline) |
| Scaling Readiness | 4* | 0.10 | correctly vertical; minor serial-prep note |
| Deletion Safety | 3 | 0.25 | markers present, but tangling + duplication block excision |
| Trade-offs & Pragmatism | 4 | 0.30 | reuse-recipe decision is Staff-level; one weak keep-smoke call |

**Weighted average ≈ 3.5 / 5** (see `figures/dimension_scores.svg`).
`*` Data Flow & Scaling are scored in the offline-batch context; request-path checks N/A.

---

## 7. Top refactor priorities (severity × blast radius × effort)

1. **Retire or quarantine the smoke cluster** (D3 + B1). Move `train_ctc.py`,
   `decode_ctc.py` (and `prep_fleurs.py`, `gen_phonemes.py` if the whole smoke path is
   done) to `training/smoke/`, or delete them — the lesson is in `results/`. *Highest
   value, low effort, removes the copy-paste hazard.*
2. **Consolidate onto `prep_icefall`** (D1 + B2). Delete `prep_fleurs` and repoint any
   surviving consumer to the `cv-*` contract, or parametrize the manifest name. *Removes
   the second prep implementation and the divergent contract.*
3. **Extract `normalize_ptbr` to `training/text_norm.py`** (D2), imported by both callers
   and covered by the existing normalization tests. *Kills the DRY drift regardless of #1/#2.*
4. **Remove the 4 unused imports** (D4) — trivial, a lint gate would catch it.
5. **Parametrize `num_jobs`** for the 500 h prep (SC1) before the billed real run.

---

## 8. ADR suggestions

- `adr-suggestions/000X-m4-reuse-icefall-recipe.md` — promotes the (already-documented)
  reuse-real-recipe trade-off from the runbook to a formal MADR ADR alongside M2's
  `0001`, so it is discoverable and survives runbook churn. *(Only `suggests_adr=1`
  finding; the decision itself is endorsed, not challenged.)*

---

## 9. What was NOT analyzed (honest limitations)

- **The real training loop / loss / model** — these live in the external icefall recipe
  (correctly reused per Rule 9) and are **out of scope**; the audit covers only the
  repo-owned prep + smoke code.
- **Runtime correctness of the pipeline on real hardware** — this is a static system-
  design review, not execution. The `train_ctc` bugs are taken from the project's own
  confirmed record, not re-measured here.
- **WER / RTFx quality** — a modeling concern owned by the ASR agents, not a system-
  design dimension.
- **Data-flow resilience & request-path scaling** — deliberately N/A: no live service
  exists to protect. If `training/` ever grows a serving surface, re-run phases 3–4.
- **`scc` complexity metrics** — tool unavailable; LOC via `wc`, coupling by inspection
  (trivial at 5 files).

---

## 10. Threshold sourcing legend

- **consensus** — DRY on a business rule (D2); unused import = dead (D4); correctness bug
  (D5). Widely-agreed defects.
- **default** — none applied (no feature-flag age / queue thresholds relevant here).
- **heuristic** — module/dir isolation (B1), interface/contract divergence (B2), module
  excisability & tangle (D1, D3), serial-prep wall-clock (SC1), implicit-contract
  (S1). Judgment calls, marked as such.
