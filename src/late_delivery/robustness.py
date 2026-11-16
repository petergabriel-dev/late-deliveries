"""Phase 3 robustness checks (ADR-0007 §7, ADR-0011).

The 12 pre-registered checks, each with the flag rule ADR-0011 §1 fixed before any result:

- sample checks (3, 7, 10, 11, 12): headline model on a different set of orders; fires if the point
  estimate leaves the headline 95% CI.
- estimand checks (1, 2, 8): a different treatment or a biased subset; fires against a direction
  stated in advance.
- diagnostic checks (4 placebo cutoffs, 5 covariate continuity, 6 unobserved confounding).
- reference (9): Phase 2 `repeat_180d/a`, no new model.

Phase 3 variants (relabels, masks, the multi-seller frame) live only here; build.py and the headline
analysis frame are untouched (ADR-0011 §6). Flags are computed in code, never judged by hand.

Sensitivity to unobserved confounding (check 6, ADR-0011 §5): Cinelli and Hazlett (2020),
"Making Sense of Sensitivity", hand-rolled. The formulas follow the numeric methods of the
sensemakr R package (v0.1.6): partial_r2, robustness_value, ovb_partial_r2_bound, bias,
adjusted_estimate (reduce = TRUE) and adjusted_se.

Partial R² values come from plain-OLS (iid) fits with the headline formula, fixed effects and
singleton drop, using residual sums of squares of nested fits. The bias uses the iid SE; the
adjusted CI uses the headline's seller-clustered SE scaled by the same SE factor (ADR-0011 §5).
"""

import json
import math
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pyfixest as pf  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from scipy.stats import t as student_t  # noqa: E402

from late_delivery import config as C  # noqa: E402
from late_delivery import rd  # noqa: E402
from late_delivery.diagnostics import GRID, INK, INK_2, SERIES, SURFACE, _style, md_table, rounded  # noqa: E402
from late_delivery.fe import CATEGORICAL_CONTROLS, FIXED_EFFECTS, NUMERIC_CONTROLS, analysis_frame, fit  # noqa: E402


# --- Sensitivity formulas (Cinelli and Hazlett 2020; sensemakr numeric methods) -------------------

def partial_r2(t_stat: float, dof: float) -> float:
    """Partial R² of a regressor with the outcome, from its t statistic and residual df."""
    return t_stat**2 / (t_stat**2 + dof)


def group_partial_r2(rss_restricted: float, rss_full: float) -> float:
    """Partial R² of a group of regressors: share of the restricted model's residual SS they explain."""
    if not 0 < rss_full <= rss_restricted:
        raise ValueError(f"nested fits out of order: rss_full={rss_full}, rss_restricted={rss_restricted}")
    return (rss_restricted - rss_full) / rss_restricted


def robustness_value(t_stat: float, dof: float, q: float = 1.0, alpha: float = 1.0) -> float:
    """RV_q (alpha = 1): confounder strength that cuts the estimate by 100q%; RV_{q,alpha} otherwise.

    ponytail: the 'extreme' case (sensemakr extreme_robustness_value, when q*|f| > 1/f_crit) is not
    implemented and raises; it needs |t| > dof / t_crit, far outside this project's estimates.
    """
    fq = q * abs(t_stat / math.sqrt(dof))
    f_crit = abs(student_t.ppf(alpha / 2, dof - 1)) / math.sqrt(dof - 1)
    fqa = fq - f_crit
    if fqa <= 0:
        return 0.0
    if f_crit > 0 and fq > 1 / f_crit:
        raise NotImplementedError("extreme robustness value case (q*|f| > 1/f_crit) not implemented")
    return 2 / (1 + math.sqrt(1 + 4 / fqa**2))


