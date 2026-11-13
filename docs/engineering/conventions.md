# Conventions

## Layout

- Package code in `src/late_delivery/` (uv_build backend); one module per pipeline step, each with a `main()` run as `python -m late_delivery.<module>`.
- Tests in `tests/`: `test_build.py` (definitions on small synthetic fixtures), `test_data_quality.py` (real data, pinned counts), `test_estimators.py` (Phase 2 estimators on synthetic data with planted effects, plus the ladder's verdict and flag logic). Estimator tests check that the known effect lies inside the 95% CI and within 0.02; tests of several coefficients at once use a joint band (|z| < 3.3 each).
- Generated files go to `data/processed/` and `outputs/`, both gitignored. Never commit generated output.

## Parameters and definitions

- Every analysis parameter lives in `src/late_delivery/config.py`, with a comment naming the ADR it implements.
- Treatment, outcome and sample definitions live only in `build.py` and must match ADR-0003..0005 (invariant 4). Changing one needs a superseding ADR first.
- Analysis-time transforms (log1p price and freight, distance cap and fill, treatment bins; ADR-0008 §1-2) live only in `fe.analysis_frame()`, which every estimator reuses.

## Code style

- Pure transform functions plus a thin `main()` that reads, writes and prints.
- Read every CSV with `encoding="utf-8-sig"` (one file has a BOM).
- Parse timestamps with the strict format `%Y-%m-%d %H:%M:%S`, so a malformed value raises instead of becoming missing.
- pandas 3 semantics: no chained assignment; use `Series.dt.day_of_week`, not the deprecated `dt.weekday`.
- Nullable dtypes (`Int64`, `boolean`) for columns that are legitimately missing (e.g., `days_late` for undelivered orders).
- Fail loudly on broken assumptions: `build.py` raises if a join changes the row count or the exclusion counts don't reconcile. Estimators raise instead of silently degrading: a term of interest dropped as collinear, donut days in a donut sample, a bandwidth other than the one requested, a non-converged logit, a cross-week or over-caliper match.
- Cast nullable columns to float64 with NaN before handing them to pyfixest or statsmodels (`fe._float`).
- Build row masks as pandas Series (`mask = mask & cond`); under copy-on-write, `Series.to_numpy()` can return a read-only view, so `mask &= ...` on it fails.
- Mark deliberate shortcuts with a `ponytail:` comment stating the limitation.

## Outputs

- Deterministic: floats rounded to 6 decimals in JSON, stable sort orders, no timestamps in output files.
- Every reported number is computed in code; markdown reports interpolate values from the same result dict as the JSON.
- Each estimator writes `outputs/<module>.{md,json}`. The JSON echoes its own specification (sample, N after drops and why, clusters, bandwidth or caliper, unmatched counts), so a reviewer can audit it without reading code. Every estimate carries a role label: headline, secondary, corroborating, sensitivity or biased baseline.
- p-values below the JSON's precision show as `<1e-06` in markdown, not `0`. Write `abs(SMD)`, not `|SMD|`, inside markdown table cells.
- Code that runs before ADR-0007 must not split `review_score`, `low_review`, `repeat_90d` or `repeat_180d` by `late`, `days_late` or `delivery_days` (invariant 3).

## Charts

- matplotlib (Agg), static PNG, light theme. Reference palette slot 1 (`#2a78d6`) for single-series charts; text in ink tokens; recessive grid.
- Never a twin y-axis: two measures get two panels.

## Decisions and commits

- One ADR per decision (ADR-0001); index regenerated with Pi `/docs update-index`.
- One commit per saved-plan task; commit messages start with the task id (e.g., `T4:`). Exception: when a decision must be on record before code computes estimates, its ADR gets its own commit with the same task id first (T13: ADR-0009, then the matching code).
