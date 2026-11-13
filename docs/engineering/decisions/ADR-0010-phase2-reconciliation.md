---
id: ADR-0010
title: Phase 2 reconciliation applied - headline stands, matching converges, donut RD diverges (JC 4)
status: Active
date: 2026-11-13
kind: analytical
judgment_call: 4
readWhen: Interpreting, reporting, or comparing the Phase 2 estimates, or before Phase 3 robustness work
---

# ADR-0010: Phase 2 reconciliation applied - headline stands, matching converges, donut RD diverges (JC 4)

Applies the reconciliation rule fixed before any results (ADR-0007 §4) to the Phase 2 estimates. Verdicts and flags are as computed by `ladder.py` (`outputs/ladder.json`, commit 86df6e4); every number below is copied from `outputs/*.json`.

## Options considered

- Apply the pre-registered rule as computed and explain each gap with the known differences between methods. This is the rule ADR-0007 §4 fixed.
- Treat the RD's divergence as evidence that the headline is fragile. The rule requires both corroborating methods to diverge in the same direction, and matching converges.
- Replace or average the headline with the RD. ADR-0007 §4 ruled this out before results: the headline never switches, and averaging mixes estimands.

## Decision

Project owner, 2026-11-13 (build session, T15). The first option above.

Estimates for `low_review` (share of 1-2 star reviews, 0-1 scale; 95% CIs):

| Method | Role | Estimate | 95% CI | Verdict |
|---|---|---|---|---|
| FE regression | headline (pre-registered) | 0.516 | [0.502, 0.530] | — |
| Matching (ATT) | corroborating | 0.529 | [0.513, 0.545] | converges |
| Donut RD (h = 7.5) | corroborating | 0.117 | [-0.110, 0.134] (robust) | diverges (below) |
| Naive difference | biased baseline | 0.537 | [0.525, 0.549] | — |

- The headline stands: a late delivery raises the share of 1-2 star reviews by 0.516 (95% CI 0.502 to 0.530), averaged over all late orders.
- Matching corroborates it. The donut RD diverges below it. The headline is not fragile, because only one corroborating method diverges.
- No pre-registered falsification flag fired:
  - balance: max post-match abs(SMD) 0.0511;
  - bin order: the 1-2 day bin is 0.1583 and the 3-7 day bin is 0.5370;
  - repeat window: 90 days -0.0024 and 180 days -0.0026, same sign;
  - star distribution: the `low_review` CI excludes 0.
- The memo reports the RD side by side with the headline and with the explanation below.
- No choice in ADR-0007, ADR-0008 or ADR-0009 changes. The Phase 4 money input stays the total effect per days-late bin (ADR-0007 §5).

## Why

The donut RD diverges for the reasons ADR-0007 §4 anticipated:

- **It is local.** The RD measures the jump at the promised date among orders delivered within a week of it. The headline averages over all late orders, whose median is 7 days late. The FE bins show the effect rising with lateness: 0.158 at 1-2 days, 0.537 at 3-7, 0.692 at 8-14, 0.674 at 15+. The RD's 0.117 is near the bottom of that range: below the 1-2 day bin's estimate, with its robust CI (upper bound 0.1336) ending just short of that bin's CI (lower bound 0.1344).
- **It mixes in waiting reviews and depends on extrapolation.** Reviews written before delivery are 0.7% at 1 day late, 6.0% at 2 and 70.0% at 3 (Phase 1 diagnostics). The 1-2 star share climbs from 0.195 on day +1 to 0.344 on day +2 and 0.503 on day +3. With days 0 and +1 dropped, the right side of the fit starts at day +2 and rises steeply. So the bias-corrected estimate (0.012) is far from the conventional one (0.117), and every RD specification's robust CI includes 0: h = 5.5 gives [-0.252, 0.155], h = 10.5 [-0.063, 0.103], no donut [-0.053, 0.031].
- **Bunching** just before the promised date is why days 0 and +1 are dropped. That leaves a three-day gap the fit must bridge.
- **The RD can neither confirm nor rule out a jump at the promised date itself.** It says the effect right at the cutoff is small or imprecisely estimated. That is consistent with the bins, where most of the harm comes from being several days late.

Matching converges:

- 0.529 is 0.013 above the headline and inside its CI.
- Balance is good (max abs(SMD) 0.0511), and 10 of 6,366 late orders went unmatched.
- The ordering naive (0.537) > matching (0.529) > FE (0.516) is consistent with some seller-level confounding that only the FE model absorbs (matching has no seller fixed effects), but the gaps are small next to the effect.

## Falsification test

- Phase 3 placebo cutoffs at days -7 and +7 show jumps as large as the RD's: the RD estimate reflects the shape of the curve, not the promise.
- Phase 3 sensitivity analysis shows an unobserved confounder no stronger than distance or customer state would remove the headline: the headline rests on a fragile no-unobserved-confounding assumption, and the convergence of matching (which uses the same observed controls) does not protect it.
- Any pre-registered Phase 3 check moves the estimate outside the headline CI: the headline is fragile on that dimension.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0007-pre-registration.md`
- `docs/engineering/decisions/ADR-0008-phase2-implementation-choices.md`
- `docs/engineering/decisions/ADR-0009-matching-separation.md`
- `README.md` (Phase 2 status, T16)

Code:

- `src/late_delivery/ladder.py` (computes the verdicts and flags quoted here)

## Consequences

- Good: the headline survives the pre-registered reconciliation without a switch, and matching confirms it with independent machinery.
- Good: the gap to the RD is explained by differences fixed before results, not by after-the-fact reasons.
- Bad/risk: matching shares the headline's observed controls, so its agreement does not address unobserved confounders such as carrier quality. Phase 3 sensitivity analysis must.
- Bad/risk: the data cannot pin down the effect of crossing the promised date by itself. The broken-promise versus waiting split rests on the FE bins and holding-speed models, not the RD.

## Read when

- reporting or explaining the Phase 2 estimates, including in the memo or write-up
- starting Phase 3 robustness checks or Phase 4 money translation

## Supersedes

- None
