"""Fixed-effects regression grid (T11): the pre-registered headline and its secondary models.

ADR-0007 §1 and §3, ADR-0008 §1-2. Linear probability models (OLS) with seller and
purchase-week fixed effects (pyfixest), singleton groups dropped, SEs clustered by seller
(CRV1), 95% CIs. Primary estimate: coefficient on `late` in model (a), outcome `low_review`.

`analysis_frame()` is the shared analysis-time frame (also used by matching): headline rows,
log1p price and freight, distance cap/fill/flag, and treatment bins. build.py is unchanged.

Writes outputs/fe.json and outputs/fe.md.
"""

import json
import warnings

import numpy as np
import pandas as pd
import pyfixest as pf

from late_delivery import config as C
from late_delivery.diagnostics import md_table, repeat_mde, rounded

# ADR-0007 §1: controls besides the absorbed seller and purchase-week fixed effects.
CATEGORICAL_CONTROLS = ["main_category", "customer_state"]
NUMERIC_CONTROLS = ["log_price", "log_freight", "n_items", "distance_km", "distance_missing", "promised_days"]
CONTROLS = " + ".join([f"C({c})" for c in CATEGORICAL_CONTROLS] + NUMERIC_CONTROLS)
FIXED_EFFECTS = "seller_id + purchase_week"
CLUSTER = "seller_id"


def _bin_name(prefix: str, lo: int, hi_inclusive: int | None) -> str:
    return f"{prefix}_{lo}p" if hi_inclusive is None else f"{prefix}_{lo}_{hi_inclusive}"


LATE_BIN_COLS = [_bin_name("late", lo, hi) for lo, hi in C.LATE_BINS]
# Delivery bins are [lo, hi), so the label's upper day is hi - 1 ("8-14" = [8, 15)).
DELIVERY_BIN_COLS = [_bin_name("dd", lo, None if hi is None else hi - 1) for lo, hi in C.DELIVERY_DAY_BINS]
DELIVERY_REF_COL, DELIVERY_BIN_TERMS = DELIVERY_BIN_COLS[0], DELIVERY_BIN_COLS[1:]

# ADR-0007 §3 / ADR-0008 §2: model id -> (label, regressors of interest, on-time orders only).
MODELS = {
    "a": ("binary late (total effect)", ["late"], False),
    "b": ("days-late bins (total effect)", LATE_BIN_COLS, False),
    "c": ("binary late + delivery_days (broken promise holding speed)", ["late", "delivery_days"], False),
    "d": ("days-late bins + delivery_days (broken promise holding speed)", LATE_BIN_COLS + ["delivery_days"], False),
    "e": ("slowness: delivery-days bins, on-time orders", DELIVERY_BIN_TERMS, True),
}
# Outcome -> (sample column, sample description).
OUTCOMES = {
    "low_review": ("has_review", "headline orders with a review"),
    "review_score": ("has_review", "headline orders with a review"),
    **{f"repeat_{w}d": (f"repeat_{w}d_sample", f"headline first orders eligible for {w} days") for w in C.REPEAT_WINDOWS},
}
STARS = range(1, 6)


def _float(s: pd.Series) -> np.ndarray:
    """Nullable (boolean/Int64) or plain column -> float64 with NaN for missing."""
    return s.astype("Float64").to_numpy(dtype=float, na_value=np.nan)


