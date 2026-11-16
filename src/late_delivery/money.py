"""Phase 4 money translation: what one late delivery costs (ADR-0006, ADR-0013).

Per late headline order, in BRL (USD alongside):

- Channel 1, lost repeat purchases (measured, upper bound): |repeat_90d effect| x mean repeat GMV.
- Channel 2, rating spillover (epsilon assumed, the rest measured):
  epsilon x sum_b w_b |beta_b| E_b(H) x r, where E_b(H) is the mean over eligible late orders in
  bin b of sum_j price_j / N_j over the seller's later orders j in (review answer, answer + H].
- Channel 3, operating costs: contacts x cost per contact, an illustrative add-on line only.

Platform revenue = lost GMV x take rate (channels 1-2). Range = every input at its low-cost end to
every input at its high-cost end; tornado one row at a time; flags by the ADR-0013 §6 rules. The
disruption scenario re-fits the bin effects on the check-10 sample (ADR-0013 §7).

Inputs come only from assumptions.toml and code output (fe.json, orders.parquet): invariant 6.
The Phase 3 masks are reused from robustness.py, never copied.

Writes outputs/money.json, outputs/money.md and outputs/fig_money_tornado.png (`make money`).
"""

import json
import math
import tomllib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from late_delivery import config as C  # noqa: E402
from late_delivery.diagnostics import GRID, INK, INK_2, SERIES, SURFACE, _style, md_table, rounded  # noqa: E402
from late_delivery.fe import LATE_BIN_COLS, fit  # noqa: E402
from late_delivery.robustness import check_frames, headline_from  # noqa: E402

ENDS = ("low", "central", "high")
ASSUMED_INPUTS = ("epsilon", "take_rate", "horizon_days", "contacts_per_late_order", "cost_per_contact")
MEASURED_INPUTS = ("repeat_effect_90d", "repeat_effect_180d", "star_drop_bins", "low_review_bins", "broken_promise",
                   "repeat_gmv_90d", "repeat_gmv_180d", "seller_exposure", "late_mix")
ASSUMED_FIELDS = ("description", "unit", "value", "low", "high")
SOURCE_FIELDS = ("citation", "url", "quote", "opened")


# --- Assumptions file (ADR-0013 §8) ----------------------------------------------------------------

def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate_assumptions(a: dict) -> dict:
    """Raise on any input that breaks the assumptions-file rules; return `a` unchanged."""
    inputs = a.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("assumptions: no [inputs] table")
    missing = [k for k in (*ASSUMED_INPUTS, *MEASURED_INPUTS) if k not in inputs]
    if missing:
        raise ValueError(f"assumptions: missing inputs {missing}")
    for name, v in inputs.items():
        tag = v.get("tag")
        if tag == "assumed":
            absent = [f for f in ASSUMED_FIELDS if f not in v]
            if absent:
                raise ValueError(f"{name}: missing field(s) {absent}")
            lo, val, hi = v["low"], v["value"], v["high"]
            if not all(_number(x) for x in (lo, val, hi)):
                raise ValueError(f"{name}: low, value and high must be finite numbers")
            if not lo <= val <= hi:
                raise ValueError(f"{name}: needs low <= value <= high, got {lo}, {val}, {hi}")
            sources = v.get("sources", [])
            for s in sources:
                gaps = [f for f in SOURCE_FIELDS if not s.get(f)]
                if gaps:
                    raise ValueError(f"{name}: a source lacks {gaps}")
            if not sources and v.get("illustrative") is not True:
                raise ValueError(f"{name}: an assumed input needs a source or illustrative = true")
        elif tag == "measured":
            if not v.get("ref"):
                raise ValueError(f"{name}: a measured input needs a ref")
            copied = [f for f in ("value", "low", "high") if f in v]
            if copied:
                raise ValueError(f"{name}: a measured input must not copy numbers {copied}; they come from its ref")
        else:
            raise ValueError(f"{name}: tag must be 'assumed' or 'measured', got {tag!r}")
    monthly = a.get("fx", {}).get("monthly")
    if not monthly or not all(_number(x) and x > 0 for x in monthly.values()):
        raise ValueError("assumptions: [fx.monthly] needs positive monthly rates")
    return a


def load_assumptions(path=C.ASSUMPTIONS_TOML) -> dict:
    with open(path, "rb") as fh:
        return validate_assumptions(tomllib.load(fh))


