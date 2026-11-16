---
id: ADR-0011
title: Phase 3 implementation choices - fills ADR-0007 §7 gaps before any robustness estimate (JC 1, 2, 4)
status: Active
date: 2026-11-16
kind: analytical
judgment_call: 1, 2, 4
readWhen: Implementing, running, or interpreting any Phase 3 robustness check, flag, or sensitivity result
---

# ADR-0011: Phase 3 implementation choices - fills ADR-0007 §7 gaps before any robustness estimate (JC 1, 2, 4)

Supplements ADR-0007, which stays unchanged. Committed before any Phase 3 check was estimated.
Evidence base: ADR-0007, ADR-0008, ADR-0010, the Phase 1 and Phase 2 outputs (`outputs/diagnostics.md`, `outputs/fe.json`, `outputs/rd.json`), and plan-session profiling of `data/processed/orders.parquet` that split no outcome by treatment.

## Options considered

How to close the gaps ADR-0007 §7 left open:

- New ADR committed before any Phase 3 estimate — git order shows the gaps were closed blind; same pattern as ADR-0008.
- Settle them in the build plan only — faster; the decision log cannot show they predate results.

Comparison rule (ADR-0007 falsification test: "any pre-registered robustness check moves the estimate outside the headline CI"):

- Classify the checks first. Checks that change only the sample keep the literal CI rule. Checks that change the estimand get a direction stated in advance. Diagnostic checks use their own ADR-0007/ADR-0010 tests. Check 9 refers to Phase 2 — keeps the pre-registered rule where it applies and still risks failing elsewhere.
- Literal CI rule for every check — most faithful to the text, but it fires by construction on checks that change the estimand (check 1 projects above the CI from Phase 2 bins), labeling the headline "fragile" for the wrong reason.
- Estimand-matched benchmarks (e.g. a headline-model effect for orders 2+ days late) — most rigorous; needs new models whose own choices would be open.

Models per check:

- Headline model (a) only — one number per check, which is what the brief's Phase 3 exit asks for.
- Model (a) plus days-late bins (b) — would show whether the Phase 4 money input is robust too; doubles the models.
- All four outcomes — repeat estimates are already upper bounds (CIs include 0); adds noise.

Check 1 (late = 2+ days), orders exactly 1 day late:

- Counted as on time — literal reading; all rows kept.
- Dropped — cleaner contrast; adds a donut ADR-0007 never stated.

Check 2 (late = slower than the route median):

- Median over all headline orders, no minimum route size — literal.
- Minimum route size — less noisy thresholds; adds a cutoff ADR-0007 never stated.

Check 4 (placebo cutoffs):

- Main donut RD specification shifted; flag if a placebo jump is at least as large as the main RD's conventional estimate — like-for-like; matches ADR-0010's "as large as".
- Shifted, no donut — more data; not like-for-like.
- Flag if a placebo's robust CI excludes 0 — asks a different question from ADR-0010's.

Check 5 (covariate continuity):

- The five numeric controls; flag if a robust CI excludes 0; no multiplicity correction.
- Add indicators for the largest customer states — more coverage; needs a rule for which states.
- Bonferroni-corrected — fewer chance flags; a correction ADR-0007 §6 uses nowhere else.

Check 6 (sensitivity to unobserved confounding), implementation:

- Hand-rolled Cinelli and Hazlett (2020) formulas on pyfixest fits — fixed effects handled natively; no new dependency.
- PySensemakr — needs a statsmodels OLS fit, so about 3,000 seller and 87 week fixed effects would have to be demeaned by hand and degrees of freedom corrected; new dependency plus glue code.

Check 6, what "remove the headline" means:

- The bias-adjusted 95% CI includes 0 — stricter; accounts for uncertainty.
- The bias-adjusted estimate is 0 or below — looser; ignores uncertainty.

Check 6, standard error of the adjusted CI:

- Seller-clustered SE scaled by the sensemakr SE factor — consistent with the headline's inference; wider CI.
- Classical SE as in the paper — understates uncertainty relative to the headline CI.

Check 7 (multi-seller orders):

- One pseudo-seller fixed-effect level and cluster — no build change; reuses the missing-distance rule.
- Seller of the highest-price item — truer seller effect and distance; needs a build change and new distances.
- Drop the seller fixed effect for this check — changes the model as well as the sample.

Check 10 (disruption periods):

