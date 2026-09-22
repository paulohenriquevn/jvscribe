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

- Corpus preparation can cycle download and preparation so the source shards leave disk
  before the next group arrives (`prepare_corpus_streaming.py`). Downloading all 157
  shards up front leaves 107.7 GB of parquet idle until extraction ends, which makes the
  source data — not the features — the dominant term of peak disk. Cycling drops peak at
  1,500 h from 166.0 GB to 57.9 GB, and raises the corpus a 117.5 GB session disk can hold
  from 800 h to ~2,900 h. Resumable: a cycle whose manifest already exists is skipped.
  (`docs/plans/m10-sota-ptbr.md` T3, step 2)
- Paste-and-run Colab cell that builds the ~1,500 h bake-off corpus end to end: projects
  peak disk and refuses to start when it will not fit, downloads stratified shards,
  prepares them in cycles, and reports kept hours against the target.
  (`docs/notebooks/m10-celula-corpus-1500h.py`)

### Fixed
- Corpus preparation can write its output to persistent storage while keeping throwaway
  intermediates on local disk (`--scratch`). Colab erases `/content` when the VM
  restarts, taking hours of already-paid extraction with it; resume protected against the
  script dying, not against the disk disappearing. The cell now targets a mounted Drive
  when one is available, checks it has room before starting, and says plainly when the
  output will not survive a restart. The wav and parquet files stay local — they are
  deleted minutes after being written, and sending them over the Drive's network would
  pay for bytes already condemned.
  (`jvscribe/finetune/prepare_corpus_streaming.py`, `docs/notebooks/m10-celula-corpus-1500h.py`)
- Changing `--horas-alvo` between runs against the same output directory now fails
  instead of producing a corpus built from two different plans. Resume skips a cycle by
  manifest name, while which shards the plan wants comes from `select_indices`, which
  depends on the target — so a changed target left completed cycles holding shards the
  new plan never chose, with nothing failing and the audit list describing only half of
  it. (`jvscribe/finetune/prepare_corpus_streaming.py`)
- Shard downloads now survive an unstable CDN and never publish a half-written file.
  `curl --retry` alone does not repeat HTTP/2 framing errors (exit 92) — by default it
  only repeats timeouts and 408/429/5xx — so one such error on shard 00057 aborted a
  1,500 h run in its first cycle. Downloads now use HTTP/1.1 with `--retry-all-errors`,
  land in a `.part` file promoted by an atomic rename, and are rejected unless both PAR1
  magics are present, which `st_size > 0` cannot tell apart from a shard truncated by a
  dead session. (`jvscribe/finetune/download_tagarela_subset.py`)
- A shard that still fails after its retries no longer destroys the run. It is counted,
  named in `shards_perdidos.txt` alongside the hours it cost, and only aborts when more
  than 10% of a cycle is lost — which is the network being down, not a bad shard.
  (`jvscribe/finetune/prepare_corpus_streaming.py`)
- The corpus cell checks its dependencies before doing any work, echoes per-batch
  progress rather than only per-cycle, and appends to its log instead of truncating it.
  A restarted runtime loses everything the setup cells installed, and the script would
  otherwise only import lhotse after hours of downloading and extraction; a cycle takes
  ~20 minutes, so echoing only cycle boundaries left the screen frozen; and truncating
  the log on resume erased the record of the run that died, which is the one worth
  reading. (`docs/notebooks/m10-celula-corpus-1500h.py`)
- The corpus cell now syncs its clone and verifies the script it is about to run exists,
  instead of surfacing Python's bare `exit status 2` for a missing file — an error that
  says nothing about the clone being out of date. It also streams the subprocess output
  live while writing it to `/content/corpus.log`, so a five-hour run is neither invisible
  while it works nor unreadable when it fails.
  (`docs/notebooks/m10-celula-corpus-1500h.py`)
- Cut IDs are now unique across the whole corpus rather than within one preparation run.
  Every batch previously restarted its counter at `tagarela_00000000`, so a concatenated
  manifest carried duplicate IDs — lhotse raises nothing for this, and the same utterance
  would have entered training twice, silently. (`jvscribe/finetune/prep_tagarela.py`)
- Bulk decode failures now abort at the batch that caused them instead of only at the end
  of the run. A shard truncated during download used to cost the full feature-extraction
  pass before anyone saw the error. (`jvscribe/finetune/prep_tagarela.py`)
