---
id: ADR-0001
title: Every decision is an ADR, analytical and engineering alike
status: Active
date: 2026-11-13
kind: engineering
judgment_call: none
readWhen: Adding, changing, or auditing any project decision
---

# ADR-0001: Every decision is an ADR, analytical and engineering alike

## Options considered

- Separate analysis log (`docs/decision-log.md`), ADRs only for engineering — one page for reviewers to audit; analysis choices never mix with tooling records. Two systems to maintain.
- ADRs for every decision, template extended — one system that Pi docs tooling validates and indexes. The analysis log is spread over many files next to engineering records.
- One file per brief judgment call plus a hand-kept index — each file can grow with evidence; more files and an index nobody validates.

## Decision

- Record every decision, analytical or engineering, as an ADR in `docs/engineering/decisions/`.
- Extend `ADR-template.md` with frontmatter `kind` (analytical or engineering), `judgment_call` (1-6 or none) and `readWhen`, plus sections "Options considered" and "Falsification test". "Why" holds the reasoning.
- An ADR that settles one of the brief's six judgment calls ends its title with "(JC n)", so the generated index shows the mapping.
- Regenerate `decisions/README.md` only with Pi `/docs update-index`; never edit it by hand.

## Why

- Project owner chose one system over the recommended separate analysis log (discuss session, 2026-11-13).
- Pi docs tooling already validates ADR metadata and regenerates the index, so the log stays consistent at no extra cost.
- The brief requires options, choice, reasoning and a falsification test for every judgment call; the stock template lacked options and falsification.
- The generated index has fixed columns (ADR, Status, Summary, Read when), so the "(JC n)" title suffix is the cheapest way to make the six judgment calls findable.

## Falsification test

- A reviewer starting from `decisions/README.md` cannot find what was decided for a given judgment call, and why, within a few minutes. If so, add a judgment-call index to the repo README or supersede this ADR with a single analysis log.
- Once all six judgment calls are logged (end of Phase 4), any of the six has no ADR tagged with its number.

## Affects

Docs:

- `docs/engineering/decisions/ADR-template.md`
- `docs/engineering/decisions/README.md`

Code:

- None

## Consequences

- Good: one validated decision system with a generated index and per-decision git history.
- Good: every entry carries options and a falsification test, as the brief requires.
- Bad/risk: analytical and engineering records share one folder; readers rely on the index and the "(JC n)" titles to separate them.
- Bad/risk: `kind` and `judgment_call` are not index columns, so they help only readers who open the files.

## Read when

- adding or changing any decision
- auditing the decision log against the brief's six judgment calls

## Supersedes

- None