- Pre-treatment windows in one combined run: purchase dates for the surge; purchase-to-promised overlap for the strike.
- Purchase dates only — misses orders already in transit when the strike began.
- Pre-treatment windows in three runs (surge, strike, combined) — attributes any movement; two more models and two more chances to fire.

Check 12 (per-order review count):

- New build column `n_reviews` — raw CSVs stay read only in `build.py`.
- Re-read the reviews CSV in the robustness module — no build change; a second raw-data reader.

## Decision

All choices by the project owner, 2026-11-16 (discuss and plan sessions). The first option in each group above was chosen, and the strike window 2018-05-21 through 2018-06-02 was chosen over 2018-05-21 through 2018-05-31.

### 1. Comparison rule (judgment call 4)

The headline is read from `outputs/fe.json` at run time: 0.516256, 95% CI [0.502433, 0.530079].

| Check | Class | Fires when |
|---|---|---|
| 3 Black Friday week, 7 multi-seller, 10 surge and strike, 11 window from 2017-02-01, 12 single review | sample | point estimate < 0.502433 or > 0.530079: the headline is fragile on that dimension (ADR-0007, as written) |
| 1 late = 2+ days | estimand | point estimate < headline point estimate |
| 2 slower than route median | estimand | point estimate <= 0 |
| 8 post-delivery reviews (biased) | estimand | point estimate <= 0 or >= headline point estimate |
| 4 placebo cutoffs | diagnostic | abs(conventional placebo estimate) >= abs(main RD conventional estimate, 0.117059) on either side |
| 5 covariate continuity | diagnostic | for any covariate, the robust 95% CI excludes 0 |
| 6 unobserved confounding | diagnostic | for a confounder 1x as strong as either benchmark group, the bias-adjusted 95% CI includes 0 |
| 9 repeat at 180 days | reference | no new model: Phase 2 `repeat_180d/a` is -0.002575 [-0.007291, 0.002141]; the Phase 2 repeat-window flag stands (not fired) |

- Point estimates are compared, as in ADR-0008 §5, except checks 5 and 6, whose rules are about uncertainty.
- Flags are computed in code. ADR-0012 records how they were read and changes no rule here.

### 2. Models (judgment calls 1 and 4)

- Every FE check (1, 2, 3, 7, 8, 10, 11, 12) runs model (a) only: `low_review` on a binary treatment, the ADR-0007 §1 controls, seller and purchase-week fixed effects, singletons dropped, SEs clustered by seller (CRV1), on orders with a review in that check's sample.
- Check 1: late = `days_late` >= 2; orders 1 day late count as on time.
- Each check reports N, the late count, and the rows dropped relative to the 94,302 headline orders with a review.

### 3. Check definitions (judgment calls 1 and 2)

- **2:** route = `seller_state` -> `customer_state`. The median `delivery_days` per route is taken over all headline orders, with or without a review. Late = `delivery_days` strictly above the route median. No minimum route size.
- **3:** drop purchases dated 2017-11-24 through 2017-11-30 (3,317 headline orders).
- **7:** add the 1,272 multi-seller orders that pass every other ADR-0005 rule (1,258 have a review). They share one seller fixed-effect level and one cluster, labeled `multi_seller`. Their distance is missing and follows the ADR-0008 §1 rule (median fill plus `distance_missing`). Other controls as built.
- **8:** keep orders whose review was created on or after the delivery date (`review_created_before_delivery` is false: 89,347 of 94,302). Labeled biased: it conditions on a consequence of lateness (ADR-0004).
- **10:** one run that drops (a) purchases dated 2018-02-01 through 2018-03-31 (13,418 headline orders) and (b) orders whose purchase-to-promised window overlaps the truckers' strike: purchase date <= 2018-06-02 and promised date >= 2018-05-21. The promised date is set at purchase, so the rule uses pre-treatment dates only.
- **11:** keep purchases dated 2017-02-01 or later (drops 746 headline orders).
- **12:** keep orders with `n_reviews` = 1 (drops 510 of the 94,302 orders with a review; in the raw data 547 orders have more than one review). `n_reviews` is the number of raw review rows per `order_id`.

Strike dates (sources opened 2026-11-16):