def ovb_partial_r2_bound(r2dxj_x: float, r2yxj_dx: float, kd: float = 1.0, ky: float | None = None) -> tuple[float, float]:
    """(R²_{D~Z|X}, R²_{Y~Z|D,X}) for a confounder kd (ky) times as strong as benchmark Xj."""
    ky = kd if ky is None else ky
    r2dz_x = kd * (r2dxj_x / (1 - r2dxj_x))
    if r2dz_x >= 1:
        raise ValueError(f"implied R2(D~Z|X) = {r2dz_x:.4f} >= 1: impossible kd = {kd}")
    r2zxj_xd = kd * r2dxj_x**2 / ((1 - kd * r2dxj_x) * (1 - r2dxj_x))
    if r2zxj_xd >= 1:
        raise ValueError(f"impossible kd = {kd}")
    r2yz_dx = ((math.sqrt(ky) + math.sqrt(r2zxj_xd)) / math.sqrt(1 - r2zxj_xd))**2 * (r2yxj_dx / (1 - r2yxj_dx))
    if r2yz_dx > 1:
        warnings.warn(f"implied R2(Y~Z|D,X) = {r2yz_dx:.4f} > 1 at k = {kd}; set to 1 (as sensemakr does)")
        r2yz_dx = 1.0
    return r2dz_x, r2yz_dx


def bias(se: float, dof: float, r2dz_x: float, r2yz_dx: float) -> float:
    """Omitted-variable bias for a confounder with the given partial R² values (sensemakr eq. 14)."""
    return math.sqrt(r2yz_dx * r2dz_x / (1 - r2dz_x)) * se * math.sqrt(dof)


def adjusted_estimate(estimate: float, se: float, dof: float, r2dz_x: float, r2yz_dx: float) -> float:
    """The estimate moved toward 0 by the bias (sensemakr reduce = TRUE)."""
    sign = -1.0 if estimate < 0 else 1.0
    return sign * (abs(estimate) - bias(se, dof, r2dz_x, r2yz_dx))


def adjusted_se(se: float, dof: float, r2dz_x: float, r2yz_dx: float) -> float:
    """SE after adjusting for the confounder; ADR-0011 §5 passes the clustered SE here."""
    return math.sqrt(1 - r2yz_dx) / math.sqrt(1 - r2dz_x) * se * math.sqrt(dof / (dof - 1))


def confounder_bounds(estimate: float, se_iid: float, se_ci: float, crit: float, dof: float,
                      r2dxj_x: float, r2yxj_dx: float, ks=(1, 2, 3)) -> list[dict]:
    """Bias-adjusted estimate and 95% CI for confounders k times as strong as one benchmark (kd = ky = k).

    se_iid feeds the bias (data geometry); se_ci and crit give the CI (ADR-0011 §5: the headline's
    clustered SE and its CI critical value).
    """
    rows = []
    for k in ks:
        r2dz_x, r2yz_dx = ovb_partial_r2_bound(r2dxj_x, r2yxj_dx, kd=k)
        est = adjusted_estimate(estimate, se_iid, dof, r2dz_x, r2yz_dx)
        se = adjusted_se(se_ci, dof, r2dz_x, r2yz_dx)
        rows.append({"k": k, "r2dz_x": r2dz_x, "r2yz_dx": r2yz_dx, "adjusted_estimate": est, "adjusted_se": se,
                     "adjusted_t": est / se, "ci95_low": est - crit * se, "ci95_high": est + crit * se})
    return rows


# --- Plain-OLS fits for partial R² ----------------------------------------------------------------

def fit_iid(f, outcome: str, terms: list[str], drop: tuple[str, ...] = ()) -> dict:
    """Headline formula fit with iid SEs (same FE, singletons dropped), optionally without some controls.

    Returns N, residual df, residual sum of squares, and the iid estimate, SE and t for each term.
    `drop` names analysis-frame control columns to leave out (a benchmark group).
    """
    unknown = set(drop) - set(CATEGORICAL_CONTROLS) - set(NUMERIC_CONTROLS)
    if unknown:
        raise ValueError(f"not a control: {sorted(unknown)}")
    rhs = list(terms) + [f"C({c})" for c in CATEGORICAL_CONTROLS if c not in drop] \
        + [c for c in NUMERIC_CONTROLS if c not in drop]
    fml = f"{outcome} ~ {' + '.join(rhs)} | {FIXED_EFFECTS}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pyfixest announces singleton drops
        m = pf.feols(fml, data=f, vcov="iid", fixef_rm="singleton")
    missing = [x for x in terms if x not in m._coefnames]
    if missing:
        raise RuntimeError(f"{fml}: term dropped as collinear: {missing}")
    coef, se, tstat = m.coef(), m.se(), m.tstat()
    return {
        "formula": fml, "n_obs": int(m._N), "dof": int(m.variance_covariance.df_t),
        "rss": float((m.resid() ** 2).sum()),
        "terms": {x: {"estimate": float(coef[x]), "se": float(se[x]), "t": float(tstat[x])} for x in terms},
    }


