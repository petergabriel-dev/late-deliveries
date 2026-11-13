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