def resolve_measured(a: dict, fe_json: dict, columns) -> dict[str, dict[str, dict]]:
    """Check that every measured ref resolves; return fe.json estimates by input name, then term."""
    models = {m["id"]: m for m in fe_json.get("models", [])}
    cols, out = set(columns), {}
    for name, v in a["inputs"].items():
        if v["tag"] != "measured":
            continue
        source, _, target = v["ref"].partition(":")
        if source == "fe.json":
            if target not in models:
                raise ValueError(f"{name}: fe.json has no model {target}")
            est = {e["term"]: e for e in models[target]["estimates"]}
            terms = v.get("terms", [])
            absent = [x for x in terms if x not in est]
            if not terms or absent:
                raise ValueError(f"{name}: terms {absent or 'none listed'} not in fe.json {target}")
            out[name] = {x: est[x] for x in terms}
        elif source == "orders.parquet":
            absent = [c for c in target.split(",") if c not in cols]
            if absent:
                raise ValueError(f"{name}: orders.parquet lacks {absent}")
        else:
            raise ValueError(f"{name}: unknown ref source {source!r}")
    return out


def harm_ends(e: dict) -> dict:
    """Cost ends of a harmful (negative) effect from its 95% CI, clamped at 0 (ADR-0013 §2-3)."""
    return {"low": max(0.0, -e["ci95_high"]), "central": max(0.0, -e["estimate"]), "high": max(0.0, -e["ci95_low"])}


def assumed_ends(v: dict) -> dict:
    return {"low": v["low"], "central": v["value"], "high": v["high"]}


def inputs_echo(a: dict) -> dict:
    """Every input as the JSON reports it: assumed values with status and citations, measured refs."""
    out = {}
    for name, v in a["inputs"].items():
        if v["tag"] == "assumed":
            out[name] = {"tag": "assumed", "status": "illustrative" if v.get("illustrative") else "sourced",
                         "unit": v["unit"], "low": v["low"], "value": v["value"], "high": v["high"],
                         "sources": [{"citation": s["citation"], "url": s["url"]} for s in v.get("sources", [])]}
        else:
            out[name] = {"tag": "measured", "ref": v["ref"], "terms": v.get("terms", [])}
    return out


def fx_rate(a: dict) -> float:
    """BRL per USD: simple mean of the monthly BCB PTAX averages (ADR-0013 §1)."""
    v = list(a["fx"]["monthly"].values())
    return sum(v) / len(v)


def window_months() -> int:
    return (C.WINDOW_END.year - C.WINDOW_START.year) * 12 + C.WINDOW_END.month - C.WINDOW_START.month


# --- Late orders, mix and channel 1 -------------------------------------------------------------------

def bin_of(days_late: pd.Series) -> pd.Series:
    """Days-late bin label (ADR-0008 §2) per order; missing outside every bin."""
    d = days_late.astype("float64")
    out = pd.Series(pd.NA, index=days_late.index, dtype="object")
    for col, (lo, hi) in zip(LATE_BIN_COLS, C.LATE_BINS):
        out[d.between(lo, np.inf if hi is None else hi)] = col
    return out


def late_orders(t: pd.DataFrame, order_ids=None) -> pd.DataFrame:
    """Late headline orders, or the given late order ids, with the columns the money code reads."""
    if order_ids is None:
        L = t[t["in_headline"].astype(bool) & t["late"].fillna(False).astype(bool)]
    else:
        L = t.set_index("order_id").loc[list(order_ids)].reset_index()
    L = L.assign(bin=bin_of(L["days_late"]), has_review=L["review_score"].notna().to_numpy())
    if L.empty or L["bin"].isna().any():
        raise ValueError("late orders: none given, or one falls outside every days-late bin")
    return L[["order_id", "seller_id", "bin", "has_review", "review_answer_ts"]].reset_index(drop=True)


def late_mix(L: pd.DataFrame) -> dict:
    """w_b over late orders with a review, and r = late orders with a review / all late (ADR-0013 §3)."""
    rev = L[L["has_review"]]
    if rev.empty:
        raise ValueError("no late order has a review")
    counts = rev["bin"].value_counts()
    return {"late_orders": len(L), "late_with_review": len(rev), "review_share": len(rev) / len(L),
            "counts": {b: int(counts.get(b, 0)) for b in LATE_BIN_COLS},
            "mix": {b: int(counts.get(b, 0)) / len(rev) for b in LATE_BIN_COLS}}


def repeat_value(t: pd.DataFrame, w: int) -> tuple[float, int]:
    """Mean repeat_{w}d_gmv over headline first orders eligible for w days that repeated (ADR-0013 §2)."""
    m = (t["in_headline"].astype(bool) & t["is_first_order"].astype(bool) & t[f"repeat_{w}d_eligible"].astype(bool)
         & t[f"repeat_{w}d"].fillna(False).astype(bool))
    if not m.any():
        raise ValueError(f"no eligible first order repeated within {w} days")
    return float(t.loc[m, f"repeat_{w}d_gmv"].astype(float).mean()), int(m.sum())


