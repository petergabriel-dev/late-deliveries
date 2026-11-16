"""Phase 4 money translation (ADR-0013) on synthetic data and hand-computed answers.

No real-data money figure is computed here. The repo's assumptions.toml is loaded only to check
that it validates and to feed the end-to-end run's assumed inputs.
"""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from late_delivery import config as C
from late_delivery import money as M
from late_delivery import robustness as R
from late_delivery.fe import LATE_BIN_COLS, analysis_frame, fit
from test_estimators import phase3_orders

A = M.load_assumptions()
PARQUET_COLS = ["repeat_90d_gmv", "repeat_180d_gmv", "seller_id", "purchase_ts", "order_status", "price",
                "review_answer_ts", "in_headline", "late", "days_late", "review_score"]


def _est(term, e, lo, hi):
    return {"term": term, "estimate": e, "ci95_low": lo, "ci95_high": hi}


def fe_stub(headline=(0.52, 0.50, 0.53)) -> dict:
    """fe.json-shaped dict with every model the assumptions file refers to."""
    stars = [_est(b, -x, -x - 0.1, -x + 0.1) for b, x in zip(LATE_BIN_COLS, (0.5, 2.0, 2.5, 2.4))]
    lows = [_est(b, x, x - 0.02, x + 0.02) for b, x in zip(LATE_BIN_COLS, (0.15, 0.5, 0.7, 0.65))]
    return {"primary": dict(zip(("estimate", "ci95_low", "ci95_high"), headline)),
            "models": [{"id": "repeat_90d/a", "estimates": [_est("late", -0.002, -0.005, 0.001)]},
                       {"id": "repeat_180d/a", "estimates": [_est("late", -0.003, -0.008, 0.002)]},
                       {"id": "review_score/b", "estimates": stars},
                       {"id": "low_review/b", "estimates": lows},
                       {"id": "low_review/c", "estimates": [_est("late", 0.43, 0.41, 0.45),
                                                            _est("delivery_days", 0.004, 0.0035, 0.0047)]}]}


# --- Assumptions file ------------------------------------------------------------------------------

def test_repo_assumptions_validate():
    assert len(A["fx"]["monthly"]) == 20 == M.window_months()
    assert M.fx_rate(A) == pytest.approx(sum(A["fx"]["monthly"].values()) / 20)
    assert A["inputs"]["horizon_days"]["illustrative"] and not A["inputs"]["epsilon"].get("illustrative")


@pytest.mark.parametrize("change, match", [
    (lambda a: a["inputs"]["epsilon"].pop("unit"), "missing field"),
    (lambda a: a["inputs"]["epsilon"].update(low=0.2), "low <= value <= high"),
    (lambda a: a["inputs"]["epsilon"].update(high=0.01), "low <= value <= high"),
    (lambda a: a["inputs"]["epsilon"].update(value=float("nan")), "finite numbers"),
    (lambda a: a["inputs"]["epsilon"].pop("sources"), "source or illustrative"),
    (lambda a: a["inputs"]["horizon_days"].update(illustrative=False), "source or illustrative"),
    (lambda a: a["inputs"]["take_rate"]["sources"][0].pop("quote"), "lacks"),
    (lambda a: a["inputs"]["star_drop_bins"].update(value=-2.0), "must not copy numbers"),
    (lambda a: a["inputs"]["late_mix"].pop("ref"), "needs a ref"),
    (lambda a: a["inputs"]["epsilon"].update(tag="guess"), "tag must be"),
    (lambda a: a["inputs"].pop("take_rate"), "missing inputs"),
    (lambda a: a["fx"]["monthly"].update({"2017-01": 0}), "fx.monthly"),
])
def test_loader_guards(change, match):
    a = copy.deepcopy(A)
    change(a)
    with pytest.raises(ValueError, match=match):
        M.validate_assumptions(a)


def test_resolve_measured_refs():
    m = M.resolve_measured(A, fe_stub(), PARQUET_COLS)
    assert list(m["star_drop_bins"]) == LATE_BIN_COLS and m["broken_promise"]["delivery_days"]["estimate"] == 0.004
    fe = fe_stub()
    fe["models"] = [x for x in fe["models"] if x["id"] != "low_review/c"]
    with pytest.raises(ValueError, match="no model low_review/c"):
        M.resolve_measured(A, fe, PARQUET_COLS)
    fe = fe_stub()
    fe["models"][2]["estimates"] = fe["models"][2]["estimates"][:3]
    with pytest.raises(ValueError, match="late_15p"):
        M.resolve_measured(A, fe, PARQUET_COLS)
    with pytest.raises(ValueError, match="lacks"):
        M.resolve_measured(A, fe_stub(), [c for c in PARQUET_COLS if c != "review_answer_ts"])


