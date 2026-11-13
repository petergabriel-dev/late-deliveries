"""Unit tests for Phase 2 estimators on synthetic data with planted effects (ADR-0008)."""

import numpy as np
import pandas as pd

from late_delivery import config as C
from late_delivery.fe import (
    DELIVERY_BIN_COLS, LATE_BIN_COLS, analysis_frame, fit, model_specs, run_grid,
)


def make_orders(n: int = 20_000, seed: int = 7, late_effect=None) -> pd.DataFrame:
    """Synthetic built table. Seller quality drives both lateness and low reviews (confounding).

    late_effect(days_late) -> planted change in P(low_review); default 0.15 for every late order.
    """
    rng = np.random.default_rng(seed)
    late_effect = late_effect or (lambda dl: np.where(dl > 0, 0.15, 0.0))
    sellers = rng.integers(0, 200, n)
    quality = rng.normal(0, 1, 200)[sellers]
    week = pd.Timestamp("2017-01-02") + pd.to_timedelta(7 * rng.integers(0, 20, n), unit="D")
    p_late = 1 / (1 + np.exp(-(-1.0 - 0.8 * quality)))
    days_late = np.where(rng.random(n) < p_late, rng.integers(1, 25, n), -rng.integers(0, 15, n))
    promised = rng.integers(10, 40, n)
    delivery_days = promised + days_late + rng.random(n)
    p_low = np.clip(0.15 - 0.05 * quality + late_effect(days_late), 0.01, 0.99)
    low = rng.random(n) < p_low
    score = np.where(low, rng.integers(1, 3, n), rng.integers(3, 6, n))
    t = pd.DataFrame({
        "order_id": [f"o{i:06d}" for i in range(n)],
        "in_headline": True,
        "seller_id": [f"s{s}" for s in sellers],
        "purchase_week": week,
        "main_category": rng.choice(["toys", "bed_bath_table", "unknown"], n),
        "customer_state": rng.choice(["SP", "RJ", "MG"], n),
        "price": rng.uniform(5, 300, n),
        "freight": np.where(rng.random(n) < 0.05, 0.0, rng.uniform(5, 40, n)),
        "n_items": rng.integers(1, 3, n),
        "distance_km": rng.uniform(10, 2500, n),
        "promised_days": pd.array(promised, dtype="Int64"),
        "days_late": pd.array(days_late, dtype="Int64"),
        "late": days_late > 0,
        "delivery_days": delivery_days,
        "review_score": pd.array(score, dtype="Int64"),
        "low_review": pd.array(low, dtype="boolean"),
        "is_first_order": True,
    })
    for w in C.REPEAT_WINDOWS:
        t[f"repeat_{w}d_eligible"] = True
        t[f"repeat_{w}d"] = pd.array(rng.random(n) < 0.02, dtype="boolean")
    return t


def test_analysis_frame_transforms():
    t = make_orders(n=12)
    t.loc[0, "freight"] = 0.0
    t.loc[1, "distance_km"] = 9000.0  # outside Brazil -> missing (ADR-0008 §1)
    t.loc[2, "distance_km"] = np.nan
    t.loc[3, "in_headline"] = False
    t.loc[4, "review_score"] = pd.NA
    t.loc[4, "low_review"] = pd.NA
    f = analysis_frame(t)
    assert len(f) == 11 and "o000003" not in set(f["order_id"])
    row = f.set_index("order_id")
    assert row.loc["o000000", "log_freight"] == 0.0
    kept = t[t["in_headline"] & t["distance_km"].le(C.DISTANCE_CAP_KM)]["distance_km"]
    for oid in ("o000001", "o000002"):
        assert row.loc[oid, "distance_missing"] == 1.0
        assert row.loc[oid, "distance_km"] == kept.median()
    assert not row.loc["o000004", "has_review"] and np.isnan(row.loc["o000004", "star_1"])
    assert f["distance_missing"].sum() == 2


def test_bin_edges():
    days = [-3, 0, 1, 2, 3, 7, 8, 14, 15, 30]
    dd = [7.99, 8.0, 14.99, 15.0, 21.99, 22.0, 1.0, 9.0, 16.0, 40.0]
    t = make_orders(n=len(days))
    t["days_late"] = pd.array(days, dtype="Int64")
    t["late"] = t["days_late"] > 0
    t["delivery_days"] = dd
    f = analysis_frame(t)
    expected_late = {
        "late_1_2": [0, 0, 1, 1, 0, 0, 0, 0, 0, 0], "late_3_7": [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
        "late_8_14": [0, 0, 0, 0, 0, 0, 1, 1, 0, 0], "late_15p": [0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
    }
    expected_dd = {
        "dd_0_7": [1, 0, 0, 0, 0, 0, 1, 0, 0, 0], "dd_8_14": [0, 1, 1, 0, 0, 0, 0, 1, 0, 0],
        "dd_15_21": [0, 0, 0, 1, 1, 0, 0, 0, 1, 0], "dd_22p": [0, 0, 0, 0, 0, 1, 0, 0, 0, 1],
    }
    assert LATE_BIN_COLS == list(expected_late) and DELIVERY_BIN_COLS == list(expected_dd)
    for col, want in {**expected_late, **expected_dd}.items():
        assert f[col].tolist() == want, col


def test_grid_is_the_pre_registered_25():
    specs = model_specs()
    assert len(specs) == 25
    assert [s["id"] for s in specs if s["role"] == "pre-registered primary"] == ["low_review/a"]
    assert {s["model"] for s in specs if s["outcome"].startswith("star_")} == {"a"}
    assert [s["id"] for s in specs if s["on_time_only"]] == [f"{o}/e" for o in ("low_review", "review_score", "repeat_90d", "repeat_180d")]


def test_fe_recovers_planted_late_effect():
    f = analysis_frame(make_orders())
    naive = f.loc[f["late"] == 1, "low_review"].mean() - f.loc[f["late"] == 0, "low_review"].mean()
    assert abs(naive - 0.15) > 0.02  # confounding is real, so recovery below is not trivial
    e = fit(f, "low_review", ["late"])["estimates"][0]
    assert e["ci95_low"] <= 0.15 <= e["ci95_high"]
    assert abs(e["estimate"] - 0.15) < 0.02


def test_fe_recovers_planted_bin_effects():
    truth = {"late_1_2": 0.05, "late_3_7": 0.10, "late_8_14": 0.20, "late_15p": 0.30}
    effect = lambda dl: np.select([dl <= 0, dl <= 2, dl <= 7, dl <= 14], [0.0, 0.05, 0.10, 0.20], 0.30)  # noqa: E731
    f = analysis_frame(make_orders(late_effect=effect))
    est = {e["term"]: e for e in fit(f, "low_review", LATE_BIN_COLS)["estimates"]}
    # Four coefficients: a joint band (|z| < 3.3 each, ~99.6% jointly) instead of four 95% CIs,
    # which would all cover only ~81% of the time.
    for term, value in truth.items():
        assert abs(est[term]["estimate"] - value) < 3.3 * est[term]["se"], term


def test_run_grid_samples():
    t = make_orders(n=4_000)
    t.loc[:99, "review_score"] = pd.NA
    t.loc[:99, "low_review"] = pd.NA
    rows = {r["id"]: r for r in run_grid(analysis_frame(t))}
    assert len(rows) == 25
    on_time = int((t["days_late"] <= 0).sum())
    assert rows["repeat_90d/e"]["n_sample"] == on_time
    assert rows["low_review/a"]["n_sample"] == 4_000 - 100
    assert all(r["n_obs"] + r["singleton_rows_dropped"] == r["n_sample"] for r in rows.values())