- Start, 2018-05-21: Wikipedia, "2018 Brazil truck drivers' strike" (https://en.wikipedia.org/wiki/2018_Brazil_truck_drivers%27_strike): "the strike began on 21 May"; infobox date "21 May 2018 – 1 June". MercoPress, 30 May 2018 (https://en.mercopress.com/2018/05/30/truckers-union-calls-an-end-to-the-crippling-strike-but-some-still-resist): "The strike began May 21 over rising diesel prices".
- End, 2018-06-02: WSWS, Miguel Andrade, 4 June 2018 (https://www.wsws.org/en/articles/2018/06/04/braz-j04.html): "Brazil's 11-day truckers' strike was declared over Saturday". The Saturday before Monday 4 June 2018 is 2 June 2018. Wikipedia: "Most demonstrations ended by June 1". The window covers both end dates.

### 4. Placebo cutoffs and covariate continuity

- **Placebo (check 4):** the main donut RD (ADR-0008 §3: triangular kernel, p = 1, h = 7.5, rdrobust with mass-point adjustment, CR1 by seller) with the cutoff moved to -6.5 (between days -7 and -6) and to 7.5 (between days 7 and 8). The donut drops the two days straddling each placebo cutoff: (-7, -6) and (7, 8). Windows: days -13..0 and days 1..14, each minus its donut, so 6 support days per side and each window on one side of the real cutoff. Reported: conventional estimate and robust CI.
- **Continuity (check 5):** the main RD specification (cutoff 0.5, h = 7.5, donut 0 and +1) on the main RD sample, with each of `log_price`, `log_freight`, `n_items`, `distance_km` (after the ADR-0008 §1 cap and fill) and `promised_days` as the outcome. No multiplicity correction (ADR-0007 §6). A fired flag weakens the RD only; the headline does not rest on it.

### 5. Sensitivity to unobserved confounding (judgment call 2)

- Cinelli and Hazlett (2020) formulas, hand-rolled, no new dependency. A unit test reproduces the sensemakr Darfur reference values.
- Model: the headline (model (a), `low_review`).
- Partial R² values come from plain OLS (iid) fits with the same formula, fixed effects and singleton drop, using the residual sums of squares of nested fits: R²(Y~D|X) for the treatment; for each benchmark group, R²(D~Xj|X-j) from the treatment regression (`late` on the controls and fixed effects) and R²(Y~Xj|D,X-j) from the outcome regression.
- Benchmark groups: distance = {`distance_km`, `distance_missing`}; customer state = all `customer_state` dummies.
- Bounds at kd = ky = k for k = 1, 2, 3, for each group (the sensemakr `ovb_partial_r2_bound` logic).
- Bias = iid SE x sqrt(R²(Y~Z|D,X) x R²(D~Z|X) / (1 - R²(D~Z|X))) x sqrt(df). The adjusted estimate moves the headline toward 0 by the bias.
- Adjusted SE = the headline's seller-clustered SE x sqrt((1 - R²(Y~Z|D,X)) / (1 - R²(D~Z|X)) x df / (df - 1)). Adjusted 95% CI = adjusted estimate ± the headline CI's critical value (pyfixest: t with clusters - 1 df) x adjusted SE.
- Reported: R²(Y~D|X), RV(q = 1), RV(q = 1, alpha = 0.05) from the iid t and df, and the bounds table. The flag uses k = 1.
- The iid and CRV1 fits must keep the same rows, and R²(D~Z|X) must be below 1; otherwise the code raises.

### 6. Code placement and outputs

- Phase 3 variants (the check 1 and 2 relabels, the sample masks, the multi-seller frame) live only in `robustness.py`.
- `fe.analysis_frame()` gains an `include_multi_seller` option and pass-through columns only. `rd.rd_sample()` and `rd.estimate()` gain cutoff, donut-day and outcome parameters whose defaults reproduce Phase 2 byte for byte.
- `build.py` adds `n_reviews`; no ADR-0003..0005 definition changes.
- Parameters live in `config.py`, each with a comment naming this ADR.
- Outputs: `outputs/robustness.{md,json}` and `fig_robustness.png`, from `make robustness` (after `fe` and `rd`), which joins `make all`.

### 7. What was known when this was written

- Every Phase 2 estimate was known (ADR-0010). No Phase 3 check had been run.
- Check 1's direction can be predicted from Phase 2. The 1-2 day bin is 0.158253, against 0.536973 to 0.692143 for later bins (`outputs/fe.json`), and 817 of the 6,366 late orders with a review are 1 day late (`outputs/diagnostics.md`). If the day-1 effect lies between 0 and 0.158253, moving those orders to the control group gives roughly (0.516256 x 6,366 - e x 817) / 5,549 = 0.569 to 0.592, above the headline CI. This is arithmetic, not an estimate: the FE coefficient is a variance-weighted average, not a simple mean. It is why check 1 gets a direction rule and not the CI rule.

## Why

- The literal CI rule cannot be failed or passed meaningfully by a check that changes what is estimated; it fires by construction on check 1. The direction rules can still fail: check 1 if removing the mildest late orders lowers the effect, check 2 if being slower than the route norm has no positive effect, check 8 if the arrived-late effect is zero, negative, or larger than the total effect.
- Checks 3, 7, 10, 11 and 12 keep the treatment, outcome and model and change only which orders enter, so the headline CI is the right yardstick for them.
- Model (a) alone answers the brief's exit question: how much the estimate moves under each check.
- The placebo specification matches the main RD, so a jump of the same size means the RD picks up the curve's shape, which is ADR-0010's falsification test.
- pyfixest absorbs the fixed effects that a dense statsmodels fit cannot hold. Partial R² is a property of the data, which plain OLS fits measure exactly; scaling the clustered SE keeps the adjusted CI on the same footing as the headline CI and makes the flag harder to pass.
- Delivery dates depend on lateness, so an exclusion based on them would select on the treatment. The promised date is fixed at purchase.
- Raw CSVs are read only in `build.py`, which also runs the checksum check first (invariant 2).

## Falsification test

- A planted-effect, mask-edge or flag-branch unit test fails: the implementation does not match this specification.
- The sensitivity code does not reproduce the Darfur reference values within 1e-5: the formulas are wrong, and no sensitivity result is reported until they are fixed.
- The specification echo in `outputs/robustness.json` differs from this ADR (sample, cutoff, donut, benchmarks, k): the implementation drifted, and the result is not the pre-registered one.
- The iid and CRV1 fits keep different rows, or rdrobust cannot run a placebo window as written: a superseding ADR is needed before any workaround.
- A sample check fires while its own 95% CI contains the headline estimate: the CI rule may be reacting to noise. The flag stands as computed, and ADR-0012 reports it with that context.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0007-pre-registration.md` (supplemented; text unchanged)
- `docs/engineering/decisions/ADR-0008-phase2-implementation-choices.md` (§3 RD specification reused for the placebo and continuity checks)
- `docs/engineering/decisions/ADR-0010-phase2-reconciliation.md` (its falsification tests are applied here)

Code:

- `src/late_delivery/build.py` (`n_reviews`; planned, T18)
- `src/late_delivery/config.py` (Phase 3 parameters; planned, T19)
- `src/late_delivery/fe.py` (`analysis_frame` options; planned, T19)
- `src/late_delivery/rd.py` (cutoff, donut and outcome parameters; planned, T19)
- `src/late_delivery/robustness.py` (planned, T20-T22)
- `Makefile` (`robustness` target; planned, T22)

## Consequences

- Good: every Phase 3 fork is closed before any robustness estimate; git order shows it.
- Good: flags are computed, not judged; no new dependency.
- Bad/risk: the CI rule is tight (±0.014). Check 10 removes the months with the most late orders (14.2% and 19.2% late in February and March 2018, ADR-0007), so its estimate is noisier and may fall outside the CI by noise alone. The rule stands; ADR-0012 reads each check's own CI.
- Bad/risk: the left placebo cutoff sits where the order count falls from 4,796 (day -7) to 3,606 (day -6) (`outputs/diagnostics.md`); a jump there may reflect which orders fall on each side, not noise.
- Bad/risk: the 1,272 multi-seller orders share one seller fixed-effect level and one cluster although their sellers differ.
- Bad/risk: the estimand rules for checks 1, 2 and 8 compare point estimates only.
- Bad/risk: the strike exclusion keeps orders purchased after 2018-06-02, while supply was still returning to normal (Wikipedia: cargo deliveries took "up to 12 days" to normalize).
- Bad/risk: the adjusted CI combines plain-OLS partial R² with a clustered SE, a pragmatic step not in the original paper.

## Read when

- implementing or running `robustness.py`, or the Phase 3 options in `fe.py` and `rd.py`
- interpreting any Phase 3 check, flag, or sensitivity result

## Supersedes

- None (supplements ADR-0007)