def test_harm_ends_clamp_at_zero():
    assert M.harm_ends(_est("late", -0.002404, -0.004878, 0.000071)) == {"low": 0.0, "central": 0.002404, "high": 0.004878}
    assert M.harm_ends(_est("late", 0.01, 0.005, 0.02)) == {"low": 0.0, "central": 0.0, "high": 0.0}


def test_bin_edges():
    d = pd.Series([0, 1, 2, 3, 7, 8, 14, 15, 40, None], dtype="Int64")
    assert M.bin_of(d).tolist() == [pd.NA, "late_1_2", "late_1_2", "late_3_7", "late_3_7", "late_8_14", "late_8_14",
                                    "late_15p", "late_15p", pd.NA]


# --- Channel 2 exposure, by hand ------------------------------------------------------------------------

def exposure_table() -> pd.DataFrame:
    """Two sellers. Late: i1 (A, 5 days), i2 (B, 1 day), i3 (B, 10 days, late in the data), i4 (B, no review)."""
    rows = [  # order_id, seller, status, purchase, price, answered, days_late, score
        ("i1", "A", "delivered", "2017-01-01", 10.0, "2017-01-10", 5, 1),
        ("i2", "B", "delivered", "2017-02-01", 15.0, "2017-02-15 10:00", 1, 2),
        ("i3", "B", "delivered", "2018-06-01", 25.0, "2018-07-01", 10, 1),
        ("i4", "B", "delivered", "2017-01-15", 35.0, None, 20, None),  # bought before i2's review: not exposed
        ("a2", "A", "delivered", "2017-01-05", 20.0, "2017-01-08", -2, 5),
        ("a3", "A", "delivered", "2017-01-20", 100.0, "2017-01-25", -1, 4),
        ("a4", "A", "canceled", "2017-02-01", 500.0, None, None, None),
        ("a5", "A", "delivered", "2017-03-15", 90.0, "2017-03-20", 0, 5),
        ("a6", "A", "delivered", "2017-04-20", 1000.0, None, -3, None),
        ("b1", "B", "delivered", "2017-02-15 10:00", 700.0, "2017-02-25", -1, 5),
        ("b2", "B", "delivered", "2017-02-20", 40.0, None, -2, None),
        ("b3", "B", "delivered", "2018-07-15", 60.0, None, -2, None),
    ]
    t = pd.DataFrame(rows, columns=["order_id", "seller_id", "order_status", "purchase_ts", "price",
                                    "review_answer_ts", "days_late", "review_score"])
    t["purchase_ts"] = pd.to_datetime(t["purchase_ts"], format="ISO8601")
    t["review_answer_ts"] = pd.to_datetime(t["review_answer_ts"], format="ISO8601")
    t["days_late"] = t["days_late"].astype("Int64")
    t["review_score"] = t["review_score"].astype("Int64")
    t["late"] = t["days_late"] > 0
    t["in_headline"] = t["order_status"].eq("delivered")
    return t


def test_seller_exposure_hand_computed():
    t = exposure_table()
    L = M.late_orders(t)
    hist = M.seller_history(t)
    x90 = M.seller_exposure(hist, L, 90).set_index("order_id")
    assert list(x90.index) == ["i1", "i2", "i3"]  # i4 has no review
    # i1, window (01-10, 04-10]: a3 sees 2 reviews (a2, i1), a5 sees 3; canceled a4 and a6 (after H) are out.
    assert x90.loc["i1", "exposure"] == pytest.approx(100 / 2 + 90 / 3) and x90.loc["i1", "min_n"] == 2
    # i2: b1 was bought at the answer time (not after it); b2 sees only i2's review (b1's comes later).
    assert x90.loc["i2", "exposure"] == pytest.approx(40 / 1) and x90.loc["i2", "min_n"] == 1
    assert not x90.loc["i3", "eligible"] and np.isnan(x90.loc["i3", "exposure"])  # 07-01 + 90 > 2018-08-31
    x30 = M.seller_exposure(hist, L, 30).set_index("order_id")
    assert x30.loc["i1", "exposure"] == pytest.approx(50.0)
    assert x30.loc["i3", "eligible"] and x30.loc["i3", "exposure"] == pytest.approx(60 / 3)  # b3 sees i2, b1, i3
    mix = M.late_mix(L)
    assert (mix["late_orders"], mix["late_with_review"], mix["review_share"]) == (4, 3, 0.75)
    assert mix["counts"] == {"late_1_2": 1, "late_3_7": 1, "late_8_14": 1, "late_15p": 0}
    with pytest.raises(ValueError, match="no eligible late order in bin late_8_14"):  # i3 is past the data end
        M.bin_exposure(x90)