# --- Check samples (ADR-0011 §2-3) ----------------------------------------------------------------

def check1_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Check 1: late = 2+ days late; orders 1 day late count as on time."""
    return f.assign(late=(f["days_late"] >= C.CHECK1_LATE_MIN_DAYS).astype(float))


def check2_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Check 2: late = delivery_days strictly above its seller-state -> customer-state route median.

    The median is taken over every row of `f` (all headline orders, with or without a review).
    """
    route = f["seller_state"] + "->" + f["customer_state"]
    median = f["delivery_days"].groupby(route).transform("median")
    return f.assign(late=(f["delivery_days"] > median).astype(float))


def _window(f: pd.DataFrame, bounds: tuple) -> pd.Series:
    lo, hi = bounds
    return f["purchase_date"].ge(lo) & f["purchase_date"].lt(hi)


def strike_mask(f: pd.DataFrame) -> pd.Series:
    """Orders whose purchase-to-promised window overlaps the strike (pre-treatment dates only)."""
    first, last = C.STRIKE_2018
    promised = f["purchase_date"] + pd.to_timedelta(f["promised_days"], unit="D")
    return f["purchase_date"].le(last) & promised.ge(first)


def drop_rows(f: pd.DataFrame, drop: pd.Series, what: str) -> pd.DataFrame:
    """Drop the masked rows; a mask that drops nothing means a wrong date or column, so it raises."""
    if not drop.any():
        raise ValueError(f"{what}: mask drops no rows")
    return f[~drop]