def analysis_frame(t: pd.DataFrame) -> pd.DataFrame:
    """Headline orders with the analysis-time controls and treatment bins (ADR-0008 §1-2)."""
    h = t[t["in_headline"]].reset_index(drop=True)
    dist = h["distance_km"].where(h["distance_km"] <= C.DISTANCE_CAP_KM)
    f = pd.DataFrame({
        "order_id": h["order_id"].astype(str),
        "seller_id": h["seller_id"].astype(str),
        "purchase_week": h["purchase_week"].dt.strftime("%Y-%m-%d"),
        "main_category": h["main_category"].astype(str),
        "customer_state": h["customer_state"].astype(str),
        "log_price": np.log1p(_float(h["price"])),
        "log_freight": np.log1p(_float(h["freight"])),
        "n_items": _float(h["n_items"]),
        "distance_km": dist.fillna(dist.median()).to_numpy(dtype=float),
        "distance_missing": dist.isna().to_numpy(dtype=float),
        "promised_days": _float(h["promised_days"]),
        "late": _float(h["late"]),
        "days_late": _float(h["days_late"]),
        "delivery_days": _float(h["delivery_days"]),
        "low_review": _float(h["low_review"]),
        "review_score": _float(h["review_score"]),
    })
    f["has_review"] = f["review_score"].notna()
    for k in STARS:
        f[f"star_{k}"] = (f["review_score"] == k).astype(float).where(f["has_review"])
    for w in C.REPEAT_WINDOWS:
        f[f"repeat_{w}d"] = _float(h[f"repeat_{w}d"])
        f[f"repeat_{w}d_sample"] = (h["is_first_order"] & h[f"repeat_{w}d_eligible"]).to_numpy(dtype=bool)
    for col, (lo, hi) in zip(LATE_BIN_COLS, C.LATE_BINS):
        f[col] = f["days_late"].between(lo, np.inf if hi is None else hi).astype(float)
    for col, (lo, hi) in zip(DELIVERY_BIN_COLS, C.DELIVERY_DAY_BINS):
        f[col] = ((f["delivery_days"] >= lo) & (f["delivery_days"] < (np.inf if hi is None else hi))).astype(float)

    required = ["seller_id", "purchase_week", *CATEGORICAL_CONTROLS, *NUMERIC_CONTROLS, "late", "days_late", "delivery_days"]
    bad = [c for c in required if f[c].isna().any() or (f[c] == "nan").any()]
    if bad:
        raise ValueError(f"missing values in analysis columns after frame prep: {bad}")
    for w in C.REPEAT_WINDOWS:
        if f.loc[f[f"repeat_{w}d_sample"], f"repeat_{w}d"].isna().any():
            raise ValueError(f"repeat_{w}d missing for an eligible first order")
    return f


def model_specs() -> list[dict]:
    """The 25 pre-registered FE models: 4 outcomes x models (a)-(e), plus 5 star-level outcomes in (a)."""
    specs = []
    for outcome, (sample, sample_desc) in OUTCOMES.items():
        for mid, (label, terms, on_time_only) in MODELS.items():
            primary = outcome == "low_review" and mid == "a"
            specs.append({
                "id": f"{outcome}/{mid}", "outcome": outcome, "model": mid, "model_label": label, "terms": terms,
                "sample": sample, "on_time_only": on_time_only,
                "sample_description": sample_desc + (", on time only" if on_time_only else ""),
                "role": "pre-registered primary" if primary else "secondary",
            })
    for k in STARS:
        specs.append({
            "id": f"star_{k}/a", "outcome": f"star_{k}", "model": "a", "model_label": MODELS["a"][0],
            "terms": MODELS["a"][1], "sample": "has_review", "on_time_only": False,
            "sample_description": "headline orders with a review",
            "role": "secondary (ADR-0004 star-distribution check)",
        })
    return specs


def fit(f: pd.DataFrame, outcome: str, terms: list[str]) -> dict:
    """OLS with seller + week FE, singletons dropped, CRV1 by seller. `f` is the model sample."""
    if f[outcome].isna().any():
        raise ValueError(f"{outcome} has missing values inside its model sample")
    fml = f"{outcome} ~ {' + '.join(terms)} + {CONTROLS} | {FIXED_EFFECTS}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pyfixest announces singleton drops; counted below
        m = pf.feols(fml, data=f, vcov={"CRV1": CLUSTER}, fixef_rm="singleton")
    dropped = [x for x in terms + NUMERIC_CONTROLS if x not in m._coefnames]
    if any(x in dropped for x in terms):
        raise RuntimeError(f"{fml}: regressor of interest dropped as collinear: {dropped}")
    est = m._data
    coef, se, p, ci = m.coef(), m.se(), m.pvalue(), m.confint()
    return {
        "formula": fml,
        "n_sample": len(f),
        "n_obs": int(m._N),
        "singleton_rows_dropped": len(f) - int(m._N),
        "clusters": int(est[CLUSTER].nunique()),
        "weeks": int(est["purchase_week"].nunique()),
        "outcome_mean": float(est[outcome].mean()),
        "collinear_controls_dropped": dropped,
        "estimates": [
            {"term": x, "estimate": float(coef[x]), "se": float(se[x]),
             "ci95_low": float(ci.loc[x].iloc[0]), "ci95_high": float(ci.loc[x].iloc[1]), "p_value": float(p[x])}
            for x in terms
        ],
    }


