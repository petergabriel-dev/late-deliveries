---
id: ADR-0012
title: Phase 3 robustness reading - headline holds except on disruption periods; RD continuity fails (JC 2, 4)
status: Active
date: 2026-11-16
kind: analytical
judgment_call: 2, 4
readWhen: Reporting or interpreting the Phase 3 robustness checks, or planning the Phase 4 money translation
---

# ADR-0012: Phase 3 robustness reading - headline holds except on disruption periods; RD continuity fails (JC 2, 4)

Applies the ADR-0011 rules to the Phase 3 results. Flags are as computed by `robustness.py` (`outputs/robustness.json`, commit f568bad); every number below is copied from `outputs/robustness.json` unless marked exploratory.

## Options considered

How to read the flags:

- Apply the ADR-0011 rules as computed and explain each fired flag with evidence — the rule fixed before results.
- Dismiss a fired flag as noise — not open here: check 10's own 95% CI excludes the headline estimate, and ADR-0011 says a fired flag stands.
- Switch or average the headline — ruled out before results (ADR-0007 §4).

Check 10 (surge and strike excluded) fired:

- Fragile on disruption periods, partly explained by an exploratory lateness-mix calculation, labeled exploratory.
- Fragile, movement only — keeps this ADR to pre-registered numbers; the memo could not say why the estimate moved.

What check 10 means for Phase 4:

- Keep the pre-registered money input and add one sensitivity scenario with disruption periods excluded.
- Memo note only — the size of the fragility in money stays unknown.
- Use the disruption-excluded effect as the money input — would supersede ADR-0007 §5 after results were seen.

Check 5 (covariate continuity) fired:

- The RD is weakened further; the headline is unaffected.
- Drop the RD from stakeholder material — contradicts ADR-0007 §4, which reports every method side by side.

## Decision

Project owner, 2026-11-16 (build session, T23). The first option in each group above.

Headline: 0.516256, 95% CI [0.502433, 0.530079], 94,302 orders with a review.

| Check | Class | Estimate | 95% CI | Orders with a review (vs headline) | Flag |
|---|---|---|---|---|---|
| 1 Late = 2+ days late | estimand | 0.578246 | [0.563474, 0.593017] | 94,302 (+0) | not fired (>= headline) |
| 2 Slower than the route median | estimand | 0.083936 | [0.078700, 0.089172] | 94,302 (+0) | not fired (> 0) |
| 3 Black Friday week excluded | sample | 0.511458 | [0.496660, 0.526256] | 91,013 (-3,289) | not fired |
| 4 Placebo cutoffs | diagnostic | -6.5: 0.002534; +7.5: -0.104597 | robust: [-0.050324, 0.039747]; [-0.200385, 0.136603] | | not fired (both below 0.117059 in size) |
| 5 Covariate continuity | diagnostic | `promised_days`: 3.436632 days | robust: [2.366293, 6.883444] | | **fired** |
| 6 Unobserved confounding | diagnostic | 1x customer state: 0.510274 | [0.496338, 0.524209] | | not fired |
| 7 Multi-seller orders included | sample | 0.514992 | [0.500985, 0.528998] | 95,560 (+1,258) | not fired |
| 8 Post-delivery reviews (biased) | estimand | 0.156664 | [0.135765, 0.177564] | 89,347 (-4,955) | not fired (between 0 and headline) |
| 9 Repeat purchase at 180 days | reference | -0.002575 | [-0.007291, 0.002141] | | Phase 2 flag (not fired) |
| 10 Surge and strike excluded | sample | 0.491795 | [0.474648, 0.508943] | 73,022 (-21,280) | **fired** |
| 11 Window from 2017-02-01 | sample | 0.515985 | [0.502167, 0.529803] | 93,565 (-737) | not fired |
| 12 Single-review orders | sample | 0.515914 | [0.502075, 0.529752] | 93,792 (-510) | not fired |

### Check 10: the headline is fragile on disruption periods

- The flag stands. Without purchases in February-March 2018 and orders exposed to the May 2018 truckers' strike, the estimate is 0.491795, 0.024461 below the headline and below its CI. The check's own CI excludes the headline estimate.
- The memo states it: the effect is about 0.49 without the disruption periods and 0.52 with them.
- The headline does not change (ADR-0007 §4).
- Partial explanation (exploratory, ADR-0007 §8): the check keeps 3,672 of the 6,366 late orders with a review; the surge removes 2,204 of them and the strike 490. The late orders that remain are less late (median 6 days, against 7):

| Late orders with a review | 1-2 days | 3-7 | 8-14 | 15+ | Phase 2 bins weighted by this mix |
|---|---|---|---|---|---|
| Headline (6,366) | 0.212 | 0.351 | 0.227 | 0.209 | 0.5206 |
| Check 10 (3,672) | 0.237 | 0.358 | 0.207 | 0.198 | 0.5066 |

