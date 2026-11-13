---
id: ADR-0003
title: Late means delivered after the promised date; estimate broken-promise and slowness effects (JC 1)
status: Active
date: 2026-11-13
kind: analytical
judgment_call: 1
readWhen: Defining or using the treatment variables, or interpreting what the estimate measures
---

# ADR-0003: Late means delivered after the promised date; estimate broken-promise and slowness effects (JC 1)

## Options considered

What the dollar figure should price (leadership's decision: invest in faster logistics?):

- Both effects, decomposed — broken promise (arriving after the promised date, delivery time roughly fixed) and slowness (extra delivery days among on-time orders). The memo can weigh faster logistics against more conservative promises. Moderate extra modeling.
- Broken promise only — binary late flag plus days late, as the brief reads. Simplest, but cannot tell leadership whether padding promises beats logistics spend.
- Slowness only — total delivery days as the treatment. Matches "faster logistics" literally but drops the promised-date RD, the strongest design.

Late against what:

- Promised date (`order_estimated_delivery_date`) — the promise the customer saw; enables the RD.
- Typical delivery time for similar orders — measures "slower than usual", not a broken promise; kept as an alternative definition for robustness (ADR-0007).

## Decision

- Estimate both effects (project owner, discuss session 2026-11-13).
- `days_late` = calendar date of `order_delivered_customer_date` minus `order_estimated_delivery_date`, in whole days. The estimated date carries no time of day (always 00:00:00), so the running variable is discrete.
- `late` = `days_late` > 0. Delivered on the promised date (day 0) counts as on time.
- Broken-promise effect: regression discontinuity at the cutoff between day 0 and day +1, plus a days-late dose-response.
- Slowness effect: dose-response in `delivery_days` (elapsed days from purchase to customer delivery) among on-time orders.
- `promised_days` (calendar days from purchase date to promised date) is recorded so the two effects can be separated.
- Exact RD and regression specifications are fixed in the pre-registration ADR (ADR-0007), not here.

## Why

- The cheapest fix may be setting more realistic promises rather than faster logistics; only the decomposition can show that.
- Profiling (2026-11-13) shows padded promises: the median delivered order arrives 12 days early, and 6.77% arrive after the promised date. The promise is a lever the company controls.
- The promised date is the only threshold the customer actually saw, which is what makes the RD possible.

## Falsification test

- Outcomes jump at a later day (e.g., +2 or +3) rather than between day 0 and +1, or placebo cutoffs show jumps of similar size: the promised date is not where customers perceive lateness.
- Evidence that customers saw a different promise than `order_estimated_delivery_date`: the treatment is mismeasured.
- The density of `days_late` breaks at the cutoff (day 0: 1,292 orders; day +1: 825 in profiling) in a way the density test attributes to manipulation: the RD comparison is not like-for-like, and ADR-0007's pre-committed response applies.

## Affects

Docs:

- `docs/engineering/invariants.md`

Code:

- None yet (`src/late_delivery/config.py` and `build.py` implement this in T4)

## Consequences

- Good: the memo can compare two levers, faster logistics and promise-setting.
- Good: the RD isolates the broken promise with delivery time held roughly constant.
- Bad/risk: the data cannot show whether longer promises lose sales at checkout, so the promise-padding lever has an unpriced downside. The memo must state this.
- Bad/risk: the RD estimate is local to orders near the promised date; the money math needs an average effect over all late orders (median 7 days late). ADR-0007 must say how the two are reconciled.

## Read when

- building or changing `days_late`, `late`, `delivery_days`, or `promised_days`
- interpreting RD or dose-response results

## Supersedes

- None
