---
id: ADR-0008
title: Phase 2 implementation choices - fills ADR-0007 gaps before estimation (JC 2, 3, 4)
status: Active
date: 2026-11-13
kind: analytical
judgment_call: 2, 3, 4
readWhen: Implementing, running, or interpreting any Phase 2 estimate, verdict, or flag
---

# ADR-0008: Phase 2 implementation choices - fills ADR-0007 gaps before estimation (JC 2, 3, 4)

Supplements ADR-0007, which stays unchanged. Committed before any Phase 2 model was estimated on a review or repeat-purchase outcome.
Evidence base: ADR-0007, the Phase 1 diagnostics, and plan-session profiling of `data/processed/orders.parquet` that read covariates only.

## Options considered

How to close the gaps ADR-0007 left open:

- New ADR committed before any estimate — git order shows the gaps were closed blind.
- Settle them in the build plan only — faster; the decision log cannot show they predate results.
- Amend ADR-0007 in place — blurs what was fixed at T7; conflicts with ADR-0001.

Zero freight (336 headline orders have freight 0, where log is undefined):

- `log1p` for price and freight — one transform, all rows kept.
- `log` plus a free-shipping indicator — exact log elsewhere; adds a control ADR-0007 did not list.
- Drop the 336 orders — complete case; against ADR-0007's keep-all-rows approach.

Matching uncertainty (1:1 nearest neighbor with replacement):

- Weighted OLS on the matched sample, SEs clustered by seller — same machinery as the headline; ignores propensity-score estimation uncertainty.
- Abadie-Imbens analytic variance — correct for nearest-neighbor matching; no seller clustering, no maintained Python implementation.
- Seller cluster bootstrap — invalid for nearest-neighbor matching (Abadie and Imbens 2008), slow.

Matching tool:

- Hand-rolled, about 50 lines, unit-tested with a planted effect — no new dependency, fully auditable.
- causalml nearest-neighbor matcher — heavy dependency tree for one function.
- R MatchIt via rpy2 — adds R to a Python-only stack (ADR-0002).

Outcomes for the donut RD and matching:

- `low_review` only — the reconciliation rule (ADR-0007 §4) compares them only to the headline.
- `low_review` and `review_score` — the second outcome has no headline CI to compare with.
- All four outcomes — repeat estimates (base rate about 1.15%) would be uninformative in a +/-7-day window.

`repeat_180d` (listed in ADR-0007 §3 and as Phase 3 check 9):

- Phase 2, same models as `repeat_90d`; check 9 points to it.
- Phase 3 only — delays ADR-0004's 90-vs-180 falsification test.

Star-distribution check (ADR-0004 falsification test):

- One FE model per star level with a preset trigger.
- Raw late vs on-time histogram — biased, cannot falsify a causal claim.
- Defer to Phase 3 — contradicts ADR-0004.

RD window for a whole-day running variable:

- Cutoff 0.5, bandwidth 7.5 — 7 days each side, symmetric, every kept day has positive kernel weight.
- Literal days -7..+7 with bandwidth 8 — 8 days left, 7 right.
- Cutoff 1 (day +1 is the first treated day) with bandwidth 7 — the triangular kernel gives day -6 zero weight.

RD CI of record:

- Robust bias-corrected (Calonico, Cattaneo and Titiunik) — the standard reviewers expect.
- Conventional — simpler; invites the question why robust was not used.

Post-match balance flag on categorical controls (74 categories, 27 states):

- Every dummy level — literal reading of "any control".
- Levels with at least 50 late orders — fewer chance trips; adds a threshold ADR-0007 never stated.
- Top five categories only — mirrors the Phase 1 table; can hide imbalance.

Falsification flags:

- Computed by code — no human discretion over whether a test failed.
- Judged by hand in ADR-0009 — reopens room for post-hoc judgment.

## Decision

All choices by the project owner, 2026-11-13 (discuss and plan sessions). The first option in each group above was chosen.