def run_grid(f: pd.DataFrame) -> list[dict]:
    rows = []
    for s in model_specs():
        mask = f[s["sample"]].astype(bool)
        if s["on_time_only"]:
            mask = mask & (f["late"] == 0)
        r = {k: s[k] for k in ("id", "outcome", "model", "model_label", "role", "sample_description")}
        rows.append(r | fit(f[mask], s["outcome"], s["terms"]))
    return rows


def bin_counts(f: pd.DataFrame) -> dict:
    on_time = f["late"] == 0
    return {
        "late_bins": {c: int(f[c].sum()) for c in LATE_BIN_COLS},
        "delivery_bins_on_time": {c: int(f.loc[on_time, c].sum()) for c in DELIVERY_BIN_COLS},
    }


def repeat_reading(models: list[dict], mde: list[dict]) -> list[dict]:
    """ADR-0004: a repeat CI that includes zero is read as an upper bound."""
    by_id = {m["id"]: m for m in models}
    rows = []
    for m_row in mde:
        w = m_row["window_days"]
        e = by_id[f"repeat_{w}d/a"]["estimates"][0]
        includes_zero = e["ci95_low"] <= 0 <= e["ci95_high"]
        rows.append({
            "outcome": f"repeat_{w}d", "estimate": e["estimate"], "ci95_low": e["ci95_low"], "ci95_high": e["ci95_high"],
            "phase1_mde": m_row["mde_pp"] / 100, "reading": "upper bound (CI includes 0)" if includes_zero else "measured",
        })
    return rows


class _PValue(float):
    """p-values below the JSON's 6-decimal precision render as '<1e-06', not '0'."""

    def __format__(self, spec: str) -> str:
        return "<1e-06" if self < 1e-6 else format(float(self), spec)


