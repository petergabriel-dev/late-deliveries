---
id: ADR-0014
title: Phase 4 money reading - about R$2 per late delivery, almost all assumption-driven; the review horizon drives the range (JC 6)
status: Active
date: 2026-11-16
kind: analytical
judgment_call: 6
readWhen: Reporting or interpreting the Phase 4 money figures, or writing the Phase 5 memo and write-up
---

# ADR-0014: Phase 4 money reading - about R$2 per late delivery, almost all assumption-driven; the review horizon drives the range (JC 6)

Applies the ADR-0013 rules to the first Phase 4 run. Flags are as computed by `money.py` (`outputs/money.json`, commit e1cf588); every number below is copied from `outputs/money.json`. Money is platform revenue per late headline order (6,518 late orders, 6,366 with a review), in BRL, with USD at R$ 3.33054 per US$.

## Options considered

How to read the flags:

- Apply the ADR-0013 rules as computed and explain each fired flag — the rules were fixed before the run.
- Dismiss a fired flag — not open: ADR-0013 says a fired flag stands.
- Change an input after seeing the figures (e.g. a shorter central horizon) — not open: it would supersede ADR-0013 after results were seen.

How the memo states the figure:

- The range with the assumptions first: about R$2 per late delivery (R$0.60-4.42), almost all through ratings, with the measured repeat loss stated beside it — meets flag 1.
- A measured floor and a scenario ceiling (R$0 to 0.13 measured; up to R$4.42 if rating effects hold) — most conservative; reads as "can't tell" and drops the central figure.
- Lost order value first (R$10.33 GMV) — larger, but ADR-0006 chose platform revenue as the unit leadership compares with investment.

Flag 2 (the illustrative horizon drives the range):

- The flag stands; the memo shows the 30-, 90- and 180-day figures and names a follow-up measurement.
- The flag stands; the memo shows the three figures only — leaves the main uncertainty without a way to reduce it.

The operating-cost add-on (about 3x the headline central):

- A separate caveat line outside the range, flagged as the next number to measure — as ADR-0013 §4 fixed.
- The technical write-up only — keeps an unsourced number off the memo, but hides a possibly larger cost.
- Inside the range — contradicts ADR-0013 §4.

Recommendation wording:

- Break-even plus promise-first, with a test before padding promises.
- The same, plus a break-even that includes the illustrative support cost — puts an unsourced number into the recommendation.

## Decision

Project owner, 2026-11-16 (build session, T29). The first option in each group above.

### The figure

| Case | Channel 1: repeat (measured) | Channel 2: rating spillover | Total, BRL | Total, USD | Lost GMV, BRL |
|---|---|---|---|---|---|
| Low | 0.000000 | 0.597399 | 0.597399 | 0.179370 | 2.986993 |
| Central | 0.061858 | 2.003649 | 2.065507 | 0.620172 | 10.327533 |
| High | 0.125517 | 4.294103 | 4.419620 | 1.326998 | 22.098101 |

- The range is bounds (every input at its low-cost or high-cost end), not a confidence interval (ADR-0013 §5).
- Memo wording: a late delivery costs the platform about R$2 in commission (R$0.60-4.42; US$0.18-1.33). Almost all of it comes through lower ratings cutting the seller's later sales, which rests on outside estimates. The directly measured repeat-purchase loss is about 6 centavos.

### Flags (ADR-0013 §6)

| Flag | Test | Value | Result |
|---|---|---|---|
| 1 | ADR-0006: the assumed channels make up nearly all of the range | channel 1 share of the central total 0.029948 (rule: < 0.10) | **fired** |
| 2 | ADR-0006: one unsourced assumption flips the recommendation | largest tornado swing: `horizon_days` (illustrative) | **fired** |
| 3 | ADR-0012: the disruption scenario changes the recommendation | scenario central 2.145512, inside [0.597399, 4.419620] | not fired |

### Flag 1: the memo leads with the assumptions

- The measured channel is 3.0% of the central figure. Channel 2 carries the rest, and its ε comes from Wayfair product ratings and Yelp restaurant ratings (ADR-0013 §8).
- The memo states the figure and, in the same sentence, that it rests on outside estimates; the measured repeat loss is quoted beside it.

### Flag 2: the review horizon drives the range

| Tornado row | Low-cost end | High-cost end | Swing |
|---|---|---|---|
| `horizon_days` (illustrative: 30 / 90 / 180 days) | 0.994650 | 3.159372 | 2.164722 |
| `epsilon` (sourced: 0.05 / 0.075 / 0.10) | 1.397624 | 2.733390 | 1.335766 |
| `repeat_window_180d` | 2.003649 | 2.195322 | 0.191673 |
| `star_drop_bins` (95% CIs) | 1.986190 | 2.144824 | 0.158634 |
| `repeat_effect_90d` (95% CI) | 2.003649 | 2.129166 | 0.125517 |
| `take_rate` (0.20 fixed) | 2.065507 | 2.065507 | 0.000000 |

- The flag stands. How long a bad review keeps hurting the seller's sales has no source; at 30, 90 and 180 days the central figure is R$0.99, R$2.07 and R$3.16.
- The central horizon stays 90 days (ADR-0013).
- Follow-up named in the memo: measure how long a review affects a seller's sales on Olist's own channel data; that would replace the illustrative horizon with a measured one.
- Fewer late orders have a full horizon inside the data as H grows: 5,803 at 30 days, 5,329 at 90 and 2,760 at 180 (eligible late orders with a review, `exposure.*.eligible` summed over the four bins).