- Bin effects from `outputs/fe.json` (`low_review/b`): 0.158253, 0.536973, 0.692143, 0.674345. The lateness mix predicts a drop of 0.0140, about 57% of the observed 0.0245; the other 0.0105 is unexplained.
- These exploratory numbers were computed ad hoc on 2026-11-16, not by `make`. Before the memo or write-up uses them, they must come from code output (invariant 6).

### Check 5: the RD's like-for-like assumption fails

- Orders just past the promised date had promise windows 3.44 days longer than orders just before it (robust CI [2.37, 6.88]). Price, freight, item count and distance show no jump.
- Together with the bunching just before the promised date (ADR-0007), the RD cannot measure the jump at the promised date. It stays in the ladder, labeled that way.
- The headline is unaffected: it controls for `promised_days` and never rested on the RD (ADR-0010).
- The +7.5 placebo (-0.104597) is not fired but is close to the threshold (0.117059); with check 5, it adds to the reasons not to read the RD as a measure of the promise.

### What the headline rests on (brief Phase 3 exit)

- **No strong unobserved confounder.** A confounder would have to explain 33.9% of the residual variance of both lateness and the outcome to remove the estimate (RV(q = 1) 0.339192; at alpha 0.05, 0.334978). Customer state, the strongest observed benchmark, explains 1.7% of lateness and 0.13% of the outcome (partial R² 0.017049 and 0.001278); even a confounder 3x as strong leaves 0.497972 [0.483803, 0.512141].
- **Including the disruption periods.** This is the one dimension where the estimate leaves its CI (check 10).
- **Survey timing.** Among reviews written after delivery the effect is 0.156664 (biased by design, ADR-0004), against 0.516256 overall: most of the measured effect comes with reviews written while still waiting, as the Phase 2 bins showed (ADR-0010).
- **Not on sample details.** Black Friday week, multi-seller orders, the window start and repeat reviews move the estimate by at most 0.0048, inside the CI.
- **Not on how lateness is cut.** Counting only 2+ days late gives 0.578246, inside the 0.569-0.592 range ADR-0011 projected from the Phase 2 bins. Being slower than the route median, a different treatment, has a positive but much smaller effect (0.083936).

### Phase 4

- The money input stays as pre-registered: the Phase 2 bin effects weighted by the observed mix of late orders (ADR-0007 §5).
- The Phase 4 plan adds one sensitivity scenario showing the dollar range with disruption periods excluded. Its method is set in the Phase 4 plan, before it is computed.

## Why

- ADR-0011 fixed every rule before the results; reading the flags as computed keeps that order.
- Check 10's movement is larger than its own uncertainty, so it is reported as fragility, not noise.
- The lateness-mix arithmetic uses only pre-registered Phase 2 estimates and the treatment distribution; it explains part of the movement and is labeled exploratory because ADR-0007 did not list it.
- A money sensitivity shows a non-technical reader how much the fragility matters, without changing the pre-registered input.
- The continuity failure is about the RD's comparison at the cutoff; the headline compares all late orders with all on-time orders, holding `promised_days` fixed.

## Falsification test

- When the lateness-mix calculation is reproduced in code, its numbers differ from the ones above: the partial explanation is withdrawn until corrected.
- The Phase 4 disruption-excluded scenario changes the recommendation, not only the dollar range: the fragility is material, and the memo leads with it.
- A correction to `robustness.py` changes any flag or estimate quoted here: this reading is void, and a superseding ADR is needed.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0007-pre-registration.md`
- `docs/engineering/decisions/ADR-0010-phase2-reconciliation.md`
- `docs/engineering/decisions/ADR-0011-phase3-implementation-choices.md`
- `README.md` (Phase 3 status and limitations; planned, T24)

Code:

- `src/late_delivery/robustness.py` (computes the estimates and flags quoted here)

## Consequences

- Good: under rules fixed in advance, 10 of the 12 checks fired no flag, and of the two that fired only check 10 concerns the headline; the sensitivity analysis puts the unobserved-confounding risk in numbers.
- Good: the one fragile dimension is named, sized, and partly explained, and Phase 4 will show its size in money.
- Bad/risk: about 40% of the disruption shift is unexplained.
- Bad/risk: the lateness-mix numbers are not yet produced by `make`.
- Bad/risk: the RD can no longer corroborate or contradict the headline at the promised date; the method ladder rests on the FE regression and matching.

## Read when

- reporting or explaining the Phase 3 results, including in the memo or write-up
- planning or running the Phase 4 money translation

## Supersedes

- None
