---
id: ADR-0006
title: Money framing - three loss channels priced as platform revenue, assumptions in one file (JC 6)
status: Active
date: 2026-11-13
kind: analytical
judgment_call: 6
readWhen: Translating effects into money or adding any money assumption
---

# ADR-0006: Money framing - three loss channels priced as platform revenue, assumptions in one file (JC 6)

## Options considered

Which loss channels to price:

- Repeat loss measured; rating spillover as a labeled scenario; operating costs listed but unpriced — "at least X (measured) to Y (if rating effects hold)".
- Repeat loss only — fully traceable to data; likely understates the cost and may collapse to "can't tell".
- All three channels, with assumptions where data is missing — fullest figure, but two channels rest entirely on outside assumptions.

Money unit:

- Platform revenue = lost order value (GMV) x take rate — comparable to an investment the marketplace pays for; adds a take-rate assumption.
- GMV only — straight from data, but overstates what the company loses by 1 / take rate.
- Contribution margin — economically most correct; needs a margin structure the data lacks.

Presenting assumptions:

- One versioned assumptions file, with measured and assumed parts shown separately in the memo.
- The same file, but one combined range in the memo — simpler, but hides which part is evidence.

## Decision

- Price all three channels (project owner chose this over the recommended option, discuss session 2026-11-13):
  1. Lost repeat purchases by the affected customer — measured from data where detectable (ADR-0004), otherwise an upper bound.
  2. Rating spillover: lower ratings reduce sales to other buyers — outside assumptions only.
  3. Operating costs such as support contacts and refunds — outside assumptions only.
- Money unit: platform revenue = lost GMV x an assumed take-rate range. Lost GMV is shown alongside.
- Compute in BRL; convert to USD at a stated 2017-2018 period-average rate, with the rate and its source recorded.
- One version-controlled assumptions file holds every money input: value, low, high, source, and a tag (measured or assumed). The sensitivity analysis reads from that file.
- The memo shows the measured part of the range separately from the assumption-driven part.
- No invented values: every assumed input cites a source or is explicitly labeled an illustrative assumption.
- Deferred to the Phase 4 plan: the GMV definition (item price, or price plus freight), the assumptions file's path and format, and the exchange-rate source.

## Why

- Project owner's choices on channels, money unit, and the guardrail (discuss session, 2026-11-13).
- Leadership will compare the figure against a logistics investment the marketplace pays for, so platform revenue is the comparable unit.
- Two channels have no support in the data; keeping them in a sourced, versioned file preserves "every number traces to code or the assumptions file".

## Falsification test

- No credible source exists for the take rate, rating spillover, or operating costs: those channels must be labeled illustrative, or this ADR superseded to drop them.
- The sensitivity analysis shows one unsourced assumption flips the recommendation: the conclusion rests on a guess, and the memo must say so.
- The assumed channels make up nearly all of the range: the "measured" figure is too small to anchor the decision, and the memo must lead with the assumptions.

## Affects

Docs:

- `docs/engineering/invariants.md`

Code:

- None yet (the assumptions file and money translation arrive in Phase 4)

## Consequences

- Good: the fullest dollar range, with every input versioned and sourced.
- Good: readers see which part of the range is evidence and which is assumption.
- Bad/risk: channels 2 and 3 have no in-data support and invite challenge; the memo must label them clearly.
- Bad/risk: the range may be wide and driven mostly by outside assumptions.

## Read when

- building the money translation or the assumptions file
- adding or changing any money assumption

## Supersedes

- None