### Operating costs: a separate caveat line

| Case | BRL | USD |
|---|---|---|
| Low | 3.03 | 0.909762 |
| Central | 6.32 | 1.897590 |
| High | 13.16 | 3.951311 |

- Outside the range, the tornado and flags 1-2 (ADR-0013 §4). Contacts per late order have no source; the cost per contact is an industry survey.
- Memo wording: if each late delivery also triggers one support contact (unmeasured), add about R$6. It is the most important number to measure next, from Olist's support data.

### Disruption scenario (ADR-0012): the fragility does not move the money

- With the Feb-Mar 2018 surge and the May 2018 strike excluded (3,772 late orders, 3,672 with a review), the cost per late delivery is 0.578547 / 2.145512 / 4.292787 (low / central / high), against 2.065507 central for the headline. Flag 3 does not fire.
- The check-10 model (a) estimate in `money.json` is 0.491795, equal to `robustness.json` check 10, so ADR-0013's frame test holds.
- ADR-0012's fragility on disruption periods is real for the review effect but does not change the money reading. The re-fit star drops are slightly smaller in three of the four bins, while the late orders that remain have larger 90-day seller exposure in three of the four (1-2 days: 90.689347 against 75.249178 for the headline; 8-14 days level), so the central figure moves up slightly.

### ADR-0012's lateness-mix numbers are confirmed from code

| Headline mix x Phase 2 bins | Check-10 mix x Phase 2 bins | Predicted drop | Observed drop | Explained |
|---|---|---|---|---|
| 0.520552 | 0.506594 | 0.013958 | 0.024461 | 0.570605 |

- These reproduce ADR-0012's exploratory 0.5206, 0.5066 and 0.0140, so ADR-0012's falsification test does not fire. The memo and write-up may quote them from `money.json` (invariant 6).

### Recommendation (brief Phase 4 exit)

- Break-even: fund faster logistics only where it avoids a late delivery for under about R$2 of platform revenue (R$0.60-4.42; US$0.18-1.33).
- Promise-first: make promised dates accurate before buying speed. A broken promise hurts reviews as much as about 105 extra delivery days (105.173405: `low_review/c` broken-promise effect over the effect of one extra delivery day; a ratio of point estimates without a CI).
- Test longer promised dates before rolling them out: the data has no checkout conversion, so their cost is unmeasured.
- Annual illustration: about 3,911 late orders a year at this dataset's volume, R$8,078 (US$2,425) a year at the central figure. It is labeled illustrative because the dataset may not be Olist's full volume.

## Why

- ADR-0013 fixed every rule before the run; reading the flags as computed keeps that order.
- Flag 1 is a statement about evidence: a reader must know that 97% of the figure rests on outside estimates before using it.
- Flag 2 points at the one input with no source at all; showing its three values and how to measure it turns the weakness into the next step.
- The support-cost line could exceed the headline, so hiding it would understate the cost; promoting it would put an unsourced number at the center. A caveat line does neither.
- The break-even is the decision rule leadership can use without knowing an investment's cost; the promise-first point uses only pre-registered effect sizes (ADR-0007 §5).

## Falsification test

- A correction to `money.py`, `build.py` or `assumptions.toml` changes any number quoted here: this reading is void, and a superseding ADR is needed.
- Evidence that buyers on Olist's channels do not see seller ratings: channel 2's mechanism fails, the figure falls to the measured R$0 to 0.13, and the memo must change.
- A measured review-persistence horizon outside 30 to 180 days: the true figure lies outside this range; re-run with the measured horizon under a new ADR.
- Measured support contacts per late order: the operating-cost line becomes sourced and joins the range under a new ADR (ADR-0013 §4).
- The memo or write-up quotes a money number that is not in `money.json` or `assumptions.toml`: invariant 6 is broken.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0006-money-framing.md` (its falsification tests 2 and 3 fired as flags 2 and 1; text unchanged)
- `docs/engineering/decisions/ADR-0012-phase3-robustness-reading.md` (its exploratory numbers confirmed; text unchanged)
- `docs/engineering/decisions/ADR-0013-phase4-implementation-choices.md` (rules applied here)
- `README.md` (Phase 4 status and answer; planned, T30)

Code:

- `src/late_delivery/money.py` (computes the figures and flags quoted here)

## Consequences

- Good: the brief's Phase 4 exit is met: a dollar range with explicit assumptions, a sensitivity on each, and a recommendation.
- Good: the disruption-period fragility is shown not to matter for the money, and ADR-0012's exploratory numbers now come from code.
- Bad/risk: 97% of the central figure rests on ε from other settings and on an unsourced horizon; the range is wide (R$0.60 to 4.42).
- Bad/risk: the illustrative support-cost line could be larger than the headline itself.
- Bad/risk: the take rate is Olist's gross commission, so platform revenue may be overstated if Olist pays channel fees out of it.
- Bad/risk: the annual illustration (R$8,078) uses this dataset's volume and is small; it is not a statement about Olist's total cost.

## Read when

- writing the Phase 5 memo or technical write-up
- reporting or interpreting any Phase 4 money figure, flag or tornado row
- planning follow-up measurements (review persistence, support contacts, seller-rating visibility)

## Supersedes

- None