def to_markdown(d: dict) -> str:
    num = "{:.4f}"
    fmt = {c: num for c in ("estimate", "se", "ci95_low", "ci95_high", "outcome_mean", "phase1_mde")} | {"p_value": "{:.3g}"}
    d = {**d, "models": [{**m, "estimates": [{**e, "p_value": _PValue(e["p_value"])} for e in m["estimates"]]}
                         for m in d["models"]]}
    p = d["primary"]
    sections = [
        "# Fixed-effects regression grid",
        "Generated by `make fe`. Linear probability models (OLS) on the headline sample with seller and "
        "purchase-week fixed effects; singleton groups dropped; standard errors clustered by seller (CRV1); "
        "95% confidence intervals from a t distribution with (clusters - 1) degrees of freedom. "
        "Specification: ADR-0007 sections 1 and 3, ADR-0008 sections 1-2.",
        f"Controls: {', '.join(CATEGORICAL_CONTROLS)} (dummies), {', '.join(NUMERIC_CONTROLS)}. Price and freight "
        f"enter as log(1 + x). Distance over {d['spec']['distance_cap_km']:,.0f} km is treated as missing "
        f"({d['spec']['distance_capped_orders']} orders). All {d['spec']['distance_missing_orders']} orders with "
        f"missing distance, those included, get the median, {d['spec']['distance_fill_km']:.1f} km, and a "
        "`distance_missing` flag.",
        "## Pre-registered primary estimate",
        "Effect of a late delivery on the share of 1-2 star reviews (`low_review`, 0-1 scale), model (a).",
        md_table([{"term": p["term"], "estimate": p["estimate"], "se": p["se"], "ci95_low": p["ci95_low"],
                   "ci95_high": p["ci95_high"], "p_value": p["p_value"], "n_obs": p["n_obs"], "clusters": p["clusters"]}], fmt),
        "## All models (secondary unless marked)",
        "Models: (a) binary late; (b) days-late bins 1-2, 3-7, 8-14, 15+ vs on time; (c) and (d) add a linear "
        "`delivery_days` control (broken promise holding speed); (e) delivery-days bins 8-14, 15-21, 22+ vs 0-7 "
        "among on-time orders (slowness). `low_review`, `repeat_*` and `star_*` are shares (0-1); "
        "`review_score` is on the 1-5 scale.",
    ]
    for outcome in [*OUTCOMES, "star"]:
        rows = [{"model": m["id"], "role": m["role"], **e} for m in d["models"]
                if m["outcome"] == outcome or (outcome == "star" and m["outcome"].startswith("star_")) for e in m["estimates"]]
        title = "Star-distribution check (ADR-0004): 1[score = k], model (a)" if outcome == "star" else f"`{outcome}`"
        sections += [f"### {title}", md_table(rows, fmt)]
    sections += [
        "## Repeat purchase against the Phase 1 minimum detectable effect",
        "Model (a) on eligible first orders. A confidence interval that includes zero is read as an upper bound (ADR-0004).",
        md_table(d["repeat_reading"], fmt),
        "## Specification echo",
        md_table([{k: m[k] for k in ("id", "n_sample", "n_obs", "singleton_rows_dropped", "clusters", "weeks", "outcome_mean")}
                  for m in d["models"]], fmt),
        "Formula for every model: `<outcome> ~ <terms> + " + CONTROLS + " | " + FIXED_EFFECTS + "`. "
        "Collinear numeric controls dropped: "
        + (", ".join(sorted({x for m in d["models"] for x in m["collinear_controls_dropped"]})) or "none") + ".",
    ]
    return "\n\n".join(sections) + "\n"


def main() -> None:
    t = pd.read_parquet(C.ORDERS_PARQUET)
    f = analysis_frame(t)
    models = run_grid(f)
    primary = next(m for m in models if m["role"] == "pre-registered primary")
    dist = t.loc[t["in_headline"], "distance_km"]
    result = rounded({
        "label": "Fixed-effects regression grid (ADR-0007 §3, ADR-0008 §2)",
        "spec": {
            "estimator": "OLS linear probability model, pyfixest feols",
            "fixed_effects": FIXED_EFFECTS.split(" + "),
            "categorical_controls": CATEGORICAL_CONTROLS,
            "numeric_controls": NUMERIC_CONTROLS,
            "vcov": "CRV1 clustered by seller_id",
            "ci": "95%, t with clusters - 1 df",
            "singletons": "dropped (fixef_rm='singleton')",
            "distance_cap_km": C.DISTANCE_CAP_KM,
            "distance_capped_orders": int((dist > C.DISTANCE_CAP_KM).sum()),
            "distance_missing_orders": int(f["distance_missing"].sum()),
            "distance_fill_km": float(f.loc[f["distance_missing"] == 0, "distance_km"].median()),
            "headline_orders": len(f),
            "models": len(models),
        },
        "bin_counts": bin_counts(f),
        "primary": {"id": primary["id"], **primary["estimates"][0], "n_obs": primary["n_obs"], "clusters": primary["clusters"]},
        "models": models,
        "repeat_reading": repeat_reading(models, repeat_mde(t[t["in_headline"]])),
    })
    C.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (C.OUTPUTS_DIR / "fe.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "fe.md").write_text(to_markdown(result))
    p = result["primary"]
    print(f"Primary (low_review, model a): late = {p['estimate']:+.4f} "
          f"[95% CI {p['ci95_low']:+.4f}, {p['ci95_high']:+.4f}], n = {p['n_obs']:,}, sellers = {p['clusters']:,}")
    print(f"Wrote {C.OUTPUTS_DIR / 'fe.md'} ({len(models)} models)")


if __name__ == "__main__":
    main()
