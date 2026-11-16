"""Unit tests for Phase 2 estimators on synthetic data with planted effects (ADR-0008)."""

import numpy as np
import pandas as pd
import pytest

from late_delivery import config as C
from late_delivery import ladder, matching, rd
from late_delivery import robustness as R
from late_delivery.fe import (
    CONTROLS, DELIVERY_BIN_COLS, LATE_BIN_COLS, analysis_frame, fit, model_specs, run_grid,
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
        # Phase 3 pass-through columns: no rng draws, so earlier planted-effect tests see the same data.
        "exclusion_reason": pd.Series([None] * n, dtype=object),
        "seller_state": [f"st{s % 5}" for s in sellers],
        "purchase_ts": week + pd.Timedelta(hours=10),
        "review_created_before_delivery": pd.array(np.zeros(n, dtype=bool), dtype="boolean"),
        "n_reviews": 1,
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


def test_analysis_frame_multi_seller_option():
    t = make_orders(n=12)
    t.loc[2, "distance_km"] = np.nan  # a headline order with missing distance
    for i in (3, 4):  # excluded only for having several sellers (ADR-0011 §3, check 7)
        t.loc[i, ["in_headline", "exclusion_reason", "seller_id", "seller_state", "distance_km"]] = \
            [False, "multi_seller", None, None, np.nan]
    t.loc[5, ["in_headline", "exclusion_reason"]] = [False, "outside_window"]
    base = analysis_frame(t)
    multi = analysis_frame(t, include_multi_seller=True)
    assert len(base) == 9 and len(multi) == 11
    m = multi.set_index("order_id")
    assert "o000005" not in m.index
    for oid in ("o000003", "o000004"):
        assert m.loc[oid, "seller_id"] == C.MULTI_SELLER_LABEL == m.loc[oid, "seller_state"]
        assert m.loc[oid, "distance_missing"] == 1.0
        assert m.loc[oid, "distance_km"] == m.loc["o000002", "distance_km"]  # same median fill as headline rows
    assert multi[multi["seller_id"] != C.MULTI_SELLER_LABEL].reset_index(drop=True).equals(base)


def test_analysis_frame_pass_through_columns():
    t = make_orders(n=4)
    t.loc[1, "n_reviews"] = 2
    t.loc[2, "review_created_before_delivery"] = True
    t.loc[3, "review_created_before_delivery"] = pd.NA
    f = analysis_frame(t)
    assert (f["purchase_date"] == t["purchase_ts"].dt.normalize()).all()
    assert f["n_reviews"].tolist() == [1.0, 2.0, 1.0, 1.0]
    assert f["review_created_before_delivery"].iloc[:3].tolist() == [0.0, 0.0, 1.0]
    assert np.isnan(f["review_created_before_delivery"].iloc[3])
    assert f["seller_state"].tolist() == t["seller_state"].tolist()


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


def test_rd_sample_placebo_windows():
    days = np.arange(-20, 21, dtype=float)
    f = pd.DataFrame({"days_late": np.repeat(days, 2), "has_review": True})
    (left_c, left_donut), (right_c, right_donut) = C.PLACEBO_CUTOFFS
    left = rd.rd_sample(f, C.RD_BANDWIDTH, True, cutoff=left_c, donut_days=left_donut)
    right = rd.rd_sample(f, C.RD_BANDWIDTH, True, cutoff=right_c, donut_days=right_donut)
    assert sorted(set(left["days_late"])) == [d for d in range(-13, 1) if d not in (-7, -6)]
    assert sorted(set(right["days_late"])) == [d for d in range(1, 15) if d not in (7, 8)]


def test_rd_estimate_covariate_outcome():
    f = rd_frame(n=100_000, jump=0.0, seed=11)
    rng = np.random.default_rng(12)
    f["log_price"] = 1.0 + 0.01 * f["days_late"] + 0.30 * (f["days_late"] >= 1) + rng.normal(0, 0.5, len(f))
    d = rd.rd_sample(f, C.RD_BANDWIDTH, True)
    e = rd.estimate(d, C.RD_BANDWIDTH, True, outcome="log_price")
    assert e["ci95_low"] <= 0.30 <= e["ci95_high"] and abs(e["estimate"] - 0.30) < 0.02
    with pytest.raises(ValueError, match="log_freight missing"):
        rd.estimate(d.assign(log_freight=np.nan), C.RD_BANDWIDTH, True, outcome="log_freight")


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


def _est(e, half=0.01, lo=None, hi=None):
    return {"estimate": e, "ci95_low": e - half if lo is None else lo, "ci95_high": e + half if hi is None else hi}


def ladder_inputs(rd_est=0.515, match_est=0.52, smd=0.05, b12=0.15, b37=0.50, r90=-0.002, r180=-0.003,
                  low=(0.50, 0.53), star5=(-0.44, -0.41)):
    """Synthetic result dicts shaped like naive/fe/rd/matching.json; headline CI = [0.50, 0.53]."""
    naive = {"outcomes": [{"outcome": "low_review (primary)", "difference": 0.54, "ci95_low": 0.53, "ci95_high": 0.55,
                           "n_late": 10, "n_on_time": 90}]}
    fe = {"primary": {**_est(0.515, lo=0.50, hi=0.53), "n_obs": 100},
          "models": [
              {"id": "low_review/a", "estimates": [{"term": "late", **_est(sum(low) / 2, lo=low[0], hi=low[1])}]},
              {"id": "low_review/b", "estimates": [{"term": "late_1_2", **_est(b12)}, {"term": "late_3_7", **_est(b37)}]},
              {"id": "repeat_90d/a", "estimates": [{"term": "late", **_est(r90, 0.003)}]},
              {"id": "repeat_180d/a", "estimates": [{"term": "late", **_est(r180, 0.003)}]},
              {"id": "star_5/a", "estimates": [{"term": "late", **_est(sum(star5) / 2, lo=star5[0], hi=star5[1])}]},
          ]}
    rd_row = {"days_left": [-6, -1], "days_right": [2, 7], "n_left": 5, "n_right": 5}
    rd = {"estimates": [
        {**rd_row, **_est(rd_est, 0.1), "spec": "main", "role": "corroborating (ADR-0007 §3)", "dropped_days": [0, 1]},
        {**rd_row, **_est(0.0, 0.1), "spec": "h = 5.5", "role": "sensitivity", "dropped_days": [0, 1]},
    ]}
    matching_ = {"att": _est(match_est), "sample": {"matched_late": 10}, "balance": {"max_abs_smd_after": smd}}
    return {"naive": naive, "fe": fe, "rd": rd, "matching": matching_}


def _fired(result):
    return {f["flag"] for f in result["flags"] if f["fired"]}


def test_ladder_converge_branch_and_roles():
    r = ladder.build(**ladder_inputs())
    assert r["reconciliation"]["verdicts"] == {"Donut RD": "converges", "Matching": "converges"}
    assert not r["reconciliation"]["headline_fragile"] and _fired(r) == set()
    assert r["reconciliation"]["headline"]["method"] == "FE regression"
    no_verdict = {x["method"] for x in r["rows"] if x["verdict"] == ""}
    assert no_verdict == {"Naive difference", "FE regression", "Donut RD (h = 5.5)"}
    edge = ladder.build(**ladder_inputs(rd_est=0.50, match_est=0.53))  # CI bounds count as inside
    assert set(edge["reconciliation"]["verdicts"].values()) == {"converges"}


def test_ladder_diverge_and_fragile_branches():
    one = ladder.build(**ladder_inputs(rd_est=0.11))
    assert one["reconciliation"]["verdicts"]["Donut RD"] == "diverges (below)"
    assert not one["reconciliation"]["headline_fragile"]
    both_below = ladder.build(**ladder_inputs(rd_est=0.11, match_est=0.40))
    assert both_below["reconciliation"]["headline_fragile"]
    opposite = ladder.build(**ladder_inputs(rd_est=0.11, match_est=0.60))
    assert opposite["reconciliation"]["verdicts"]["Matching"] == "diverges (above)"
    assert not opposite["reconciliation"]["headline_fragile"]


def test_ladder_flags_fire():
    r = ladder.build(**ladder_inputs(smd=0.12, b12=0.60, b37=0.50, r90=-0.002, r180=0.001,
                                     low=(-0.01, 0.02), star5=(-0.10, -0.05)))
    assert _fired(r) == {"balance", "bin order", "repeat window", "star distribution"}
    edge = ladder.build(**ladder_inputs(smd=0.1, b12=0.5, b37=0.5))  # strict inequalities
    assert _fired(edge) == set()


# Reference values copied from the sensemakr R package, v0.1.6 (master; DESCRIPTION Date 2024-07-22),
# tests/testthat/test-02-darfur.R, read 2026-11-16:
# https://raw.githubusercontent.com/carloscinelli/sensemakr/master/tests/testthat/test-02-darfur.R
# Model: lm(peacefactor ~ directlyharmed + age + farmer_dar + herder_dar + pastvoted + hhsize_darfur
#           + female + village, data = darfur). Lines checked with tolerance = 1e5 (a typo there) are not used.
DARFUR = {"estimate": 0.09731582, "se": 0.02325654, "dof": 783,
          "r2yd_x": 0.02187309, "rv_q": 0.138776, "rv_qa": 0.07625797}
DARFUR_FEMALE_BOUNDS = {  # `check_bounds` in the same file: benchmark female, kd = ky = 1, 2, 3
    "r2dz_x": (0.00916428667504862, 0.0183285733500972, 0.0274928600251459),
    "r2yz_dx": (0.12464092303637, 0.249324064199975, 0.374050471038094),
    "adjusted_estimate": (0.0752202712144491, 0.0529151723844518, 0.0303960234641548),
    "adjusted_se": (0.0218733277437572, 0.0203500620779637, 0.0186700648170924),
    "adjusted_t": (3.43890386024675, 2.60024623913809, 1.62806202131271),
    "ci95_low": (0.032282966, 0.012968035, -0.006253282),
    "ci95_high": (0.11815758, 0.09286231, 0.06704533),
}


def test_sensitivity_darfur_stats():
    t = DARFUR["estimate"] / DARFUR["se"]
    assert R.partial_r2(t, DARFUR["dof"]) == pytest.approx(DARFUR["r2yd_x"], abs=1e-5)
    assert R.robustness_value(t, DARFUR["dof"]) == pytest.approx(DARFUR["rv_q"], abs=1e-5)
    assert R.robustness_value(t, DARFUR["dof"], alpha=0.05) == pytest.approx(DARFUR["rv_qa"], abs=1e-5)


def test_sensitivity_darfur_female_bounds():
    """The file does not state female's partial R² values, so they are recovered from its 1x bound.

    Inverting the 1x row pins r2dxj_x and r2yxj_dx; the 2x and 3x rows and every adjusted estimate,
    SE, t and CI are then independent checks of the bound, bias and SE formulas.
    """
    b = DARFUR_FEMALE_BOUNDS
    r2dxj_x = b["r2dz_x"][0] / (1 + b["r2dz_x"][0])
    r2zxj_xd = r2dxj_x**2 / (1 - r2dxj_x) ** 2
    g = b["r2yz_dx"][0] / ((1 + np.sqrt(r2zxj_xd)) ** 2 / (1 - r2zxj_xd))
    r2yxj_dx = g / (1 + g)
    crit = R.student_t.ppf(0.975, DARFUR["dof"] - 1)
    rows = R.confounder_bounds(DARFUR["estimate"], DARFUR["se"], DARFUR["se"], crit, DARFUR["dof"], r2dxj_x, r2yxj_dx)
    assert [r["k"] for r in rows] == [1, 2, 3]
    for key, want in b.items():
        assert [r[key] for r in rows] == pytest.approx(list(want), abs=1e-6), key


def test_fit_iid_matches_statsmodels_and_group_partial_r2():
    import statsmodels.formula.api as smf
    from patsy.builtins import C  # noqa: F401  formulas below need patsy's C(), not this module's `config as C`

    t = make_orders(n=3_000, seed=21)
    t.loc[:40, "distance_km"] = np.nan  # give distance_missing variation, as on real data
    f = analysis_frame(t)
    full = R.fit_iid(f, "low_review", ["late"])
    assert full["n_obs"] == len(f)  # no singletons in this design
    fe_terms = "C(seller_id) + C(purchase_week)"
    sm_full = smf.ols(f"low_review ~ late + {CONTROLS} + {fe_terms}", data=f).fit()
    assert full["dof"] == sm_full.df_resid
    assert full["terms"]["late"]["t"] == pytest.approx(sm_full.tvalues["late"], rel=1e-6)
    # Single regressor: RSS-based partial R² equals t²/(t² + df).
    no_d = R.fit_iid(f, "low_review", [])
    t_late = full["terms"]["late"]["t"]
    assert R.group_partial_r2(no_d["rss"], full["rss"]) == pytest.approx(R.partial_r2(t_late, full["dof"]), abs=1e-8)
    # Group: RSS-based partial R² equals the F-test form F*q / (F*q + df).
    no_state = R.fit_iid(f, "low_review", ["late"], drop=("customer_state",))
    sm_r = smf.ols(f"low_review ~ late + {CONTROLS.replace('C(customer_state) + ', '')} + {fe_terms}", data=f).fit()
    F, _, q = sm_full.compare_f_test(sm_r)
    assert R.group_partial_r2(no_state["rss"], full["rss"]) == pytest.approx(F * q / (F * q + sm_full.df_resid), abs=1e-8)


def test_sensitivity_guards():
    assert R.robustness_value(1.0, 100, alpha=0.05) == 0.0  # not significant: RV is 0
    with pytest.raises(ValueError, match="impossible"):
        R.ovb_partial_r2_bound(0.5, 0.1, kd=2)
    with pytest.raises(ValueError, match="out of order"):
        R.group_partial_r2(1.0, 2.0)
    with pytest.raises(ValueError, match="not a control"):
        R.fit_iid(analysis_frame(make_orders(n=50)), "low_review", ["late"], drop=("seller_id",))