def test_exposure_guards():
    t = exposure_table()
    t.loc[t["order_id"] == "a3", "price"] = np.nan
    with pytest.raises(ValueError, match="no item price"):
        M.seller_history(t)
    t = exposure_table()
    with pytest.raises(ValueError, match="outside every days-late bin"):
        M.late_orders(t, ["a2"])  # on time


def test_repeat_value():
    t = pd.DataFrame({"in_headline": [True, True, True, False], "is_first_order": [True, True, True, True],
                      "repeat_90d_eligible": [True, True, False, True],
                      "repeat_90d": pd.array([True, False, True, True], dtype="boolean"),
                      "repeat_90d_gmv": pd.array([80.0, 0.0, 999.0, 999.0], dtype="Float64")})
    assert M.repeat_value(t, 90) == (80.0, 1)  # ineligible and non-headline repeaters are left out


# --- Cases, corners, tornado, flags ---------------------------------------------------------------

def toy_data() -> dict:
    return {"exposure": {H: {b: v for b in LATE_BIN_COLS} for H, v in ((30, 10.0), (90, 20.0), (180, 30.0))},
            "mix": dict.fromkeys(LATE_BIN_COLS, 0.25), "review_share": 0.8}


def test_money_case_arithmetic():
    p = {"epsilon": 0.1, "take_rate": 0.2, "horizon_days": 90, "star_drop": dict.fromkeys(LATE_BIN_COLS, 2.0),
         "repeat_effect": 0.002, "repeat_value": 150.0}
    r = M.money_case(p, toy_data())
    assert r["channel1_gmv"] == pytest.approx(0.3)
    assert r["channel2_gmv"] == pytest.approx(0.1 * (4 * 0.25 * 2.0 * 20.0) * 0.8)  # 3.2
    assert r["total_revenue"] == pytest.approx(0.2 * 3.5) and r["channel1_revenue"] == pytest.approx(0.06)


def test_corners_and_tornado():
    m = M.resolve_measured(A, fe_stub(), PARQUET_COLS)
    cases = M.case_params(A, m["star_drop_bins"], m["repeat_effect_90d"]["late"], 150.0)
    assert [cases[e]["horizon_days"] for e in M.ENDS] == [30, 90, 180]
    assert [cases[e]["repeat_effect"] for e in M.ENDS] == [0.0, 0.002, 0.005]  # CI crosses 0: low end clamps
    data = toy_data()
    rev = [M.money_case(cases[e], data)["total_revenue"] for e in M.ENDS]
    assert rev[0] < rev[1] < rev[2]
    moved = ("epsilon", "horizon_days", "take_rate", "star_drop", "repeat_effect")
    for end in ("low", "high"):  # moving every row together gives the corner
        assert {**cases["central"], **{k: cases[end][k] for k in moved}} == cases[end]
    rows = M.tornado(A, cases, data, m["repeat_effect_180d"]["late"], 120.0)
    assert [r["swing"] for r in rows] == sorted((r["swing"] for r in rows), reverse=True)
    by = {r["input"]: r for r in rows}
    assert set(by) == {"epsilon", "horizon_days", "take_rate", "star_drop_bins", "repeat_effect_90d", "repeat_window_180d"}
    assert by["take_rate"]["swing"] == 0.0  # 0.20 fixed
    assert by["horizon_days"]["illustrative"] and not by["epsilon"]["illustrative"]
    for r in rows:
        if r["input"] != "repeat_window_180d":  # the 180-day row swaps the value too, so it need not bracket
            assert r["low_revenue"] <= rev[1] <= r["high_revenue"]


def test_flag_rules_fire_and_hold():
    c = lambda ch1, total: {"channel1_revenue": ch1, "total_revenue": total}  # noqa: E731
    assert M.flag1(c(0.099, 1.0))["fired"] and not M.flag1(c(0.10, 1.0))["fired"]
    with pytest.raises(ValueError, match="not positive"):
        M.flag1(c(0.0, 0.0))
    row = lambda name, swing, ill: {"input": name, "swing": swing, "illustrative": ill}  # noqa: E731
    assert M.flag2([row("horizon_days", 2.0, True), row("epsilon", 1.0, False)])["fired"]
    assert not M.flag2([row("horizon_days", 1.0, True), row("epsilon", 2.0, False)])["fired"]
    assert M.flag2([row("horizon_days", 2.0, True), row("epsilon", 2.0, False)])["fired"]  # a tie with an illustrative input
    assert not M.flag3(1.0, 1.0, 2.0)["fired"] and not M.flag3(2.0, 1.0, 2.0)["fired"]
    assert M.flag3(0.999, 1.0, 2.0)["fired"] and M.flag3(2.001, 1.0, 2.0)["fired"]


def test_loss_fraction_guard():
    cases = {e: {"epsilon": 0.5, "star_drop": {"late_1_2": 3.0}} for e in M.ENDS}
    with pytest.raises(ValueError, match="exceeds 1"):
        M.guard_loss_fraction(cases, 1.0)
    assert M.guard_loss_fraction(cases, 2.0) == 0.75 and M.guard_loss_fraction(cases, float("nan")) == 0.0


