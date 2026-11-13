"""Unit tests for Phase 2 estimators on synthetic data with planted effects (ADR-0008)."""

import numpy as np
import pandas as pd
import pytest

from late_delivery import config as C
from late_delivery import matching, rd
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


def rd_frame(n: int = 200_000, jump: float = 0.20, seed: int = 3) -> pd.DataFrame:
    """Analysis-frame columns the RD reads: a planted jump at the cutoff, junk on the donut days."""
    rng = np.random.default_rng(seed)
    x = rng.integers(-12, 13, n).astype(float)
    p = 0.10 + 0.005 * x + jump * (x >= 1)
    y = (rng.random(n) < p).astype(float)
    y[np.isin(x, C.RD_DONUT_DAYS)] = 1.0  # sorting/heaping at the cutoff: only the donut protects the estimate
    return pd.DataFrame({"days_late": x, "low_review": y, "has_review": True,
                         "seller_id": [f"s{s}" for s in rng.integers(0, 2_000, n)]})


def test_rd_recovers_planted_jump_with_donut():
    f = rd_frame()
    main = rd.run(f)[0]
    assert main["spec"] == "main" and main["dropped_days"] == [0, 1]
    assert main["days_left"] == [-6, -5, -4, -3, -2, -1] and main["days_right"] == [2, 3, 4, 5, 6, 7]
    assert main["ci95_low"] <= 0.20 <= main["ci95_high"]
    assert abs(main["estimate"] - 0.20) < 0.02
    no_donut = rd.run(f)[-1]
    assert no_donut["spec"] == "no donut" and abs(no_donut["estimate"] - 0.20) > 0.1  # the junk days bite without it


def test_rd_window_and_donut_guards():
    f = rd_frame(n=20_000)
    for s in rd.SPECS:
        d = rd.rd_sample(f, s["bandwidth"], s["donut"])
        assert (d["days_late"] - C.RD_CUTOFF).abs().max() < s["bandwidth"]
        assert d["days_late"].isin(C.RD_DONUT_DAYS).any() != s["donut"]
    with pytest.raises(ValueError, match="donut"):
        rd.estimate(rd.rd_sample(f, C.RD_BANDWIDTH, donut=False), C.RD_BANDWIDTH, donut=True)


def test_nearest_matches_rules():
    rows = [  # (order_id, week, late, score)
        ("t1", "A", 1, 0.00), ("t2", "A", 1, 1.00), ("t5", "A", 1, 0.12), ("t6", "A", 1, 0.11),
        ("c9", "A", 0, 0.10), ("c1", "A", 0, -0.10), ("c5", "A", 0, 0.95), ("c7", "A", 0, 9.00),
        ("t3", "B", 1, 9.00), ("c2", "B", 0, 0.00),  # nearest same-week control is beyond the caliper
        ("t4", "C", 1, 0.00),  # no control in week C (c7 in week A must not be used)
    ]
    d = pd.DataFrame(rows, columns=["order_id", "purchase_week", "late", "score"])
    d["low_review"] = 0.0
    d["seller_id"] = "s"
    pairs = matching.nearest_matches(d, caliper=0.5)
    by_id = {d.loc[t, "order_id"]: d.loc[c, "order_id"] for t, c in zip(pairs["treated"], pairs["control"])}
    # t1 is 0.10 from both c9 and c1: the tie goes to the lowest order_id (c1).
    assert by_id == {"t1": "c1", "t2": "c5", "t5": "c9", "t6": "c9"}
    ms = matching.matched_sample(d, pairs, caliper=0.5)
    weights = dict(zip(ms.loc[ms["late"] == 0, "order_id"], ms.loc[ms["late"] == 0, "w"]))
    assert weights == {"c1": 1.0, "c9": 2.0, "c5": 1.0}
    idx = dict(zip(d["order_id"], d.index))
    cross = pd.DataFrame({"treated": [idx["t3"]], "control": [idx["c7"]], "distance": [0.0], "purchase_week": ["B"]})
    with pytest.raises(RuntimeError, match="crosses purchase weeks"):
        matching.matched_sample(d, cross, caliper=0.5)
    with pytest.raises(RuntimeError, match="caliper"):
        matching.matched_sample(d, pairs.assign(distance=0.6), caliper=0.5)


def test_drop_separated_levels():
    m = pd.DataFrame({
        "late": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        "main_category": ["a", "a", "rare", "a", "a", "a"],
        "customer_state": ["SP"] * 6,
        "purchase_week": ["w1", "w1", "w1", "w2", "w2", "w9"],
    })
    kept, dropped = matching.drop_separated(m)
    assert len(kept) == 4 and kept["late"].sum() == 2
    assert {(x["variable"], x["level"]) for x in dropped} == {("main_category", "rare"), ("purchase_week", "w9")}


def matching_frame(n: int = 40_000, seed: int = 11, effect: float = 0.15) -> pd.DataFrame:
    """Analysis-frame columns for matching; confounding only through observed controls."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    late = (rng.random(n) < 1 / (1 + np.exp(-(-1.2 + 1.0 * z)))).astype(float)
    p = np.clip(0.15 + 0.05 * z + effect * late, 0.01, 0.99)
    f = pd.DataFrame({
        "order_id": [f"o{i:06d}" for i in range(n)],
        "seller_id": [f"s{s}" for s in rng.integers(0, 500, n)],
        "purchase_week": [f"w{w:02d}" for w in rng.integers(0, 10, n)],
        "main_category": rng.choice(["toys", "bed_bath_table", "unknown"], n),
        "customer_state": rng.choice(["SP", "RJ", "MG"], n),
        "log_price": rng.normal(4, 1, n), "log_freight": z + rng.normal(0, 0.1, n),
        "n_items": rng.integers(1, 3, n).astype(float), "distance_km": rng.uniform(10, 2500, n),
        "distance_missing": (rng.random(n) < 0.01).astype(float), "promised_days": rng.integers(10, 40, n).astype(float),
        "late": late, "low_review": (rng.random(n) < p).astype(float),
    })
    return f


def test_matching_recovers_planted_att():
    f = matching_frame()
    naive = f.loc[f["late"] == 1, "low_review"].mean() - f.loc[f["late"] == 0, "low_review"].mean()
    assert abs(naive - 0.15) > 0.02  # confounded through log_freight
    r = matching.run(f)
    a, s = r["att"], r["sample"]
    assert a["ci95_low"] <= 0.15 <= a["ci95_high"] and abs(a["estimate"] - 0.15) < 0.02
    assert s["orders_dropped_separation"] == 0 and s["matched_late"] + s["unmatched_late"] == s["late_orders"]
    assert r["balance"]["max_abs_smd_after"] < 0.1
    assert r == matching.run(f)  # deterministic


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
