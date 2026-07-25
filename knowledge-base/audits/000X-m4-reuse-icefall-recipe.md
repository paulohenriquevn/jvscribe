# ADR 000X — M4 pilot reuses the real icefall recipe; our owned surface is data prep only

- Status: proposed (draft suggested by system-design audit 2026-07-25)
- Deciders: project owner
- Date: 2026-07-25
- Context tags: M4, training, Unbreakable Rule 9 (Don't Reinvent)

## Context and problem statement

The M4 pilot must train Zipformer-CTC on ~500 h of PT-BR and produce a WER × RTFx
curve. An early self-contained wrapper (`training/train_ctc.py`) proved the GPU/k2/
corpus infra but reproduced a class of bugs the icefall authors already solved
(missing `src_key_padding_mask`, ad-hoc phoneme head, size configs derived by scaling
instead of copied from RESULTS.md). It also overfit (WER train 18 % vs held-out 99 %),
which masked those defects. How should the pilot be structured to avoid re-deriving a
tested training loop?

## Decision drivers

- Unbreakable Rule 9 — do not reinvent a battle-tested training recipe.
- Evidence discipline — the wrapper's bugs were confirmed against `AsrModel`.
- Minimal owned/maintained surface — fewer lines we must test and debug.

## Considered options

1. **Reuse the real icefall recipe** (`train.py` / `model.py` / `asr_datamodule.py`
   with `--use-ctc 1 --use-transducer 0`); own only a corpus adapter that emits cuts
   in the exact format the datamodule loads.
2. **Keep/extend the self-contained wrapper** (`train_ctc.py`).
3. **Fork/vendor the icefall recipe** into this repo.

## Decision outcome

Chosen: **Option 1**. The only code we own is `training/prep_icefall.py`, which emits
`cv-{lang}_cuts_{train,dev,test}.jsonl.gz` + fbank so the recipe runs unmodified. The
phoneme-supervision ablation is added as a second head on the recipe's `model.py`, not
a new wrapper.

### Consequences

- Positive: eliminates the wrapper's bug class; recipe stays upgradable; owned surface
  is ~140 LOC + tests.
- Negative: our contract is an on-disk filename/format the datamodule expects — it must
  be kept in sync with the upstream recipe version (see audit finding B2/S1).

## Why this ADR is being suggested

The decision is already documented in `training/run_pilot_icefall.md`, the CHANGELOG,
and the `train_ctc.py` docstring — but not as a formal ADR alongside M2's
`knowledge-base/adrs/0001-m2-architecture-finalists.md`. Promoting it makes the decision
discoverable and durable against runbook churn. This draft is a suggestion only; the
audit does not create ADRs in the repo.