def test_mix_decomposition():
    bins = {b: {"estimate": x} for b, x in zip(LATE_BIN_COLS, (0.2, 0.6, 0.7, 0.7))}
    d = M.mix_decomposition(dict(zip(LATE_BIN_COLS, (0.5, 0.5, 0, 0))), dict(zip(LATE_BIN_COLS, (1, 0, 0, 0))),
                            bins, headline=0.5, scenario=0.25)
    assert d["headline_mix_weighted"] == pytest.approx(0.4) and d["check10_mix_weighted"] == pytest.approx(0.2)
    assert d["predicted_drop"] == pytest.approx(0.2) and d["observed_drop"] == pytest.approx(0.25)
    assert d["explained_share"] == pytest.approx(0.8)


# --- End to end on synthetic data ----------------------------------------------------------------------

def money_orders(n: int = 20_000) -> pd.DataFrame:
    """phase3_orders plus the Phase 4 build columns: status, review answer times, repeat GMV."""
    t = phase3_orders(n=n)
    rng = np.random.default_rng(5)
    t["order_status"] = "delivered"
    has = t["review_score"].notna()
    t["review_answer_ts"] = (t["purchase_ts"] + pd.to_timedelta(t["delivery_days"] + 2, unit="D")).where(has)
    for w in C.REPEAT_WINDOWS:
        repeat = t[f"repeat_{w}d"].to_numpy(dtype=bool)
        t[f"repeat_{w}d_gmv"] = pd.array(np.where(repeat, rng.uniform(20, 200, n), 0.0), dtype="Float64")
    return t


def test_build_end_to_end_synthetic(tmp_path):
    t = money_orders()
    f = analysis_frame(t)
    h = fit(f[f["has_review"]], "low_review", ["late"])["estimates"][0]
    fe = fe_stub(headline=(h["estimate"], h["ci95_low"], h["ci95_high"]))
    frames = R.check_frames(t)
    d = M.build(t, fe, A)
    rate = d["fx"]["brl_per_usd"]
    rev = [d["cases"][e]["brl"]["total_revenue"] for e in M.ENDS]
    assert rev[0] <= rev[1] <= rev[2]
    assert d["cases"]["central"]["usd"]["total_revenue"] == pytest.approx(rev[1] / rate)
    assert d["channel3_addon"]["central"]["brl"] == pytest.approx(1.0 * 6.32)
    assert [f["id"] for f in d["flags"]] == [1, 2, 3] and all(isinstance(f["fired"], bool) for f in d["flags"])
    assert d["flags_fired"] == [f["id"] for f in d["flags"] if f["fired"]]
    assert len(d["tornado"]) == 6 and list(d["exposure"]) == ["30", "90", "180"]
    for b in LATE_BIN_COLS:  # a longer horizon leaves fewer late orders inside the data
        assert d["exposure"]["30"]["eligible"][b] >= d["exposure"]["90"]["eligible"][b] >= d["exposure"]["180"]["eligible"][b]
    assert 0 < d["max_loss_fraction"] <= 1
    # Scenario: check-10 sample, its own late orders, and model (a) equal to robustness check 10.
    s = d["scenario"]
    assert s["late_orders"]["late_orders"] == int(frames[10]["late"].sum()) < d["late_orders"]["late_orders"]
    c10 = R.fe_check(frames[10], 0)
    assert s["fits"]["low_review/a"]["estimate"] == pytest.approx(c10["estimate"], abs=1e-12)
    assert d["mix_decomposition"]["observed_drop"] == pytest.approx(h["estimate"] - c10["estimate"])
    assert d["recommendation"]["broken_promise_equivalent_days"] == pytest.approx(0.43 / 0.004)
    be = d["recommendation"]["break_even_per_late_delivery"]
    assert [be[e]["brl"] for e in M.ENDS] == rev
    a = d["annual_illustration"]
    assert a["central_revenue_brl"] == pytest.approx(rev[1] * a["late_orders"] / 20 * 12)
    assert d["inputs"]["horizon_days"]["status"] == "illustrative" and d["inputs"]["epsilon"]["status"] == "sourced"
    # Report, JSON and figure render from the same rounded result.
    r = M.rounded(d)
    assert json.loads(json.dumps(r)) == r
    md = M.to_markdown(r)
    assert md.count("\n| ") > 30 and f"{r['cases']['central']['brl']['total_revenue']:,.2f}" in md
    assert all(f"| {f['id']} |" in md for f in r["flags"])
    M.plot(r, tmp_path / "fig.png")
    assert (tmp_path / "fig.png").stat().st_size > 0
