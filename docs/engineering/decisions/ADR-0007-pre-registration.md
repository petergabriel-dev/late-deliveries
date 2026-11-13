---
id: ADR-0007
title: Pre-registration - FE regression headline; donut RD and matching corroborate (JC 2, 3, 4)
status: Active
date: 2026-11-13
kind: analytical
judgment_call: 2, 3, 4
readWhen: Before running, changing, or interpreting any Phase 2-4 estimate
---

# ADR-0007: Pre-registration - FE regression headline; donut RD and matching corroborate (JC 2, 3, 4)

Fixed before any review or repeat-purchase outcome was compared between late and on-time orders.
Evidence base: the Phase 1 design diagnostics only (`outputs/diagnostics.md`, commit 3038078).

## Options considered

Confounders (judgment call 2):

- Full observed control set — covers every imbalance the diagnostics found.
- Minimal: seller and time fixed effects only — fewer choices; leaves distance and region imbalances unadjusted.
- Full set plus customer-state x seller-state route fixed effects — finer logistics proxy; costs many parameters.

Distance problems (470 headline orders missing, 3 over 5,000 km):

- Missing indicator, outliers blanked — keeps all rows.
- Drop affected orders — complete case, 0.5% lost.
- Use as built — keeps known-wrong distances.

Time controls:

- Purchase-week fixed effects — absorbs Black Friday week and the Feb-Mar 2018 surge.
- Purchase-month fixed effects — fewer parameters; within-month spikes stay confounded.
- Linear trend plus event dummies — assumes the rest of the variation is smooth.

Headline method (judgment call 3):

- Fixed-effects regression headline; donut RD and matching corroborate.
- Donut RD headline — design-based but local, exposed to bunching, right side mixes "still waiting" reviews.
- RD and regression co-headline — two numbers to reconcile, and a post-results choice stays possible.

Dose-response shape:

- Bins aligned to the survey-timing shift at day 3.
- Linear in days — hides the shift.
- Restricted cubic splines — flexible but hard to explain and to price.

RD specification:

- Donut local-linear, fixed +/-7 days.
- Data-driven bandwidth, no donut — ignores the bunching.
- Drop the RD — loses the only design-based method.

Matching:

- 1:1 nearest neighbor within purchase week, caliper.
- 1:5 nearest neighbor — more bias from worse matches.
- Inverse-probability weighting — unstable near propensity 0 or 1.

Outcome model:

- Linear probability model with fixed effects — percentage-point coefficients.
- Logit with fixed effects — needs marginal effects; sellers without outcome variation drop out.
- Poisson (PPML) — relative effects need converting back for money.

Reconciliation (judgment call 4):

- Fixed headline; explain gaps with known differences.
- Precision-weighted average — mixes estimands.
- Most conservative estimate wins — choice depends on results.

Money input:

- Total late effect per days-late bin, weighted by the observed mix.
- Broken promise holding speed — understates what late deliveries cost as they happen.
- Local RD estimate — local to the cutoff; median late order is 7 days late.

Inference:

- Seller-clustered, alpha 0.05.
- Two-way clustered by seller and week — only ~87 week clusters.
- HC1 robust, no clustering — likely overstates precision.

Robustness:

- Full list below.
- The brief's minimum only — leaves Phase 1 concerns untested.
- Full list minus disruption periods — avoids dropping the months holding most late orders.

## Decision

All choices by the project owner, 2026-11-13. The first option in each group above was chosen.

### 1. Controls (judgment call 2)

- Seller fixed effects, purchase-week fixed effects (~87 weeks), main category, log price, log freight, `n_items`, `distance_km`, `promised_days`, customer state.
- Excluded as consequences of lateness (bad controls): review timing (`review_created_before_delivery`) and the carrier handoff date.
- Not observed, left to Phase 3 sensitivity analysis: carrier, product defects, customer expectations.
- Distance at analysis time: values over 5,000 km are treated as missing; missing values are filled with the median and flagged by a `distance_missing` indicator. All rows are kept; the build is unchanged.

### 2. Construction rules (confirmed from the T4 build)

- Repeat purchase counts any new order, whatever its status.
- `main_category` = category of the highest-price item; ties go to the lowest `order_item_id`; untranslated categories keep their Portuguese name; missing becomes `unknown`.
- `bf_2017` flags purchases on 2017-11-24 as a covariate; the robustness window below is wider.

### 3. Models (judgment call 3)

- Outcome model: linear probability model (OLS) with seller and purchase-week fixed effects (pyfixest), on the headline sample (ADR-0005).
- **Primary estimate:** the coefficient on binary `late` in that model with the controls above, outcome `low_review`. This is the average total effect of a late delivery.
- Total-effect dose-response: the same model with days-late bins 1-2, 3-7, 8-14, 15+ (reference: on time). The 1-2 bin is mostly the arrived-late effect (6% or fewer of its reviews are written before delivery); later bins add the waiting experience.
- Broken promise holding speed: the total-effect models plus a linear `delivery_days` control. Two orders with the same speed and different promises differ in lateness, which identifies the promise effect.
- Slowness: on-time headline orders only; delivery-days bins 0-7 (reference), 8-14, 15-21, 22+; same controls including `promised_days`.
- Secondary outcomes with the same models: mean `review_score`; `repeat_90d` and `repeat_180d` on eligible first orders. Repeat estimates are read against the Phase 1 minimum detectable effects (90 days: 0.43 points; 180 days: 0.75 points); a confidence interval that includes zero becomes an upper bound (ADR-0004).
- Corroborating methods:
  - Donut RD: running variable `days_late`, cutoff between day 0 and day +1, local-linear, triangular kernel, fixed +/-7-day window, days 0 and +1 dropped, rdrobust with mass-point adjustment, SEs clustered by seller. Sensitivity: +/-5 and +/-10 days, and no donut. Caveat: its right side mixes "still waiting" reviews from day 3 on.
  - Propensity-score matching: effect on late orders (ATT); logit propensity on the control set without seller; exact match on purchase week; 1:1 nearest neighbor with replacement; caliper 0.2 SD of the logit score; post-match balance (SMD) reported.
  - Naive late vs on-time difference (Phase 1 T8), labeled biased.

