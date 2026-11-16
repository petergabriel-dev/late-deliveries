# Architecture

A linear batch pipeline: committed raw CSVs in, one order-level table, then analysis outputs. No services, no database.

## Data flow

```text
data/raw/*.csv + SHA256SUMS  (committed, immutable)
        │  make check-data   (shasum -c; aborts on mismatch)
        ▼
src/late_delivery/build.py   (make build)
        │  → data/processed/orders.parquet   one row per order, all 99,441
        │  → outputs/exclusions.json         exclusion waterfall
        ▼
        ├── tests/                            (make test)        unit + data-quality checks
        ├── src/late_delivery/diagnostics.py  (make diagnostics) → outputs/diagnostics.{md,json}, fig_monthly.png, fig_days_late.png
        ├── src/late_delivery/naive.py        (make naive)       → outputs/naive.{md,json}
        ├── src/late_delivery/fe.py           (make fe)          → outputs/fe.{md,json}
        ├── src/late_delivery/rd.py           (make rd)          → outputs/rd.{md,json}, fig_rd.png
        └── src/late_delivery/matching.py     (make matching)    → outputs/matching.{md,json}
                │  naive.json + fe.json + rd.json + matching.json
                ▼
        src/late_delivery/ladder.py           (make ladder)      → outputs/ladder.{md,json}, fig_ladder.png

orders.parquet + fe.json + rd.json
        ▼
src/late_delivery/robustness.py               (make robustness)  → outputs/robustness.{md,json}, fig_robustness.png

orders.parquet + fe.json + assumptions.toml
        ▼
src/late_delivery/money.py                    (make money)       → outputs/money.{md,json}, fig_money_tornado.png
```

`make all` runs check-data → build → test → diagnostics → naive, fe, rd, matching → ladder → robustness → money. Generated results in `outputs/` are committed and guarded by `make check-outputs` (PNG bytes excluded; ADR-0015); intermediate data in `data/processed/` stays gitignored and untracked. `assumptions.toml` (repo root, committed) holds every money input (ADR-0013 §8).

## Components

| Module | Responsibility |
|---|---|
| `config.py` | Every analysis parameter: paths, purchase window, repeat windows, follow-up cap, low-review threshold, Black Friday date; Phase 2 distance cap, days-late and delivery-days bins, RD cutoff and bandwidths, matching caliper (ADR-0008); Phase 3 check windows, strike dates, placebo cutoffs, continuity covariates, sensitivity benchmarks (ADR-0011); Phase 4 assumptions-file path, flag 1 threshold, statuses left out of later orders (ADR-0013). Money input values live in `assumptions.toml`, not here. |
| `build.py` | Reads the 8 CSVs the analysis needs; builds treatment, outcome, covariate and sample columns (ADR-0003..0005); writes the parquet and exclusion counts. Pure functions plus `main()`. |
| `diagnostics.py` | Phase 1 design diagnostics. Never loads `review_score` or `low_review`; the only outcome statistic is the pooled repeat base rate for power (invariant 3). Also holds the shared report helpers (`md_table`, `rounded`) and chart palette. |
| `naive.py` | Biased late vs on-time baseline, allowed only after ADR-0007. |
| `fe.py` | `analysis_frame()`: the shared analysis-time frame (headline rows, log1p price and freight, distance cap and fill, treatment bins; ADR-0008 §1), with an `include_multi_seller` option and pass-through columns for Phase 3 (ADR-0011 §6). The 25 pre-registered fixed-effects models (pyfixest; ADR-0007 §3, ADR-0008 §2), including the headline. |
| `rd.py` | Donut regression discontinuity at the promised date on `low_review`, plus three sensitivity runs (rdrobust; ADR-0008 §3). Corroborating. `rd_sample()` and `estimate()` take a cutoff, donut days and outcome, so Phase 3 reuses them for placebo and continuity checks. |
| `matching.py` | Propensity-score matching on `low_review`: separation drop (ADR-0009), statsmodels logit, exact match on week, nearest neighbour with caliper, weighted OLS, balance table (ADR-0008 §4). Corroborating. |
| `ladder.py` | Reads the four estimate JSONs; computes the ADR-0007 §4 verdicts and the falsification flags in code (ADR-0008 §5). ADR-0010 records how they were read. |
| `robustness.py` | The 12 pre-registered Phase 3 checks (ADR-0007 §7): check samples (relabels, date and review masks, multi-seller frame), FE, placebo and continuity runners, hand-rolled Cinelli-Hazlett sensitivity, and the ADR-0011 §1 flags computed in code. ADR-0012 records how they were read. |
| `money.py` | Phase 4 cost per late delivery (ADR-0013): validates `assumptions.toml` and resolves measured refs in `fe.json`; channel 1 (repeat, measured upper bound), channel 2 (rating spillover: seller exposure from each late order's review answer time, per-later-order dilution by the seller's visible review count), channel 3 (illustrative add-on); corners, tornado and flags 1-3 computed in code; the disruption scenario re-fit on `robustness.check_frames(t)[10]`; the lateness-mix decomposition. ADR-0014 records how the results were read. |

## Order-level table (`orders.parquet`)

| Group | Columns |
|---|---|
| Keys | `order_id`, `customer_id`, `customer_unique_id`, `order_status` |
| Timestamps | `purchase_ts`, `delivery_ts`, `estimated_date` |
| Treatment | `days_late`, `late`, `delivery_days`, `promised_days` |
| Review outcomes | `review_score`, `low_review`, `review_created_before_delivery`, `n_reviews` (raw review rows per order; Phase 3 check 12), `review_answer_ts` (when the kept review was answered; Phase 4 channel 2 anchor) |
| Repeat outcomes | `is_first_order`, `repeat_90d_eligible`, `repeat_90d`, `repeat_180d_eligible`, `repeat_180d`, `repeat_90d_gmv`, `repeat_180d_gmv` (item price of the repeat orders under the same rule; 0 if none, missing if not eligible) |
| Covariates | `n_items`, `n_sellers`, `price`, `freight`, `main_category`, `seller_id`, `seller_state`, `customer_state`, `distance_km`, `purchase_month`, `purchase_week`, `bf_2017` |
| Sample | `exclusion_reason`, `in_headline` |

Exclusion rules apply in precedence order: `not_delivered`, `missing_delivery_ts`, `outside_window`, `no_items`, `multi_seller`. The 94,931 orders that pass all of them form the headline sample.

## Not used yet

`olist_order_payments_dataset.csv` is committed but not read: Phase 4 GMV is item price from the order-items table (ADR-0013 §1), and the payments table has no refund field.
