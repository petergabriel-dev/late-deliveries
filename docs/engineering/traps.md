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

## Tooling

- **pandas 3.** Copy-on-write and the default string dtype differ from pandas 2 examples; `Series.dt.weekday` raises a deprecation warning.
- **Decision index.** `/docs update-index` writes only in Pi Build mode. Check the index's modification time and contents after running it; a run in the wrong mode silently leaves it stale.
- **Filenames with spaces.** The project brief's filename has spaces; use `-z`/`-0` when piping git file lists to `xargs`.
