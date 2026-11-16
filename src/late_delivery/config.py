"""Analysis parameters: the single source of truth. Must match ADR-0003..0005."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUTS_DIR = ROOT / "outputs"
ORDERS_PARQUET = PROCESSED_DIR / "orders.parquet"
EXCLUSIONS_JSON = OUTPUTS_DIR / "exclusions.json"

TS_FORMAT = "%Y-%m-%d %H:%M:%S"

# ADR-0005: headline purchase window, 2017-01-01 through 2018-08-31 (end exclusive).
WINDOW_START = pd.Timestamp("2017-01-01")
WINDOW_END = pd.Timestamp("2018-09-01")

# ADR-0004: repeat-purchase windows in days after first-order delivery (90 primary, 180 check).
REPEAT_WINDOWS = (90, 180)
# ADR-0004: eligible only if delivery + window falls on or before 2018-08-31 (end exclusive).
FOLLOWUP_END = pd.Timestamp("2018-09-01")

# ADR-0004: low_review = review score at or below this value.
LOW_REVIEW_MAX = 2

# ADR-0005: Black Friday 2017 purchase date (kept in headline; excluded only as robustness).
BLACK_FRIDAY_2017 = pd.Timestamp("2017-11-24")

# ADR-0008 §1: distances above this are treated as missing at analysis time (build unchanged).
DISTANCE_CAP_KM = 5000.0

# ADR-0007 §3 / ADR-0008 §2: days-late bins, inclusive integer days; None = open-ended.
# Reference: on time (days_late <= 0).
LATE_BINS = ((1, 2), (3, 7), (8, 14), (15, None))
# ADR-0008 §2: slowness bins on fractional delivery_days, [lo, hi); the first bin is the reference.
DELIVERY_DAY_BINS = ((0, 8), (8, 15), (15, 22), (22, None))

# ADR-0008 §3: donut RD. Cutoff between day 0 and day +1; h = 7.5 -> days -6..+7.
RD_CUTOFF = 0.5
RD_BANDWIDTH = 7.5
RD_SENSITIVITY_BANDWIDTHS = (5.5, 10.5)
RD_DONUT_DAYS = (0, 1)

# ADR-0008 §4: matching caliper, in SDs of the logit propensity score.
MATCH_CALIPER_SD = 0.2

# ADR-0011 §2: check 1, late = at least this many days late (day +1 counts as on time).
CHECK1_LATE_MIN_DAYS = 2
# ADR-0011 §3: purchase windows dropped by checks 3 and 10, [start, end) on the purchase timestamp.
BLACK_FRIDAY_WEEK_2017 = (pd.Timestamp("2017-11-24"), pd.Timestamp("2017-12-01"))  # check 3: 11-24..11-30
SURGE_2018 = (pd.Timestamp("2018-02-01"), pd.Timestamp("2018-04-01"))  # check 10: Feb-Mar 2018
# ADR-0011 §3: check 10, truckers' strike, first and last day inclusive (sources cited in ADR-0011).
# An order is dropped if purchase date <= last day and promised date >= first day.
STRIKE_2018 = (pd.Timestamp("2018-05-21"), pd.Timestamp("2018-06-02"))
# ADR-0011 §3: check 11, purchases on or after this date.
CHECK11_WINDOW_START = pd.Timestamp("2017-02-01")
# ADR-0011 §3: check 7, seller_id and seller_state label shared by multi-seller orders.
MULTI_SELLER_LABEL = "multi_seller"
# ADR-0011 §4: check 4 placebo cutoffs, each with the two days straddling it dropped (donut).
PLACEBO_CUTOFFS = ((-6.5, (-7, -6)), (7.5, (7, 8)))
# ADR-0011 §4: check 5, covariates tested for continuity at the real cutoff (main RD spec).
CONTINUITY_COVARIATES = ("log_price", "log_freight", "n_items", "distance_km", "promised_days")
# ADR-0011 §5: check 6 benchmark groups (analysis-frame columns) and confounder strengths k (kd = ky = k).
SENSITIVITY_BENCHMARKS = {"distance": ("distance_km", "distance_missing"), "customer_state": ("customer_state",)}
SENSITIVITY_K = (1, 2, 3)

# ADR-0013 §8: every Phase 4 money input (assumed values with sources; measured inputs as refs).
ASSUMPTIONS_TOML = ROOT / "assumptions.toml"
# ADR-0013 §6: flag 1 fires if measured channel 1 is below this share of the central total.
MONEY_MEASURED_SHARE_MIN = 0.10
# ADR-0013 §3: order statuses left out of the seller's later orders exposed to a bad review.
LATER_ORDER_EXCLUDED_STATUSES = ("canceled", "unavailable")

# ADR-0015: reader-facing report templates and rendered documents.
REPORT_DIR = ROOT / "docs" / "report"
# ADR-0015: computed report values, not a hand-maintained analysis source.
REPORT_JSON = OUTPUTS_DIR / "report.json"
# ADR-0015: (template, target) pairs added with each communication deliverable.
REPORT_TEMPLATES = ((REPORT_DIR / "memo.template.md", REPORT_DIR / "memo.md"),
                    (REPORT_DIR / "writeup.template.md", REPORT_DIR / "writeup.md"),
                    (REPORT_DIR / "README.template.md", ROOT / "README.md"))
# ADR-0015: Markdown memo word cap; changing it requires a new ADR.
MEMO_MAX_WORDS = 450