### 1. Analysis frame (judgment call 2)

- Built at analysis time by `analysis_frame()` in `fe.py` and reused by matching. `build.py` is unchanged.
- Price and freight enter as `log1p`. All rows are kept.
- Distance over 5,000 km is set to missing. Missing distance is filled with the median of non-missing headline distances after that cap, and a `distance_missing` indicator is added.
- `main_category` and `customer_state` enter as dummies. Seller and purchase week are absorbed fixed effects.

### 2. Fixed-effects grid (judgment call 3)

- pyfixest `feols` with seller and purchase-week fixed effects. Singleton groups are dropped (`fixef_rm="singleton"`) and N after the drop is reported. SEs are clustered by seller (CRV1).
- Samples: review outcomes use headline orders with a review. Repeat outcomes use headline first orders eligible for that window (`is_first_order` and `repeat_{w}d_eligible`).
- Days-late bins on integer `days_late`: 1-2, 3-7, 8-14, 15+ (reference: on time, `days_late` <= 0).
- Slowness bins on fractional `delivery_days`, on-time headline orders only: [0, 8), [8, 15), [15, 22), [22, inf) (reference: [0, 8)).
- For each outcome (`low_review`, `review_score`, `repeat_90d`, `repeat_180d`), five models:
  - (a) binary `late`;
  - (b) days-late bins;
  - (c) model (a) plus linear `delivery_days`;
  - (d) model (b) plus linear `delivery_days`;
  - (e) slowness bins.
- `repeat_180d` runs in Phase 2. Phase 3 robustness check 9 is met by reference to this output.
- Star-distribution check: outcomes 1[`review_score` = k] for k = 1..5 in model (a); the five coefficients sum to zero. Trigger: the `low_review` 95% CI includes 0 while the 5-star coefficient's 95% CI excludes 0. If it fires, the primary metric misses the effect (ADR-0004).
- 25 models in total.

### 3. Donut RD (judgment call 3)

- Outcome `low_review` only, on headline orders with a review.
- Running variable `days_late`; cutoff c = 0.5, so day +1 and later are late.
- Bandwidth h = 7.5 with a triangular kernel and a local-linear fit (p = 1): days -6..0 and +1..+7. The donut drops days 0 and +1, leaving 6 support points per side, each with positive weight. This is how ADR-0007's "fixed +/-7-day window" is read.
- Sensitivity: h = 5.5, h = 10.5, and no donut at h = 7.5.
- rdrobust settings: `vce="hc1"` with `cluster=seller_id` (CR1, matching the FE models), `masspoints="adjust"`, no covariates. Covariate continuity is Phase 3 check 5.
- The reported estimate is the conventional point estimate. The CI of record is the robust bias-corrected 95% CI. The conventional CI is kept in the JSON only.

### 4. Propensity-score matching (judgment call 3)

- Outcome `low_review` only, on headline orders with a review.
- Hand-rolled and covered by a planted-effect unit test.
- Propensity model: statsmodels Logit of `late` on the ADR-0007 control set minus seller. Week dummies are included (literal reading of ADR-0007 §3).
- Exact match on purchase week. 1:1 nearest neighbor on the logit of the propensity score, with replacement. Caliper = 0.2 x the SD of that logit score in the matching sample. Ties go to the lowest `order_id`.
- Late orders with no control inside the caliper are dropped and counted. The estimand is the ATT on the matched late orders.
- Estimate: weighted OLS of `low_review` on `late` in the matched sample (late orders weight 1; each control weighted by the number of times it was matched), SEs clustered by seller (CRV1). The output states that propensity-score estimation uncertainty is ignored.
- Balance: a weighted post-match SMD for each numeric control and for each dummy level of `main_category` and `customer_state`, with the pre-match pooled SD as denominator. Week SMD is zero by construction.

### 5. Verdicts and falsification flags (judgment call 4)

`ladder.py` computes these from the output files, with no manual input:

