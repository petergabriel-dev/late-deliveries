---
id: ADR-0002
title: Python + uv + Makefile stack; raw CSVs committed with checksums
status: Active
date: 2026-11-13
kind: engineering
judgment_call: none
readWhen: Changing dependencies, the Makefile, the Python version, or raw data handling
---

# ADR-0002: Python + uv + Makefile stack; raw CSVs committed with checksums

## Options considered

Stack:

- Python + uv + Makefile, plain scripts — one language most reviewers read; uv lockfile pins exact versions; `make` is universal.
- R + renv + targets — strongest causal toolkit (fixest, rdrobust, MatchIt, sensemakr) and cached pipeline steps; smaller reviewer pool and one more framework.
- Python + notebooks — readable narrative; hidden state, harder to test, weakens the one-command rebuild.

Raw data:

- Kaggle API fetch + checksums — small repo; every reviewer needs a Kaggle token.
- Commit `archive.zip` (44.7MB) + checksum, extract in `make` — one file under GitHub's 50MB warning.
- Commit the extracted CSVs + per-file `SHA256SUMS` — zero setup and browsable on GitHub; 126MB in history, 61MB geolocation file triggers GitHub's warning.
- Manual download instructions — simplest to build; not one command and easy to get wrong.

## Decision

- Python 3.12 (`.python-version`), managed by uv; `uv.lock` pins exact versions. Code lives in scripts under `src/late_delivery/`, never notebooks.
- `Makefile` is the single entry point; targets grow through Phase 1 until `make all` rebuilds everything.
- Dependencies are added only when a task needs them. Phase 1: pandas, pyarrow, numpy, matplotlib, pytest (dev). Phase 2+ libraries (pyfixest, rdrobust, PySensemakr) arrive with their phase.
- The 9 Olist CSVs are committed unmodified in `data/raw/` with per-file `SHA256SUMS`; `make check-data` verifies them before anything reads data. `docs/archive.zip` stays local and gitignored.
- Data license CC BY-NC-SA 4.0, confirmed by the project owner on the Kaggle page on 2026-11-13; attribution and share-alike notice in `data/raw/README.md`.

## Why

- Project owner chose Python + uv + Makefile with scripts (discuss session, 2026-11-13): broadest reviewer reach, exact rebuilds, no extra framework.
- Project owner chose committing extracted CSVs over the Kaggle fetch and the committed zip: a cold reviewer needs no credentials and can read the raw files on GitHub.
- Per-file checksums prove the committed files match the published dataset byte for byte.

## Falsification test

- A fresh clone on another machine fails `uv sync && make all`, or produces different outputs: the locking or entry point is insufficient.
- GitHub rejects a push or the repo becomes impractical to clone: move the data to the committed zip or Git LFS.
- A method the pre-registration requires has no maintained Python implementation: revisit the language for that step only.

## Affects

Docs:

- `data/raw/README.md`
- `docs/engineering/dev-workflow.md`

Code:

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `Makefile`
- `.gitignore`
- `data/raw/SHA256SUMS`

## Consequences

- Good: one command and exact versions; no credentials needed to rebuild.
- Good: the integrity check runs before every data step.
- Bad/risk: 126MB of CSVs stay in git history permanently; GitHub warns on the 61MB geolocation file.
- Bad/risk: the lockfile resolves pandas 3.x, whose copy-on-write and string-dtype defaults differ from older pandas examples.
- Bad/risk: `make check-data` uses `shasum`, which needs Perl on Linux (preinstalled on most distributions).

## Read when

- adding or upgrading a dependency
- changing the Makefile, Python version, or how raw data is stored or verified

## Supersedes

- None