# --- Channel 2 exposure (ADR-0013 §3) ------------------------------------------------------------------

def _ns(s: pd.Series) -> np.ndarray:
    return s.to_numpy(dtype="datetime64[ns]")


def seller_history(t: pd.DataFrame) -> dict:
    """Per seller: later-order purchase times, visible review counts N_j and cumulative price / N_j.

    Later orders: single-seller orders whose status is not in LATER_ORDER_EXCLUDED_STATUSES. N_j counts
    the seller's single-seller orders (any status or window) whose review was answered before j's purchase.
    """
    s = t[t["seller_id"].notna()]
    answered = s[s["review_answer_ts"].notna()]
    answers = {k: np.sort(_ns(g["review_answer_ts"])) for k, g in answered.groupby("seller_id", sort=True)}
    pool = s[~s["order_status"].isin(C.LATER_ORDER_EXCLUDED_STATUSES)].sort_values(["seller_id", "purchase_ts", "order_id"])
    if not np.isfinite(pool["price"].to_numpy(dtype=float)).all():
        raise ValueError("a later order has no item price")
    none = np.array([], dtype="datetime64[ns]")
    hist = {}
    for k, g in pool.groupby("seller_id", sort=True):
        p = _ns(g["purchase_ts"])
        n = np.searchsorted(answers.get(k, none), p, side="left")  # answered strictly before the purchase
        w = np.where(n > 0, g["price"].to_numpy(dtype=float) / np.maximum(n, 1), 0.0)
        hist[k] = {"purchase": p, "n": n, "cum_w": np.concatenate([[0.0], np.cumsum(w)]),
                   "cum_unseen": np.concatenate([[0], np.cumsum(n == 0)])}
    return hist


