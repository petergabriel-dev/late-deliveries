"""Data-quality tests on the real data and the built table (read-only).

Pinned counts come from the 2026-11-13 profiling of the committed raw CSVs.
A changed count means the raw data or a definition changed: investigate first.
Requires `make build` (orders.parquet + exclusions.json); `make test` runs it.
"""

import hashlib
import json
import warnings
from datetime import date

import pandas as pd
import pytest

from late_delivery import config as C
from late_delivery.build import EXCLUSION_ORDER, FILES, read_csv

# Known issue, kept by project-owner decision (T5, 2026-11-13): 42 geolocation rows lie outside
# Brazil, pulling some zip-prefix medians abroad. Reported, not fixed; revisit in ADR-0007.
KNOWN_DISTANCE_OUTLIERS_OVER_5000_KM = 3


@pytest.fixture(scope="module")
def raw():
    names = ["orders", "reviews", "items", "customers", "sellers", "geolocation"]
    return {n: read_csv(C.RAW_DIR / FILES[n]) for n in names}


@pytest.fixture(scope="module")
def t():
    return pd.read_parquet(C.ORDERS_PARQUET)


def test_checksums_match():
    for line in (C.RAW_DIR / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        assert hashlib.sha256((C.RAW_DIR / name).read_bytes()).hexdigest() == digest, name


def test_raw_counts(raw):
    o = raw["orders"]
    assert len(o) == 99_441
    assert (o["order_status"] == "delivered").sum() == 96_478
    assert len(raw["reviews"]) == 99_224
    assert len(raw["items"]) == 112_650


def test_one_row_per_order(t):
    assert len(t) == 99_441 and t["order_id"].is_unique


def test_estimated_dates_are_midnight(raw):
    assert raw["orders"]["order_estimated_delivery_date"].str.endswith("00:00:00").all()


def test_no_delivery_before_purchase(t):
    d = t.dropna(subset=["delivery_ts"])
    assert (d["delivery_ts"] >= d["purchase_ts"]).all()


def test_days_late_matches_calendar_difference(raw, t):
    # Independent recomputation from the raw strings with the standard library.
    o = raw["orders"].dropna(subset=["order_delivered_customer_date"])
    expected = {
        oid: (date.fromisoformat(dlv[:10]) - date.fromisoformat(est[:10])).days
        for oid, dlv, est in zip(o["order_id"], o["order_delivered_customer_date"], o["order_estimated_delivery_date"])
    }
    got = t.set_index("order_id")["days_late"].dropna().astype(int).to_dict()
    assert got == expected


def test_review_scores_in_range(raw, t):
    assert raw["reviews"]["review_score"].between(1, 5).all()
    assert t["review_score"].dropna().between(1, 5).all()


def test_headline_rows_follow_adr_0005(t):
    h = t[t["in_headline"]]
    assert (h["order_status"] == "delivered").all()
    assert h["delivery_ts"].notna().all()
    assert (h["n_sellers"] == 1).all() and h["seller_id"].notna().all()
    assert h["purchase_ts"].between(C.WINDOW_START, C.WINDOW_END, inclusive="left").all()


def test_exclusion_waterfall_reconciles(t):
    summary = json.loads(C.EXCLUSIONS_JSON.read_text())
    excluded = {e["reason"]: e["orders"] for e in summary["excluded"]}
    assert list(excluded) == EXCLUSION_ORDER
    assert summary["in_headline"] + sum(excluded.values()) == summary["total_orders"] == 99_441
    counts = t["exclusion_reason"].value_counts()
    assert all(int(counts.get(r, 0)) == n for r, n in excluded.items())
    assert int(t["in_headline"].sum()) == summary["in_headline"]


def test_distance_bounds(t):
    dist = t["distance_km"].dropna()
    assert (dist >= 0).all()
    outliers = int((dist > 5000).sum())
    if outliers:
        warnings.warn(f"{outliers} orders have distance_km > 5,000 (known out-of-Brazil geolocation rows)")
    assert outliers == KNOWN_DISTANCE_OUTLIERS_OVER_5000_KM


def test_geo_missing_counts(raw, t):
    prefixes = set(raw["geolocation"]["geolocation_zip_code_prefix"])
    assert (~raw["customers"]["customer_zip_code_prefix"].isin(prefixes)).sum() == 278
    assert (~raw["sellers"]["seller_zip_code_prefix"].isin(prefixes)).sum() == 7
    assert int(t.loc[t["in_headline"], "distance_km"].isna().sum()) == 470
