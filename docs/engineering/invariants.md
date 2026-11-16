# Invariants

Rules that must not break. Breaking one invalidates results or the audit trail.

## Rules

1. **People are `customer_unique_id`.** `customer_id` is per order. Any person-level logic (first order, repeat purchase) uses `customer_unique_id` only.
2. **Raw data is immutable.** Files in `data/raw/` are never edited. Every step that reads data runs `make check-data` first, and a checksum mismatch aborts the run. (ADR-0002)
3. **No outcome is split by treatment before pre-registration.** No code, notebook, or ad-hoc query computes `review_score`, `low_review`, `repeat_90d`, or `repeat_180d` by `late`, `days_late`, or `delivery_days` until ADR-0007 is committed. Pooled base rates for power calculations are allowed.
4. **Definitions live in one place and match the ADRs.** Treatment, outcome, and sample definitions live only in `src/late_delivery/config.py` and `src/late_delivery/build.py`, and must match ADR-0003, ADR-0004, and ADR-0005. Changing a definition requires a superseding ADR first.
5. **No silent row drops.** The built table keeps all 99,441 orders, each with an `exclusion_reason` when outside the headline sample; the exclusion counts reconcile to the raw order count. (ADR-0005)
6. **Every reported number is traceable.** Every number in the memo or write-up comes from code output or from the version-controlled assumptions file, `assumptions.toml`. No invented property of the data, statistic, or money input; measured inputs are referenced there, never copied. (ADR-0006, ADR-0013)