- ADR-0007 §4 verdict for the donut RD (main specification) and for matching: "converges" if its point estimate lies inside the headline 95% CI. The headline is flagged fragile if both diverge in the same direction. The naive baseline and the RD sensitivity runs are shown but get no verdict.
- Balance flag: any post-match |SMD| > 0.1 means the matching estimate is not interpretable (ADR-0007 falsification test).
- Bin-order flag: in `low_review` model (b), the 1-2 day bin's point estimate is larger than the 3-7 day bin's (ADR-0007 falsification test).
- Repeat-window flag: in model (a), the `repeat_90d` and `repeat_180d` point estimates have opposite signs (ADR-0004 falsification test).
- Star trigger: as defined in section 2.
- The bin-order and repeat-window flags compare point estimates, not confidence intervals.

### 6. Results record and dependencies

- After the Phase 2 results exist, ADR-0009 records the reconciliation (judgment call 4). It quotes the estimates and the code's verdicts and flags, and explains each gap with the known differences. It changes no choice in ADR-0007 or here.
- pyfixest, rdrobust and statsmodels are added in the task that first uses each (ADR-0002). statsmodels is already installed through plotnine and is declared directly.

## Why

- Every gap was closed before any outcome was estimated, so no choice here can follow the results.
- Profiling (covariates only): 336 headline orders have freight 0; price is at least 0.85, so `log1p` barely differs from `log` for price.
- `delivery_days` is fractional (elapsed time from purchase to delivery), so bin edges must say which side a value like 7.5 falls on.
- With cutoff 0.5 and bandwidth 7.5, both sides of the RD have the same number of days and none gets zero kernel weight.
- Seller-clustered weighted OLS keeps matching consistent with ADR-0007 §6. The Abadie-Imbens variance cannot cluster by seller, and the bootstrap is invalid for nearest-neighbor matching.
- The reconciliation rule compares corroborating methods to the headline only, so running them on secondary outcomes would add numbers without a rule to read them by.
- Mechanical verdicts and flags remove room for judging, after the fact, whether a pre-registered test failed.

## Falsification test

- A planted-effect unit test does not recover its known effect: the implementation does not match this specification.
- A spec echo in `outputs/` differs from this ADR (sample, bandwidth, caliper, clustering, bins): the implementation drifted, and the result is not the pre-registered one.
- rdrobust cannot run with the bandwidth or mass-point setting stated here, or the logit does not converge: the specification cannot run as written, and a superseding ADR is needed before any workaround.
- The balance flag fires only on category levels with very few late orders: the per-level rule may be too strict. The flag still stands as computed, and ADR-0009 reports it.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0007-pre-registration.md` (supplemented; text unchanged)
- `docs/engineering/decisions/ADR-0004-outcomes-and-repeat-purchase.md` (its star-distribution and 90-vs-180 tests are scheduled here)

Code:

- `src/late_delivery/config.py` (Phase 2 parameters; planned, T11)
- `src/late_delivery/fe.py` (planned, T11)
- `src/late_delivery/rd.py` (planned, T12)
- `src/late_delivery/matching.py` (planned, T13)
- `src/late_delivery/ladder.py` (planned, T14)

## Consequences

- Good: every Phase 2 fork is closed before estimation; the spec echo in each output makes drift visible.
- Good: convergence verdicts and falsification flags are computed, not judged.
- Bad/risk: matching SEs ignore propensity-score estimation uncertainty.
- Bad/risk: the per-level balance rule may flag a rare category and leave the matching estimate not interpretable.
- Bad/risk: the RD has 6 support points per side and seller clusters, so its CI will be wide.
- Bad/risk: `log1p` departs slightly from ADR-0007's "log price, log freight" wording.

## Read when

- implementing or running `fe.py`, `rd.py`, `matching.py`, or `ladder.py`
- interpreting any Phase 2 estimate, convergence verdict, or falsification flag

## Supersedes

- None (supplements ADR-0007)
