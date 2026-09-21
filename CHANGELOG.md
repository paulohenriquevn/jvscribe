# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

> **On the missing history.** This repository was started fresh; the 329 commits that
> precede this file were never mirrored into a changelog. They are not reconstructed here,
> because a reconstruction would be a guess dressed as a record. What those commits produced
> is documented where it was measured: `wiki/medicoes/` for every number, `wiki/decisoes/`
> for every ADR, and `wiki/log.md` for the narrative. Entries below start from the first
> change made after this file existed.
>
> **On issue references.** Rule 6 requires every entry to cite its ticket/issue/PR. No
> tracker is configured for this repository yet; entries cite the on-disk artifact that
> originated them instead. No number has been invented retroactively.

## [Unreleased]

### Added
- Corpus preparation can now run in shard batches, so peak disk usage tracks the batch
  instead of the whole corpus. `prep_tagarela.py --shards-per-batch N` processes N shards
  through decode → wav → fbank before the next group starts, and
  `--drop-audio-after-features` deletes each batch's audio once its features are on disk.
  Without this, 1,500 h of corpus needs ~170 GB of intermediate wav files — more than a
  Colab session disk can hold alongside the source shards and the extracted features.
  (`docs/plans/m10-sota-ptbr.md` T3, step 2)

### Fixed
- Cut IDs are now unique across the whole corpus rather than within one preparation run.
  Every batch previously restarted its counter at `tagarela_00000000`, so a concatenated
  manifest carried duplicate IDs — lhotse raises nothing for this, and the same utterance
  would have entered training twice, silently. (`jvscribe/finetune/prep_tagarela.py`)
- Bulk decode failures now abort at the batch that caused them instead of only at the end
  of the run. A shard truncated during download used to cost the full feature-extraction
  pass before anyone saw the error. (`jvscribe/finetune/prep_tagarela.py`)