def seller_exposure(hist: dict, L: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    """X_i(H) = sum_j price_j / N_j over the seller's later orders in (a_i, a_i + H], per late order with a review.

    Eligible: a_i + H < FOLLOWUP_END. Returns order_id, bin, eligible, exposure (NaN if not eligible)
    and min_n (smallest N_j in the window; NaN if not eligible or the window is empty).
    """
    R = L[L["has_review"]].reset_index(drop=True)
    if R["review_answer_ts"].isna().any():
        raise ValueError("a late order with a review has no review_answer_ts")
    eligible = (R["review_answer_ts"] + pd.Timedelta(days=horizon_days) < C.FOLLOWUP_END).to_numpy()
    a, h = _ns(R["review_answer_ts"]), np.timedelta64(int(horizon_days), "D")
    exposure, min_n = np.zeros(len(R)), np.full(len(R), np.nan)
    for k, idx in R.groupby("seller_id", sort=True).indices.items():
        g = hist.get(k)
        if g is None:
            continue  # the seller has no later orders at all
        lo = np.searchsorted(g["purchase"], a[idx], side="right")
        hi = np.searchsorted(g["purchase"], a[idx] + h, side="right")
        if (g["cum_unseen"][hi] - g["cum_unseen"][lo] > 0).any():
            raise ValueError(f"seller {k}: a later order inside a window sees no review (N_j = 0)")
        exposure[idx] = g["cum_w"][hi] - g["cum_w"][lo]
        nonempty = hi > lo
        min_n[idx[nonempty]] = g["n"][lo[nonempty]]  # N_j never falls as time passes
    exposure = np.where(eligible, exposure, np.nan)
    if not np.isfinite(exposure[eligible]).all():
        raise ValueError("non-finite seller exposure")
    return pd.DataFrame({"order_id": R["order_id"], "bin": R["bin"], "eligible": eligible,
                         "exposure": exposure, "min_n": np.where(eligible, min_n, np.nan)})


def bin_exposure(X: pd.DataFrame) -> tuple[dict, dict]:
    """E_b: mean exposure over eligible late orders per bin, and the eligible counts; empty bins raise."""
    e = X[X["eligible"]]
    means, counts = {}, {}
    for b in LATE_BIN_COLS:
        x = e.loc[e["bin"] == b, "exposure"]
        if x.empty:
            raise ValueError(f"no eligible late order in bin {b}")
        means[b], counts[b] = float(x.mean()), len(x)
    return means, counts


# --- Cases, range, tornado, flags (ADR-0013 §5-6) ----------------------------------------------------

def money_case(p: dict, data: dict) -> dict:
    """Lost GMV and platform revenue per late delivery for one set of inputs (channels 1-2)."""
    E = data["exposure"][int(p["horizon_days"])]
    spill = sum(data["mix"][b] * p["star_drop"][b] * E[b] for b in LATE_BIN_COLS)
    ch1 = p["repeat_effect"] * p["repeat_value"]
    ch2 = p["epsilon"] * spill * data["review_share"]
    take = p["take_rate"]
    return {"channel1_gmv": ch1, "channel2_gmv": ch2, "total_gmv": ch1 + ch2,
            "channel1_revenue": ch1 * take, "channel2_revenue": ch2 * take, "total_revenue": (ch1 + ch2) * take}


def case_params(a: dict, star_drop: dict, repeat_effect: dict, repeat_value_90d: float) -> dict:
    """Parameter sets with every input at its low-cost end, its value, or its high-cost end."""
    inp = a["inputs"]
    stars = {b: harm_ends(star_drop[b]) for b in LATE_BIN_COLS}
    rep = harm_ends(repeat_effect)
    return {end: {"epsilon": assumed_ends(inp["epsilon"])[end], "take_rate": assumed_ends(inp["take_rate"])[end],
                  "horizon_days": int(assumed_ends(inp["horizon_days"])[end]),
                  "star_drop": {b: stars[b][end] for b in LATE_BIN_COLS},
                  "repeat_effect": rep[end], "repeat_value": repeat_value_90d}
            for end in ENDS}


def tornado(a: dict, cases: dict, data: dict, repeat_180d: dict, repeat_value_180d: float) -> list[dict]:
    """One row at a time from the central case to its low-cost and high-cost ends, sorted by swing."""
    c, lo, hi = cases["central"], cases["low"], cases["high"]
    e180 = harm_ends(repeat_180d)
    specs = [(k, bool(a["inputs"][k].get("illustrative", False)), {k: lo[k]}, {k: hi[k]})
             for k in ("epsilon", "horizon_days", "take_rate")]
    specs += [("star_drop_bins", False, {"star_drop": lo["star_drop"]}, {"star_drop": hi["star_drop"]}),
              ("repeat_effect_90d", False, {"repeat_effect": lo["repeat_effect"]}, {"repeat_effect": hi["repeat_effect"]}),
              ("repeat_window_180d", False, {"repeat_effect": e180["low"], "repeat_value": repeat_value_180d},
               {"repeat_effect": e180["high"], "repeat_value": repeat_value_180d})]
    rows = []
    for name, illustrative, low_p, high_p in specs:
        r_lo = money_case({**c, **low_p}, data)["total_revenue"]
        r_hi = money_case({**c, **high_p}, data)["total_revenue"]
        rows.append({"input": name, "illustrative": illustrative, "low_revenue": r_lo, "high_revenue": r_hi,
                     "swing": r_hi - r_lo})
    return sorted(rows, key=lambda r: (-r["swing"], r["input"]))


def guard_loss_fraction(cases: dict, min_n: float) -> float:
    """Largest loss fraction epsilon x |beta| / N_j any case implies; above 1 raises (ADR-0013 §3)."""
    worst = max(p["epsilon"] * max(p["star_drop"].values()) for p in cases.values())
    frac = 0.0 if math.isnan(min_n) else worst / min_n
    if frac > 1:
        raise ValueError(f"loss fraction {frac:.3f} exceeds 1: the channel 2 formula does not fit the data")
    return frac


def flag1(central: dict) -> dict:
    if central["total_revenue"] <= 0:
        raise ValueError("central total revenue is not positive; flag 1 is undefined")
    share = central["channel1_revenue"] / central["total_revenue"]
    return {"id": 1, "test": "ADR-0006: the assumed channels make up nearly all of the range",
            "rule": f"channel 1 central revenue < {C.MONEY_MEASURED_SHARE_MIN:.0%} of the central total",
            "value": share, "fired": share < C.MONEY_MEASURED_SHARE_MIN}


def flag2(rows: list[dict]) -> dict:
    top = max(r["swing"] for r in rows)
    leaders = [r["input"] for r in rows if r["swing"] == top]
    illustrative = [r["input"] for r in rows if r["swing"] == top and r["illustrative"]]
    return {"id": 2, "test": "ADR-0006: one unsourced assumption flips the recommendation",
            "rule": "the tornado row with the largest swing is an illustrative input",
            "value": leaders, "fired": bool(illustrative)}


def flag3(scenario_central: float, low: float, high: float) -> dict:
    return {"id": 3, "test": "ADR-0012: the disruption scenario changes the recommendation",
            "rule": "the scenario's central figure lies outside [headline low corner, headline high corner]",
            "value": scenario_central, "fired": not low <= scenario_central <= high}


# --- Disruption scenario and decomposition (ADR-0013 §7) ---------------------------------------------

def scenario_fits(frame: pd.DataFrame) -> dict:
    """Model (b) for review_score and low_review, and model (a) for low_review, on one check frame."""
    s = frame[frame["has_review"]]
    out = {}
    for outcome in ("review_score", "low_review"):
        r = fit(s, outcome, LATE_BIN_COLS)
        out[f"{outcome}/b"] = {"n_obs": r["n_obs"], "estimates": {e["term"]: e for e in r["estimates"]}}
    r = fit(s, "low_review", ["late"])
    out["low_review/a"] = {"n_obs": r["n_obs"], **r["estimates"][0]}
    return out


def mix_decomposition(mix_head: dict, mix_scen: dict, low_bins: dict, headline: float, scenario: float) -> dict:
    """Phase 2 low_review bins weighted by each late-order mix; predicted vs observed drop (ADR-0012)."""
    wh = sum(mix_head[b] * low_bins[b]["estimate"] for b in LATE_BIN_COLS)
    ws = sum(mix_scen[b] * low_bins[b]["estimate"] for b in LATE_BIN_COLS)
    observed = headline - scenario
    return {"headline_mix_weighted": wh, "check10_mix_weighted": ws, "predicted_drop": wh - ws,
            "observed_drop": observed, "explained_share": (wh - ws) / observed if observed else None}


# --- Assembly ---------------------------------------------------------------------------------------

def _usd(d: dict, rate: float) -> dict:
    return {k: v / rate for k, v in d.items()}


def _pipeline(hist: dict, L: pd.DataFrame, horizons: list[int]) -> dict:
    mix = late_mix(L)
    exposure, eligible, min_n = {}, {}, []
    for H in horizons:
        X = seller_exposure(hist, L, H)
        exposure[H], eligible[H] = bin_exposure(X)
        min_n.append(X.loc[X["eligible"], "min_n"].min())
    finite = [x for x in min_n if not math.isnan(x)]
    return {"mix": mix, "exposure": exposure, "eligible": eligible, "min_n": min(finite) if finite else math.nan,
            "data": {"exposure": exposure, "mix": mix["mix"], "review_share": mix["review_share"]}}


def _cases_out(cases: dict, data: dict, rate: float) -> dict:
    out = {}
    for end in ENDS:
        brl = money_case(cases[end], data)
        out[end] = {"brl": brl, "usd": _usd(brl, rate)}
    return out


def build(t: pd.DataFrame, fe_json: dict, a: dict, frame10: pd.DataFrame | None = None) -> dict:
    """Every Phase 4 number from the built table, fe.json and the assumptions (ADR-0013)."""
    measured = resolve_measured(a, fe_json, t.columns)
    inp, rate = a["inputs"], fx_rate(a)
    horizons = sorted({int(inp["horizon_days"][k]) for k in ("low", "value", "high")})
    values = {}
    for w in C.REPEAT_WINDOWS:
        values[f"repeat_value_{w}d"], values[f"repeaters_{w}d"] = repeat_value(t, w)
    hist = seller_history(t)

    head = _pipeline(hist, late_orders(t), horizons)
    cases = case_params(a, measured["star_drop_bins"], measured["repeat_effect_90d"]["late"], values["repeat_value_90d"])
    loss_frac = guard_loss_fraction(cases, head["min_n"])
    out = _cases_out(cases, head["data"], rate)
    rows = tornado(a, cases, head["data"], measured["repeat_effect_180d"]["late"], values["repeat_value_180d"])
    ch3 = {end: assumed_ends(inp["contacts_per_late_order"])[end] * assumed_ends(inp["cost_per_contact"])[end]
           for end in ENDS}

    frame10 = check_frames(t)[10] if frame10 is None else frame10
    fits = scenario_fits(frame10)
    scen = _pipeline(hist, late_orders(t, frame10.loc[frame10["late"] == 1, "order_id"]), horizons)
    cases10 = case_params(a, fits["review_score/b"]["estimates"], measured["repeat_effect_90d"]["late"],
                          values["repeat_value_90d"])
    guard_loss_fraction(cases10, scen["min_n"])
    out10 = _cases_out(cases10, scen["data"], rate)

    headline = headline_from(fe_json)["estimate"]
    lo, c, hi = (out[e]["brl"]["total_revenue"] for e in ENDS)
    flags = [flag1(out["central"]["brl"]), flag2(rows), flag3(out10["central"]["brl"]["total_revenue"], lo, hi)]
    bp = measured["broken_promise"]
    return {
        "label": "Phase 4 money translation: cost per late delivery (ADR-0006, ADR-0013)",
        "spec": {
            "unit": "per late headline order; BRL, USD = BRL / mean monthly BCB PTAX rate",
            "platform_revenue": "lost GMV (item price) x take rate, channels 1-2; channel 3 is a direct cost",
            "channel2_anchor": "review_answer_ts of the late order; later orders in (answer, answer + H]",
            "eligible": f"answer + H < {C.FOLLOWUP_END.date()}",
            "later_order_excluded_statuses": list(C.LATER_ORDER_EXCLUDED_STATUSES),
            "horizons_days": horizons,
            "range": "every input at its low-cost end to every input at its high-cost end: bounds, not a confidence interval",
            "measured_share_min": C.MONEY_MEASURED_SHARE_MIN,
            "window_months": window_months(),
        },
        "fx": {"brl_per_usd": rate, "months": len(a["fx"]["monthly"]), "series": a["fx"]["series"]},
        "inputs": inputs_echo(a),
        "measured": {
            "repeat_effect_90d": harm_ends(measured["repeat_effect_90d"]["late"]),
            "repeat_effect_180d": harm_ends(measured["repeat_effect_180d"]["late"]),
            "star_drop": {b: harm_ends(measured["star_drop_bins"][b]) for b in LATE_BIN_COLS},
            **values,
        },
        "late_orders": head["mix"],
        "exposure": {str(H): {"by_bin": head["exposure"][H], "eligible": head["eligible"][H]} for H in horizons},
        "max_loss_fraction": loss_frac,
        "cases": out,
        "channel3_addon": {end: {"brl": ch3[end], "usd": ch3[end] / rate} for end in ENDS},
        "tornado": rows,
        "flags": flags,
        "flags_fired": [f["id"] for f in flags if f["fired"]],
        "scenario": {
            "label": "Disruption periods excluded (check 10 sample; ADR-0012, ADR-0013 §7): sensitivity",
            "fits": fits,
            "late_orders": scen["mix"],
            "exposure": {str(H): {"by_bin": scen["exposure"][H], "eligible": scen["eligible"][H]} for H in horizons},
            "cases": out10,
        },
        "mix_decomposition": mix_decomposition(head["mix"]["mix"], scen["mix"]["mix"], measured["low_review_bins"],
                                               headline, fits["low_review/a"]["estimate"]),
        "recommendation": {
            "break_even_per_late_delivery": {end: {"brl": v, "usd": v / rate} for end, v in zip(ENDS, (lo, c, hi))},
            "broken_promise_equivalent_days": bp["late"]["estimate"] / bp["delivery_days"]["estimate"],
            "caveat": "The data has no checkout conversion, so the cost of padding promised dates is unmeasured.",
        },
        "annual_illustration": {
            "late_orders": head["mix"]["late_orders"],
            "late_orders_per_year": head["mix"]["late_orders"] / window_months() * 12,
            "central_revenue_brl": c * head["mix"]["late_orders"] / window_months() * 12,
            "central_revenue_usd": c * head["mix"]["late_orders"] / window_months() * 12 / rate,
            "note": "This dataset's volume, which may not be Olist's full volume: illustrative.",
        },
    }


# --- Report, figure, entry point (T28) --------------------------------------------------------------

def _money(x: float) -> str:
    return f"{x:,.2f}"


def _case_rows(cases: dict) -> list[dict]:
    return [{"case": e, "channel_1_brl": _money(c["brl"]["channel1_revenue"]),
             "channel_2_brl": _money(c["brl"]["channel2_revenue"]), "total_brl": _money(c["brl"]["total_revenue"]),
             "total_usd": _money(c["usd"]["total_revenue"]), "lost_gmv_brl": _money(c["brl"]["total_gmv"])}
            for e, c in cases.items()]


def _flag_value(f: dict) -> str:
    v = f["value"]
    if f["id"] == 1:
        return f"channel 1 share {v:.1%}"
    if f["id"] == 2:
        return "largest swing: " + ", ".join(v)
    return f"scenario central R$ {_money(v)}"


def _exposure_rows(exposure: dict) -> list[dict]:
    return [{"H_days": H, **{f"E_{b}": _money(e["by_bin"][b]) for b in LATE_BIN_COLS},
             "eligible": ", ".join(f"{e['eligible'][b]:,}" for b in LATE_BIN_COLS)} for H, e in exposure.items()]


def to_markdown(d: dict) -> str:
    rate, lo, s = d["fx"]["brl_per_usd"], d["late_orders"], d["scenario"]
    yes = {True: "**fired**", False: "not fired"}
    flags = [{"flag": f["id"], "test": f["test"], "rule": f["rule"], "value": _flag_value(f), "fired": yes[f["fired"]]}
             for f in d["flags"]]
    tornado = [{"input": r["input"], "status": "illustrative" if r["illustrative"] else "sourced or measured",
                "low_brl": _money(r["low_revenue"]), "high_brl": _money(r["high_revenue"]), "swing_brl": _money(r["swing"])}
               for r in d["tornado"]]
    assumed = [{"input": k, "status": v["status"], "low": f"{v['low']:g}", "value": f"{v['value']:g}",
                "high": f"{v['high']:g}", "unit": v["unit"],
                "sources": "; ".join(x["citation"] for x in v["sources"]) or "none (illustrative)"}
               for k, v in d["inputs"].items() if v["tag"] == "assumed"]
    m = d["measured"]
    ends = lambda e: f"{e['low']:.6f} / {e['central']:.6f} / {e['high']:.6f}"  # noqa: E731
    measured = ([{"input": "repeat effect 90 days, abs()", "low / central / high": ends(m["repeat_effect_90d"])},
                 {"input": "repeat effect 180 days, abs()", "low / central / high": ends(m["repeat_effect_180d"])}]
                + [{"input": f"star drop {b} (stars)", "low / central / high": ends(m["star_drop"][b])} for b in LATE_BIN_COLS])
    mix = [{"bin": b, "late_with_review": f"{lo['counts'][b]:,}", "mix": f"{lo['mix'][b]:.4f}",
            "check10_late_with_review": f"{s['late_orders']['counts'][b]:,}", "check10_mix": f"{s['late_orders']['mix'][b]:.4f}"}
           for b in LATE_BIN_COLS]
    fits = [{"model": k, "term": t, "estimate": f"{e['estimate']:.4f}", "ci95_low": f"{e['ci95_low']:.4f}",
             "ci95_high": f"{e['ci95_high']:.4f}", "n_obs": f"{v['n_obs']:,}"}
            for k, v in s["fits"].items() if k.endswith("/b") for t, e in v["estimates"].items()]
    a10 = s["fits"]["low_review/a"]
    md, r = d["mix_decomposition"], d["recommendation"]
    be = r["break_even_per_late_delivery"]
    ann, c3 = d["annual_illustration"], d["channel3_addon"]
    return "\n\n".join([
        "# Phase 4 money translation: what one late delivery costs",
        "Generated by `make money` from `orders.parquet`, `fe.json` and `assumptions.toml`. Every formula, input and "
        "flag rule was fixed in ADR-0013 before this run; flags are computed by code. Figures are per late headline "
        f"order ({lo['late_orders']:,} late orders, {lo['late_with_review']:,} with a review), as platform revenue "
        f"(lost GMV x take rate). USD at R$ {rate:.4f} per US$ (mean of {d['fx']['months']} monthly BCB PTAX averages, "
        "2017-01 to 2018-08). The range is bounds (every input at its low-cost or high-cost end), not a confidence interval.",
        "## Cost per late delivery",
        md_table(_case_rows(d["cases"])),
        "Channel 1 (lost repeat purchases) is measured but an upper bound: its 90-day effect's CI includes 0 (ADR-0004). "
        "Channel 2 (rating spillover) rests on the assumed ε and horizon; the star drop, the sellers' later sales and "
        "review counts are measured (ADR-0013 §3).",
        "## Operating costs: illustrative add-on, outside the range",
        md_table([{"case": e, "brl": _money(v["brl"]), "usd": _money(v["usd"])} for e, v in c3.items()]),
        "Support contacts per late order (no source) x cost per contact (CIP study, illustrative). A direct cost, "
        "not multiplied by the take rate; never part of the range, the tornado or flags 1-2 (ADR-0013 §4).",
        "## Flags (ADR-0013 §6)",
        md_table(flags),
        "## Tornado: one input at a time from the central case",
        md_table(tornado),
        "Figure: `fig_money_tornado.png`. The 180-day row swaps both the repeat effect and the value per lost repeat.",
        "## Disruption scenario (sensitivity; ADR-0012, ADR-0013 §7)",
        f"Check-10 sample (Feb-Mar 2018 surge and May 2018 strike excluded): {s['late_orders']['late_orders']:,} late "
        f"orders, {s['late_orders']['late_with_review']:,} with a review. Model (a) on this sample: {a10['estimate']:.4f}, "
        f"95% CI [{a10['ci95_low']:.4f}, {a10['ci95_high']:.4f}], N {a10['n_obs']:,}.",
        md_table(_case_rows(s["cases"])),
        "Bin effects re-fit on the check-10 sample (model (b); star drop uses `review_score`):",
        md_table(fits),
        "## Lateness-mix decomposition (ADR-0012, now from code)",
        md_table([{"headline_mix_weighted": f"{md['headline_mix_weighted']:.4f}",
                   "check10_mix_weighted": f"{md['check10_mix_weighted']:.4f}",
                   "predicted_drop": f"{md['predicted_drop']:.4f}", "observed_drop": f"{md['observed_drop']:.4f}",
                   "explained_share": "-" if md["explained_share"] is None else f"{md['explained_share']:.1%}"}]),
        "Phase 2 `low_review/b` bin effects weighted by each sample's mix of late orders with a review. Observed drop "
        "= headline minus the check-10 model (a) estimate.",
        "## Recommendation numbers",
        f"- Break-even per late delivery avoided (platform revenue): R$ {_money(be['low']['brl'])} / "
        f"{_money(be['central']['brl'])} / {_money(be['high']['brl'])} (US$ {_money(be['low']['usd'])} / "
        f"{_money(be['central']['usd'])} / {_money(be['high']['usd'])}), low / central / high.\n"
        f"- Broken-promise-equivalent days: {r['broken_promise_equivalent_days']:.1f} (`low_review/c`: the broken-promise "
        "effect over the effect of one extra delivery day; ratio of point estimates, no CI).\n"
        f"- Caveat: {r['caveat']}",
        "## Inputs",
        "Assumed (`assumptions.toml`):",
        md_table(assumed),
        "Measured (from `fe.json`; cost ends from 95% CIs, clamped at 0):",
        md_table(measured),
        f"Value per lost repeat: R$ {_money(m['repeat_value_90d'])} at 90 days ({m['repeaters_90d']:,} repeaters), "
        f"R$ {_money(m['repeat_value_180d'])} at 180 days ({m['repeaters_180d']:,}). Review share of late orders: "
        f"{lo['review_share']:.4f}. Largest loss fraction any case implies: {d['max_loss_fraction']:.4f}.",
        md_table(mix),
        "Seller exposure E_b (mean sum of price / visible reviews over the seller's later orders in the horizon) and "
        "eligible late orders per bin (1-2, 3-7, 8-14, 15+):",
        md_table(_exposure_rows(d["exposure"])),
        "## Annual illustration",
        f"{ann['late_orders']:,} late orders over {d['spec']['window_months']} months = {ann['late_orders_per_year']:,.0f} "
        f"a year; x the central cost = R$ {ann['central_revenue_brl']:,.0f} (US$ {ann['central_revenue_usd']:,.0f}) a year. "
        f"{ann['note']}",
        "## Specification echo",
        "\n".join(f"- {k}: {v}" for k, v in d["spec"].items()),
    ]) + "\n"


def plot(d: dict, path) -> None:
    rows = d["tornado"][::-1]  # largest swing on top
    central = d["cases"]["central"]["brl"]["total_revenue"]
    fig, ax = plt.subplots(figsize=(10, 4.8), facecolor=SURFACE)
    for y, r in enumerate(rows):
        ax.barh(y, r["high_revenue"] - r["low_revenue"], left=r["low_revenue"], height=0.55, color=SERIES,
                alpha=0.45 if r["illustrative"] else 1.0, hatch="//" if r["illustrative"] else None, edgecolor=SERIES)
        ax.annotate(f"{r['low_revenue']:.2f} to {r['high_revenue']:.2f}", (max(r["high_revenue"], central), y),
                    xytext=(6, 0), textcoords="offset points", va="center", color=INK_2, fontsize=9)
    ax.axvline(central, color=INK, linewidth=1)
    ax.annotate(f"central R$ {central:.2f}", (central, len(rows) - 0.4), xytext=(4, 0), textcoords="offset points",
                color=INK, fontsize=9)
    labels = [r["input"] + (" (illustrative)" if r["illustrative"] else "") for r in rows]
    ax.set_yticks(range(len(rows)), labels, color=INK)
    ax.set_title("What drives the cost per late delivery\nPlatform revenue per late order, R$, one input moved at a time",
                 loc="left", color=INK, fontsize=11)
    ax.set_ylim(-0.6, len(rows))
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.tick_params(axis="y", colors=INK, labelsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)


def main() -> None:
    fe_json = json.loads((C.OUTPUTS_DIR / "fe.json").read_text())
    result = rounded(build(pd.read_parquet(C.ORDERS_PARQUET), fe_json, load_assumptions()))
    (C.OUTPUTS_DIR / "money.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "money.md").write_text(to_markdown(result))
    plot(result, C.OUTPUTS_DIR / "fig_money_tornado.png")
    c = result["cases"]
    print("Cost per late delivery (platform revenue, R$): " + " / ".join(
        _money(c[e]["brl"]["total_revenue"]) for e in ENDS) + " (low / central / high)")
    print("Flags fired: " + (", ".join(f"flag {i}" for i in result["flags_fired"]) or "none"))
    print(f"Wrote {C.OUTPUTS_DIR / 'money.md'}")


if __name__ == "__main__":
    main()
