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
