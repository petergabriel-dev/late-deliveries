# Traps

Known gotchas in the Olist data and this pipeline. Counts are from the committed raw data.

## Data

- **BOM header.** `product_category_name_translation.csv` starts with a UTF-8 BOM; read with `utf-8-sig` or the first column name comes out as `﻿product_category_name`.
- **Promised date has no time of day.** `order_estimated_delivery_date` is always midnight, so days late is a whole-day (discrete) running variable. Compare calendar dates, not timestamps.
- **Survey timing.** Olist sends the review survey at delivery, or after the promised date if the order hasn't arrived. On-time reviews are created the day after delivery; late-order reviews are created about 2 days after the promised date. Reviews written before delivery: 0.7% at 1 day late, 6.0% at 2, 70% at 3, 91-100% beyond (headline sample).
- **Bunching at the promised date.** Orders fall 36% from day 0 to day +1, against about 10% per day just before; `rddensity` results swing with bandwidth and polynomial order, and its automatic bandwidth returns a negative density.
- **Same-session orders.** 30.9% of second orders by a person come within one day of the first (one cart split into orders). Repeat purchase counts only orders placed after the first order's delivery.
- **`customer_id` is per order.** Use `customer_unique_id` for people (96,096 people, 99,441 orders).
- **Reviews are not one per order.** 547 orders have more than one review, 768 have none, and some `review_id`s are attached to several orders. The build keeps the latest-answered review per order.
- **Delivered without a delivery date.** 8 orders have status `delivered` but no customer delivery timestamp.
- **Multi-seller orders.** 1,278 orders contain items from more than one seller; they have no single `seller_id` or distance and are excluded from the headline sample.
- **Geolocation duplicates and outliers.** Up to 1,146 rows per zip prefix (the build takes the median). 42 rows lie outside Brazil, giving 3 orders a distance over 5,000 km; kept as-is by decision and pinned in `test_data_quality.py`. 278 customer rows and 7 sellers have no geolocation match. Prefix 53990 (Fernando de Noronha) is a real island far east of the mainland.
- **Untranslated categories.** `pc_gamer` and `portateis_cozinha_e_preparadores_de_alimentos` have no English name; the build keeps the Portuguese name. 610 products have no category (`unknown`).
- **No carrier identifier.** No table records the carrier, so carrier quality is an unobserved confounder.
- **Thin edges.** 2016 and Sep-Oct 2018 have very few orders; the headline window is 2017-01-01 to 2018-08-31.
- **Zero freight.** 336 headline orders have freight 0, where `log` is undefined; price and freight enter the models as `log1p` (ADR-0008).
- **`delivery_days` is fractional.** It is elapsed time from purchase to delivery (0.53 to 209.6 days), so bins are half-open, [lo, hi): "8-14" means 8 <= days < 15.
- **Groups with no late orders.** Among headline orders with a review, purchase week 2018-08-27 and 7 rare categories have no late orders (211 orders in all). Their dummies perfectly predict "on time", so the propensity logit does not converge with them; matching drops those orders first (ADR-0009).

## Tooling

- **pandas 3.** Copy-on-write and the default string dtype differ from pandas 2 examples; `Series.dt.weekday` raises a deprecation warning.
- **Decision index.** `/docs update-index` writes only in Pi Build mode. Check the index's modification time and contents after running it; a run in the wrong mode silently leaves it stale. From Claude Code, importing Pi's `engineering-docs/filesystem.ts` with Node fails (`ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING`: no type stripping under `node_modules`). Instead, take the source of its functions from `parseFrontmatter` to `updateDecisionIndex`, strip the types with `node:module`'s `stripTypeScriptTypes`, and evaluate it with the constants from `constants.ts`. Its output matches Pi's byte for byte.
- **Triangular kernel edge.** With cutoff 0.5 and bandwidth h, a day exactly h from the cutoff gets zero weight and rdrobust leaves it out of `N_h`. `rd.py` keeps only days with |days_late - 0.5| < h and checks `N_h == N`.
- **rdrobust quirks.** With `cluster=`, `vce="hc1"` is switched to `"cr1"` with a warning, so `rd.py` passes `"cr1"` (the same CR1 estimator). It prints a mass-point notice to stdout. The robust CI is centred on the bias-corrected estimate, so the conventional estimate of record can lie outside its own CI. Draw CIs as segments, not `errorbar` (negative lengths raise).
- **pyfixest.** Collinear regressors silently disappear from `_coefnames`, so `fe.fit` raises if a term of interest is dropped. CIs use t with (clusters - 1) degrees of freedom. The first run on a machine compiles numba code and is slower.
- **Per-level balance flag.** Matching balance is checked for every category and state level, so a rare level can exceed abs(SMD) 0.1 by chance (none did: max 0.0511).
- **Filenames with spaces.** The project brief's filename has spaces; use `-z`/`-0` when piping git file lists to `xargs`.
