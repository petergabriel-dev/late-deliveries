# Conventions

## Layout

- Package code in `src/late_delivery/` (uv_build backend); one module per pipeline step, each with a `main()` run as `python -m late_delivery.<module>`.
- Tests in `tests/`: `test_build.py` (definitions on small synthetic fixtures), `test_data_quality.py` (real data, pinned counts).
- Generated files go to `data/processed/` and `outputs/`, both gitignored. Never commit generated output.

## Parameters and definitions

- Every analysis parameter lives in `src/late_delivery/config.py`, with a comment naming the ADR it implements.
- Treatment, outcome and sample definitions live only in `build.py` and must match ADR-0003..0005 (invariant 4). Changing one needs a superseding ADR first.

## Code style

- Pure transform functions plus a thin `main()` that reads, writes and prints.
- Read every CSV with `encoding="utf-8-sig"` (one file has a BOM).
- Parse timestamps with the strict format `%Y-%m-%d %H:%M:%S`, so a malformed value raises instead of becoming missing.
- pandas 3 semantics: no chained assignment; use `Series.dt.day_of_week`, not the deprecated `dt.weekday`.
- Nullable dtypes (`Int64`, `boolean`) for columns that are legitimately missing (e.g., `days_late` for undelivered orders).
- Fail loudly on broken assumptions: `build.py` raises if a join changes the row count or the exclusion counts don't reconcile.
- Mark deliberate shortcuts with a `ponytail:` comment stating the limitation.

## Outputs

- Deterministic: floats rounded to 6 decimals in JSON, stable sort orders, no timestamps in output files.
- Every reported number is computed in code; markdown reports interpolate values from the same result dict as the JSON.
- Code that runs before ADR-0007 must not split `review_score`, `low_review`, `repeat_90d` or `repeat_180d` by `late`, `days_late` or `delivery_days` (invariant 3).

## Charts

- matplotlib (Agg), static PNG, light theme. Reference palette slot 1 (`#2a78d6`) for single-series charts; text in ink tokens; recessive grid.
- Never a twin y-axis: two measures get two panels.

## Decisions and commits

- One ADR per decision (ADR-0001); index regenerated with Pi `/docs update-index`.
- One commit per saved-plan task; commit messages start with the task id (e.g., `T4:`).
