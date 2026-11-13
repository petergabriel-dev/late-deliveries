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
        ├── tests/                     (make test)        unit + data-quality checks
        ├── src/late_delivery/diagnostics.py  (make diagnostics) → outputs/diagnostics.{md,json}, fig_*.png
        └── src/late_delivery/naive.py        (make naive)       → outputs/naive.{md,json}
```

`make all` runs check-data → build → test → diagnostics → naive. Everything under `data/processed/` and `outputs/` is generated and gitignored.

## Components

| Module | Responsibility |
|---|---|
| `config.py` | Every analysis parameter: paths, purchase window, repeat windows, follow-up cap, low-review threshold, Black Friday date. |
| `build.py` | Reads the 8 CSVs the analysis needs; builds treatment, outcome, covariate and sample columns (ADR-0003..0005); writes the parquet and exclusion counts. Pure functions plus `main()`. |
| `diagnostics.py` | Phase 1 design diagnostics. Never loads `review_score` or `low_review`; the only outcome statistic is the pooled repeat base rate for power (invariant 3). |
| `naive.py` | Biased late vs on-time baseline, allowed only after ADR-0007. |

## Order-level table (`orders.parquet`)

| Group | Columns |
|---|---|
| Keys | `order_id`, `customer_id`, `customer_unique_id`, `order_status` |
| Timestamps | `purchase_ts`, `delivery_ts`, `estimated_date` |
| Treatment | `days_late`, `late`, `delivery_days`, `promised_days` |
| Review outcomes | `review_score`, `low_review`, `review_created_before_delivery` |
| Repeat outcomes | `is_first_order`, `repeat_90d_eligible`, `repeat_90d`, `repeat_180d_eligible`, `repeat_180d` |
| Covariates | `n_items`, `n_sellers`, `price`, `freight`, `main_category`, `seller_id`, `seller_state`, `customer_state`, `distance_km`, `purchase_month`, `purchase_week`, `bf_2017` |
| Sample | `exclusion_reason`, `in_headline` |

Exclusion rules apply in precedence order: `not_delivered`, `missing_delivery_ts`, `outside_window`, `no_items`, `multi_seller`. The 94,931 orders that pass all of them form the headline sample.

## Not used yet

`olist_order_payments_dataset.csv` is committed but not read; GMV and payment inputs arrive with the Phase 4 money translation (ADR-0006).