def check_frames(t: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Analysis frames for the FE checks, keyed by check id (all rows; the model keeps those with a review)."""
    f = analysis_frame(t)
    bf, surge, strike = _window(f, C.BLACK_FRIDAY_WEEK_2017), _window(f, C.SURGE_2018), strike_mask(f)
    drop_rows(f, surge, "surge window")  # each check 10 component must bite on its own
    drop_rows(f, strike, "strike window")
    return {
        1: check1_frame(f),
        2: check2_frame(f),
        3: drop_rows(f, bf, "Black Friday week"),
        7: analysis_frame(t, include_multi_seller=True),
        8: drop_rows(f, f["review_created_before_delivery"].eq(1), "reviews written before delivery"),
        10: drop_rows(f, surge | strike, "surge and strike"),
        11: drop_rows(f, f["purchase_date"].lt(C.CHECK11_WINDOW_START), "purchases before the check 11 window"),
        12: drop_rows(f, f["n_reviews"].gt(1), "orders with more than one review"),
    }


# --- Runners ---------------------------------------------------------------------------------------

_RD_KEYS = ("estimate", "ci95_low", "ci95_high", "estimate_bias_corrected", "n_left", "n_right",
            "days_left", "days_right")


def fe_check(frame: pd.DataFrame, n_ref: int) -> dict:
    """Headline model (a) on one check's sample: low_review on binary `late` (ADR-0011 §2)."""
    s = frame[frame["has_review"]]
    late = int(s["late"].sum())
    if len(s) == 0 or late == 0 or late == len(s):
        raise ValueError(f"check sample needs late and on-time orders (n = {len(s)}, late = {late})")
    r = fit(s, "low_review", ["late"])
    e = r["estimates"][0]
    return {"estimate": e["estimate"], "se": e["se"], "ci95_low": e["ci95_low"], "ci95_high": e["ci95_high"],
            "n_sample": len(s), "n_obs": r["n_obs"], "late_orders": late, "clusters": r["clusters"],
            "rows_vs_headline": len(s) - n_ref}


def placebo(f: pd.DataFrame) -> list[dict]:
    """Check 4: the main donut RD with the cutoff moved to each placebo (ADR-0011 §4)."""
    rows = []
    for cutoff, donut in C.PLACEBO_CUTOFFS:
        d = rd.rd_sample(f, C.RD_BANDWIDTH, True, cutoff=cutoff, donut_days=donut)
        late_side = d["days_late"] > C.RD_CUTOFF
        if late_side.any() and not late_side.all():
            raise ValueError(f"placebo window at {cutoff} crosses the real cutoff")
        e = rd.estimate(d, C.RD_BANDWIDTH, True, cutoff=cutoff, donut_days=donut)
        rows.append({"cutoff": cutoff, "donut_days": list(donut), **{k: e[k] for k in _RD_KEYS}})
    return rows


def continuity(f: pd.DataFrame) -> list[dict]:
    """Check 5: the main donut RD with each pre-treatment covariate as the outcome (ADR-0011 §4)."""
    d = rd.rd_sample(f, C.RD_BANDWIDTH, True)
    return [{"covariate": c, **{k: e[k] for k in _RD_KEYS}}
            for c in C.CONTINUITY_COVARIATES
            for e in [rd.estimate(d, C.RD_BANDWIDTH, True, outcome=c)]]


def sensitivity(f: pd.DataFrame, headline: dict) -> dict:
    """Check 6: Cinelli-Hazlett bounds against the distance and customer-state groups (ADR-0011 §5)."""
    s = f[f["has_review"]]
    crv = fit(s, "low_review", ["late"])
    h = crv["estimates"][0]
    if abs(h["estimate"] - headline["estimate"]) > 5e-7:  # fe.json is rounded to 6 decimals
        raise ValueError(f"headline refit {h['estimate']} differs from fe.json {headline['estimate']}")
    y_full, d_full = fit_iid(s, "low_review", ["late"]), fit_iid(s, "late", [])
    t_iid, dof = y_full["terms"]["late"], y_full["dof"]
    if abs(t_iid["estimate"] - h["estimate"]) > 1e-9:
        raise RuntimeError("iid and CRV1 point estimates differ")
    crit = (h["ci95_high"] - h["estimate"]) / h["se"]  # the headline CI's own critical value
    n_obs = {crv["n_obs"], y_full["n_obs"], d_full["n_obs"]}
    benchmarks = []
    for name, cols in C.SENSITIVITY_BENCHMARKS.items():
        y_r, d_r = fit_iid(s, "low_review", ["late"], drop=cols), fit_iid(s, "late", [], drop=cols)
        n_obs |= {y_r["n_obs"], d_r["n_obs"]}
        r2dxj_x, r2yxj_dx = group_partial_r2(d_r["rss"], d_full["rss"]), group_partial_r2(y_r["rss"], y_full["rss"])
        benchmarks.append({"benchmark": name, "columns": list(cols), "r2dxj_x": r2dxj_x, "r2yxj_dx": r2yxj_dx,
                           "bounds": confounder_bounds(h["estimate"], t_iid["se"], h["se"], crit, dof,
                                                       r2dxj_x, r2yxj_dx, C.SENSITIVITY_K)})
    if len(n_obs) != 1:
        raise RuntimeError(f"iid and CRV1 fits kept different rows: {sorted(n_obs)}")
    return {"estimate": h["estimate"], "se_clustered": h["se"], "se_iid": t_iid["se"], "t_iid": t_iid["t"],
            "dof": dof, "crit": crit, "n_obs": crv["n_obs"], "r2yd_x": partial_r2(t_iid["t"], dof),
            "rv_q1": robustness_value(t_iid["t"], dof), "rv_q1_alpha05": robustness_value(t_iid["t"], dof, alpha=0.05),
            "benchmarks": benchmarks}


# --- Inputs from Phase 2 outputs -------------------------------------------------------------------

def headline_from(fe_json: dict) -> dict:
    try:
        p = fe_json["primary"]
        return {k: float(p[k]) for k in ("estimate", "ci95_low", "ci95_high")}
    except (KeyError, TypeError) as e:
        raise ValueError(f"fe.json has no headline estimate: {e}") from e


def repeat_180d_from(fe_json: dict) -> dict:
    for m in fe_json.get("models", []):
        if m.get("id") == "repeat_180d/a":
            e = next(x for x in m["estimates"] if x["term"] == "late")
            return {"estimate": e["estimate"], "ci95_low": e["ci95_low"], "ci95_high": e["ci95_high"], "n_obs": m["n_obs"]}
    raise ValueError("fe.json has no repeat_180d/a model")


def rd_main_from(rd_json: dict) -> float:
    for e in rd_json.get("estimates", []):
        if e.get("spec") == "main":
            return float(e["estimate"])
    raise ValueError("rd.json has no main estimate")


# --- Flags (ADR-0011 §1) ----------------------------------------------------------------------------

SAMPLE_CHECKS = (3, 7, 10, 11, 12)
CHECKS = {  # id -> (label, class)
    1: ("Late = 2+ days late (day +1 counts as on time)", "estimand"),
    2: ("Late = slower than the route median", "estimand"),
    3: ("Exclude Black Friday week (2017-11-24 to 11-30)", "sample"),
    4: ("Placebo cutoffs at days -7 and +7", "diagnostic"),
    5: ("Covariate continuity at the promised date", "diagnostic"),
    6: ("Sensitivity to unobserved confounding", "diagnostic"),
    7: ("Include multi-seller orders", "sample"),
    8: ("Post-delivery reviews only (biased)", "estimand"),
    9: ("Repeat purchase at 180 days", "reference"),
    10: ("Exclude the Feb-Mar 2018 surge and the May 2018 strike", "sample"),
    11: ("Window from 2017-02-01", "sample"),
    12: ("Drop orders with more than one review", "sample"),
}


def _includes_zero(r: dict) -> bool:
    return r["ci95_low"] <= 0 <= r["ci95_high"]


def rule(check_id: int, headline: dict, rd_main: float) -> tuple[str, str]:
    """(rule, meaning if fired) for one check, as ADR-0011 §1 states them."""
    if check_id in SAMPLE_CHECKS:
        return (f"point estimate outside the headline 95% CI [{headline['ci95_low']:.4f}, {headline['ci95_high']:.4f}]",
                "the headline is fragile on this dimension (ADR-0007)")
    return {
        1: (f"point estimate < headline estimate ({headline['estimate']:.4f})",
            "removing the mildest late orders lowered the effect (ADR-0011 §1)"),
        2: ("point estimate <= 0", "being slower than the route norm shows no positive effect (ADR-0011 §1)"),
        8: (f"point estimate <= 0 or >= headline estimate ({headline['estimate']:.4f})",
            "the arrived-late effect is not positive or exceeds the total effect (ADR-0011 §1)"),
        4: (f"abs(placebo conventional estimate) >= abs(main RD conventional estimate) ({abs(rd_main):.4f})",
            "the RD estimate reflects the shape of the curve, not the promise (ADR-0010)"),
        5: ("any covariate's robust 95% CI excludes 0",
            "a covariate jumps at the promised date: the RD's no-sorting assumption fails (the headline does not rest on the RD)"),
        6: ("for a confounder 1x as strong as distance or customer state, the bias-adjusted 95% CI includes 0",
            "the headline rests on a fragile no-unobserved-confounding assumption (ADR-0007, ADR-0010)"),
        9: ("no new flag: the Phase 2 repeat-window flag applies (outputs/ladder.json)", ""),
    }[check_id]


def flag(check_id: int, r: dict, headline: dict, rd_main: float) -> bool | None:
    """Whether a check's pre-registered flag fires (ADR-0011 §1). Check 9 has no flag of its own."""
    if check_id in SAMPLE_CHECKS:
        return r["estimate"] < headline["ci95_low"] or r["estimate"] > headline["ci95_high"]
    if check_id == 1:
        return r["estimate"] < headline["estimate"]
    if check_id == 2:
        return r["estimate"] <= 0
    if check_id == 8:
        return not 0 < r["estimate"] < headline["estimate"]
    if check_id == 4:
        return any(abs(p["estimate"]) >= abs(rd_main) for p in r["placebos"])
    if check_id == 5:
        return any(not _includes_zero(c) for c in r["covariates"])
    if check_id == 6:
        return any(_includes_zero(next(b for b in bm["bounds"] if b["k"] == 1)) for bm in r["benchmarks"])
    if check_id == 9:
        return None
    raise ValueError(f"unknown check {check_id}")


def run_checks(t: pd.DataFrame, fe_json: dict, rd_json: dict) -> list[dict]:
    """Run all 12 checks on the built table and compute their flags (ADR-0011)."""
    headline, rd_main = headline_from(fe_json), rd_main_from(rd_json)
    f = analysis_frame(t)
    n_ref = int(f["has_review"].sum())
    frames = check_frames(t)
    results = []
    for cid, (label, cls) in CHECKS.items():
        if cid in frames:
            r = fe_check(frames[cid], n_ref)
        elif cid == 4:
            r = {"placebos": placebo(f)}
        elif cid == 5:
            r = {"covariates": continuity(f)}
        elif cid == 6:
            r = sensitivity(f, headline)
        else:
            r = repeat_180d_from(fe_json)
        text, if_fired = rule(cid, headline, rd_main)
        results.append({"id": cid, "label": label, "class": cls, "rule": text, **r,
                        "fired": flag(cid, r, headline, rd_main), "if_fired": if_fired})
    return results


# --- Report ----------------------------------------------------------------------------------------

def spec() -> dict:
    """Echo of the ADR-0011 parameters the run used, so drift from the ADR is visible."""
    day = "%Y-%m-%d"
    return {
        "model": "headline model (a): low_review on binary late, ADR-0007 §1 controls, seller + purchase-week FE, "
                 "singletons dropped, CRV1 by seller, orders with a review",
        "check1_late_min_days": C.CHECK1_LATE_MIN_DAYS,
        "check2_route": "seller_state -> customer_state; median delivery_days over all headline orders; late = strictly above",
        "check3_black_friday_week": [d.strftime(day) for d in C.BLACK_FRIDAY_WEEK_2017],
        "check7_multi_seller_label": C.MULTI_SELLER_LABEL,
        "check10_surge": [d.strftime(day) for d in C.SURGE_2018],
        "check10_strike_first_last_day": [d.strftime(day) for d in C.STRIKE_2018],
        "check11_window_start": C.CHECK11_WINDOW_START.strftime(day),
        "date_windows": "[start, end) on the purchase date; strike: purchase date <= last day and promised date >= first day",
        "rd_bandwidth": C.RD_BANDWIDTH,
        "placebo_cutoffs": [{"cutoff": c, "donut_days": list(d)} for c, d in C.PLACEBO_CUTOFFS],
        "continuity_covariates": list(C.CONTINUITY_COVARIATES),
        "sensitivity_benchmarks": {k: list(v) for k, v in C.SENSITIVITY_BENCHMARKS.items()},
        "sensitivity_k": list(C.SENSITIVITY_K),
    }


def build(t: pd.DataFrame, fe_json: dict, rd_json: dict) -> dict:
    checks = run_checks(t, fe_json, rd_json)
    first_fe = next(c for c in checks if "rows_vs_headline" in c)
    return {
        "label": "Phase 3 robustness checks (ADR-0007 §7, ADR-0011)",
        "outcome": "low_review (share of 1-2 star reviews, 0-1 scale)",
        "headline": {**headline_from(fe_json), "n_with_review": first_fe["n_sample"] - first_fe["rows_vs_headline"]},
        "rd_main_estimate": rd_main_from(rd_json),
        "spec": spec(),
        "checks": checks,
        "flags_fired": [c["id"] for c in checks if c["fired"]],
    }


def _fmt(x, f="{:.4f}") -> str:
    return "-" if x is None else f.format(x)


def to_markdown(d: dict) -> str:
    h, by = d["headline"], {c["id"]: c for c in d["checks"]}
    fired = {True: "yes", False: "no", None: "n/a"}
    summary = [{"check": f"{c['id']}. {c['label']}", "class": c["class"],
                "estimate": _fmt(c.get("estimate")) if c["id"] not in (4, 5, 6) else "see below",
                "ci95_low": _fmt(c.get("ci95_low")) if c["id"] not in (4, 5, 6) else "",
                "ci95_high": _fmt(c.get("ci95_high")) if c["id"] not in (4, 5, 6) else "",
                "orders_with_review": _fmt(c.get("n_sample"), "{:,}"), "rows_vs_headline": _fmt(c.get("rows_vs_headline"), "{:+,}"),
                "late_orders": _fmt(c.get("late_orders"), "{:,}"), "flag_fired": fired[c["fired"]]} for c in d["checks"]]
    flags = [{"check": c["id"], "rule": c["rule"], "fired": fired[c["fired"]], "if fired": c["if_fired"]} for c in d["checks"]]
    rd_cols = ("estimate", "estimate_bias_corrected", "ci95_low", "ci95_high")
    placebos = [{"cutoff": f"{p['cutoff']:g}", "donut_days": ", ".join(map(str, p["donut_days"])),
                 **{k: _fmt(p[k]) for k in rd_cols}, "n_left": p["n_left"], "n_right": p["n_right"],
                 "days_left": f"{min(p['days_left'])}..{max(p['days_left'])} ({len(p['days_left'])})",
                 "days_right": f"{min(p['days_right'])}..{max(p['days_right'])} ({len(p['days_right'])})"}
                for p in by[4]["placebos"]]
    covs = [{"covariate": c["covariate"], **{k: _fmt(c[k]) for k in rd_cols},
             "robust_ci_excludes_0": "yes" if not _includes_zero(c) else "no"} for c in by[5]["covariates"]]
    s = by[6]
    bounds = [{"benchmark": b["benchmark"], "k": x["k"], "r2dz_x": _fmt(x["r2dz_x"], "{:.6f}"),
               "r2yz_dx": _fmt(x["r2yz_dx"], "{:.6f}"), "adjusted_estimate": _fmt(x["adjusted_estimate"]),
               "adjusted_se": _fmt(x["adjusted_se"]), "ci95_low": _fmt(x["ci95_low"]), "ci95_high": _fmt(x["ci95_high"]),
               "ci_includes_0": "yes" if _includes_zero(x) else "no"} for b in s["benchmarks"] for x in b["bounds"]]
    benchmarks = [{"benchmark": b["benchmark"], "columns": ", ".join(b["columns"]),
                   "r2_with_treatment": _fmt(b["r2dxj_x"], "{:.6f}"), "r2_with_outcome": _fmt(b["r2yxj_dx"], "{:.6f}")}
                  for b in s["benchmarks"]]
    fired_ids = d["flags_fired"]
    return "\n\n".join([
        "# Phase 3 robustness checks",
        "Generated by `make robustness` from `orders.parquet`, `fe.json` and `rd.json`. Outcome: share of 1-2 star "
        "reviews (`low_review`, 0-1 scale). Every check, rule and flag below was fixed in ADR-0011 before this run; "
        "flags are computed by code. Headline (pre-registered FE, ADR-0007): "
        f"{h['estimate']:.4f}, 95% CI [{h['ci95_low']:.4f}, {h['ci95_high']:.4f}], {h['n_with_review']:,} orders with a review.",
        "Classes (ADR-0011 §1): **sample** checks change only which orders enter and fire if the estimate leaves the "
        "headline CI; **estimand** checks change the treatment or use a biased subset and fire against a direction "
        "stated in advance; **diagnostic** checks have their own tests; the **reference** check quotes Phase 2.",
        "## Summary",
        md_table(summary),
        "`rows_vs_headline`: orders with a review in the check's sample minus the headline's. FE checks use model (a) "
        "with the headline's controls, fixed effects and seller-clustered SEs.",
        "## Flags (ADR-0011 §1)",
        md_table(flags),
        f"Flags fired: {', '.join(f'check {i}' for i in fired_ids) if fired_ids else 'none'}.",
        "## Check 4: placebo cutoffs",
        f"Main donut RD (ADR-0008 §3) with the cutoff moved; main RD conventional estimate {d['rd_main_estimate']:.4f}. "
        "Estimate of record: conventional; 95% CI: robust bias-corrected.",
        md_table(placebos),
        "## Check 5: covariate continuity at the promised date",
        "Main donut RD specification with each covariate as the outcome (robust bias-corrected 95% CI).",
        md_table(covs),
        "## Check 6: sensitivity to unobserved confounding",
        f"Cinelli and Hazlett (2020). Headline {s['estimate']:.4f}; seller-clustered SE {s['se_clustered']:.6f}; "
        f"plain-OLS SE {s['se_iid']:.6f}, t {s['t_iid']:.2f}, residual df {s['dof']:,}. Partial R² of late with the "
        f"outcome: {s['r2yd_x']:.6f}. Robustness value RV(q = 1): {s['rv_q1']:.4f}; RV(q = 1, alpha = 0.05): "
        f"{s['rv_q1_alpha05']:.4f}. Bias from plain-OLS partial R² values; adjusted CI from the clustered SE scaled "
        f"by the sensemakr SE factor, critical value {s['crit']:.4f} (ADR-0011 §5).",
        "Benchmark groups (partial R² values from nested plain-OLS fits):",
        md_table(benchmarks),
        "Confounders k times as strong as each benchmark (kd = ky = k); the flag uses k = 1:",
        md_table(bounds),
        "## Check 9: repeat purchase at 180 days",
        f"Phase 2 `repeat_180d/a` (no new model): {by[9]['estimate']:.4f}, 95% CI [{by[9]['ci95_low']:.4f}, "
        f"{by[9]['ci95_high']:.4f}], N {by[9]['n_obs']:,}. The Phase 2 repeat-window flag applies (`ladder.md`).",
        "Notes: check 8 conditions on a consequence of lateness and is biased by design (ADR-0004). Check 7's "
        f"multi-seller orders share one seller fixed effect and cluster (`{C.MULTI_SELLER_LABEL}`).",
        "Figure: `fig_robustness.png` (FE checks against the headline CI).",
    ]) + "\n"


def plot(d: dict, path) -> None:
    h = d["headline"]
    rows = [{"name": "Headline (pre-registered FE)", "kind": "headline", **h}] + [
        {"name": f"{c['id']}. {c['label']}" + ("  [flag fired]" if c["fired"] else ""), "kind": c["class"], **c}
        for c in d["checks"] if c["class"] in ("sample", "estimand")]
    rows = rows[::-1]  # headline on top
    fig, ax = plt.subplots(figsize=(10, 6.4), facecolor=SURFACE)
    ax.axvspan(h["ci95_low"] * 100, h["ci95_high"] * 100, color=SERIES, alpha=0.15, linewidth=0)
    ax.axvline(0, color=INK_2, linewidth=1)
    for y, r in enumerate(rows):
        hollow = r["kind"] == "estimand"
        ax.hlines(y, r["ci95_low"] * 100, r["ci95_high"] * 100, color=SERIES, linewidth=2)
        ax.plot(r["estimate"] * 100, y, "o", markersize=8 if r["kind"] == "headline" else 7,
                markerfacecolor=SURFACE if hollow else SERIES, markeredgecolor=SERIES, markeredgewidth=1.5)
        ax.annotate(f"{r['estimate'] * 100:+.1f}", (max(r["ci95_high"], r["estimate"]) * 100, y), xytext=(6, 0),
                    textcoords="offset points", va="center", color=INK_2, fontsize=9)
    ax.set_yticks(range(len(rows)), [r["name"] for r in rows], color=INK)
    ax.annotate("headline 95% CI", (h["ci95_low"] * 100, -0.45), xytext=(-4, 0), textcoords="offset points",
                ha="right", va="center", color=INK_2, fontsize=9)
    ax.legend(handles=[
        Line2D([], [], marker="o", linestyle="", color=SERIES, label="same estimand: flag if outside the headline CI"),
        Line2D([], [], marker="o", linestyle="", color=SERIES, markerfacecolor=SURFACE,
               label="estimand changes: flag against a stated direction"),
    ], frameon=False, fontsize=9, labelcolor=INK_2, loc="upper left", bbox_to_anchor=(0.03, 1.0))
    ax.set_title("Headline under each robustness check\n"
                 "Late-delivery effect on the 1-2 star share, pp (95% CI)", loc="left", color=INK, fontsize=11)
    ax.set_ylim(-0.6, len(rows))
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.tick_params(axis="y", colors=INK, labelsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)


def main() -> None:
    fe_json, rd_json = (json.loads((C.OUTPUTS_DIR / f"{n}.json").read_text()) for n in ("fe", "rd"))
    result = rounded(build(pd.read_parquet(C.ORDERS_PARQUET), fe_json, rd_json))
    (C.OUTPUTS_DIR / "robustness.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "robustness.md").write_text(to_markdown(result))
    plot(result, C.OUTPUTS_DIR / "fig_robustness.png")
    print("Flags fired: " + (", ".join(f"check {i}" for i in result["flags_fired"]) or "none"))
    print(f"Wrote {C.OUTPUTS_DIR / 'robustness.md'}")


if __name__ == "__main__":
    main()