### 4. Reconciliation rule (judgment call 4)

- The headline never switches after results are seen.
- A corroborating estimate "converges" if it falls inside the headline's 95% CI.
- If one does not, all estimates are reported side by side and the gap is explained with the known differences: the RD is local and mixes waiting reviews; matching has no seller fixed effects.
- If the RD and matching both diverge in the same direction, the memo flags the headline as fragile.

### 5. Money input (feeds ADR-0006)

- Phase 4 uses the total late effect per days-late bin, weighted by the observed mix of late orders across bins.
- The broken-promise-holding-speed and slowness estimates split the recommendation (fix promises vs speed up logistics); they do not enter the dollar total.

### 6. Inference

- Standard errors clustered by seller; two-sided tests at alpha 0.05; 95% confidence intervals.
- One pre-registered primary test: the primary estimate above.
- Bins, secondary outcomes, and corroborating methods are reported with confidence intervals, labeled secondary, without multiplicity correction.

### 7. Phase 3 robustness checks (all pre-registered)

1. Late defined as 2 or more days late.
2. Late defined as slower than the median `delivery_days` for the same seller-state to customer-state route.
3. Exclude purchases 2017-11-24 through 2017-11-30 (Black Friday week).
4. Placebo cutoffs at days -7 and +7.
5. Covariate continuity at the cutoff.
6. Sensitivity to unobserved confounding (sensemakr), benchmarked against distance and customer state.
7. Include multi-seller orders.
8. Post-delivery-review subset (mechanism check, labeled biased per ADR-0004).
9. Repeat purchase at 180 days.
10. Exclude the Feb-Mar 2018 lateness surge, and the May 2018 truckers' strike (exact dates verified from a cited source before use).
11. Window starting 2017-02-01.
12. Drop orders that had more than one review.

### 8. Deviations

- Any change to a choice above after results are seen needs a superseding ADR that states the reason.
- Analyses not listed here are labeled exploratory wherever they are reported.

## Why

- Bunching at the promised date: orders fall 36% from day 0 to day +1, against about 10% per day over the five days before, and density tests are unstable across specifications. The RD's no-sorting assumption is in doubt, so it corroborates rather than heads.
- Survey timing: 0.7% (day 1) and 6.0% (day 2) of late-order reviews are written before delivery, against 70% on day 3 and 91-100% after. Wider RD windows mix in the waiting experience; the dose-response bins follow this shift.
- Imbalance: late orders differ on customer state (SMD -0.32), distance (+0.28), Black Friday (+0.14), seller state (+0.14), freight (+0.13), and promised days (-0.13), so all of these are controlled.
- Lateness clusters in time (about 3% of orders late in a typical month vs 12.5%, 14.2%, and 19.2% in Nov 2017, Feb 2018, and Mar 2018), so time is absorbed by week.
- Seller fixed effects are well supported: the 1,218 sellers with both late and on-time orders hold 99.1% of late orders.
- The money translation needs an effect that covers all late orders, not only those near the cutoff.

## Falsification test

- Sensitivity analysis shows an unobserved confounder no stronger than distance or customer state would remove the primary estimate: the headline rests on a fragile no-unobserved-confounding assumption, and the memo must say so.
- The donut RD and matching both fall outside the headline CI in the same direction: the headline is fragile (rule 4).
- Placebo cutoffs at -7 or +7 show jumps comparable to the cutoff: the RD is picking up noise or shape, not the promise.
- Post-match SMD stays above 0.1 on any control: matching failed to balance, and its estimate is not interpretable.
- The 1-2 day bin shows a larger effect than the 3-7 day bin: the "waiting adds harm" reading of the bins is wrong.
- Any pre-registered robustness check moves the estimate outside the headline CI: the result is fragile on that dimension, and the memo reports it.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0003-estimand-and-late-definition.md`
- `docs/engineering/decisions/ADR-0004-outcomes-and-repeat-purchase.md`
- `docs/engineering/decisions/ADR-0005-headline-sample.md`
- `docs/engineering/decisions/ADR-0006-money-framing.md`
- `docs/engineering/invariants.md`

Code:

- `src/late_delivery/build.py` (construction rules already implemented)
- `src/late_delivery/config.py`

## Consequences

- Good: every analytical fork for Phases 2-4 is closed before outcomes are seen; git history proves the order.
- Good: each choice is tied to a Phase 1 diagnostic, not to taste.
- Bad/risk: the headline rests on selection on observables; carrier identity is unobserved.
- Bad/risk: the RD is weakened by bunching and by survey timing; it can corroborate but not settle the question.
- Bad/risk: repeat purchase will likely be an upper bound, pushing the money range toward assumptions.
- Bad/risk: Phase 2 needs new dependencies (pyfixest, rdrobust, a matching tool, PySensemakr), added in the Phase 2 plan.

## Read when

- running, changing, or interpreting any Phase 2-4 estimate
- tempted to add, drop, or swap an analysis after seeing results

## Supersedes

- None
