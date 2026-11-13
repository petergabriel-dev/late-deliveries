"""Propensity-score matching (T13): a corroborating estimate of the effect on late orders (ATT).

ADR-0007 §3, ADR-0008 §4, ADR-0009. Outcome `low_review` on headline orders with a review.
Orders in a week, category or state level with no late (or no on-time) orders are dropped first
(ADR-0009). Propensity: statsmodels Logit of `late` on the control set minus seller, with week
dummies. Exact match on purchase week; 1:1 nearest neighbour on the logit score, with
replacement; caliper 0.2 SD of the logit score; ties go to the lowest order_id. ATT: weighted OLS
of `low_review` on `late` (controls weighted by times matched), SEs clustered by seller (CRV1).
The SEs ignore the uncertainty from estimating the propensity score.

Writes outputs/matching.json and outputs/matching.md.
"""

import json
import warnings

import numpy as np
import pandas as pd
import pyfixest as pf
import statsmodels.api as sm

from late_delivery import config as C
from late_delivery.diagnostics import md_table, rounded
from late_delivery.fe import CATEGORICAL_CONTROLS, CLUSTER, NUMERIC_CONTROLS, _PValue, analysis_frame

# ADR-0008 §4: control set minus seller; week dummies included.
PS_CATEGORICAL = [*CATEGORICAL_CONTROLS, "purchase_week"]
SE_NOTE = "SEs ignore the uncertainty from estimating the propensity score (ADR-0008 §4)."


def drop_separated(m: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """ADR-0009: drop levels with no late or no on-time orders, and their orders, until none remain."""
    dropped = []
    while True:
        hits = []
        for col in PS_CATEGORICAL:
            g = m.groupby(col)["late"].agg(["sum", "size"])
            for level, r in g[(g["sum"] == 0) | (g["sum"] == g["size"])].iterrows():
                hits.append({"variable": col, "level": str(level), "orders": int(r["size"]), "late_orders": int(r["sum"])})
        if not hits:
            return m, dropped
        bad = np.zeros(len(m), dtype=bool)
        for h in hits:
            bad |= (m[h["variable"]] == h["level"]).to_numpy()
        dropped += hits
        m = m[~bad]


def logit_score(m: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Linear predictor (logit of the propensity score); raises unless the MLE converged."""
    X = pd.get_dummies(m[PS_CATEGORICAL], drop_first=True, dtype=float)
    X = sm.add_constant(pd.concat([m[NUMERIC_CONTROLS], X], axis=1), has_constant="add")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # convergence is checked explicitly below
        r = sm.Logit(m["late"].to_numpy(dtype=float), X).fit(disp=0, maxiter=100)
    score = np.asarray(r.fittedvalues, dtype=float)
    if not r.mle_retvals["converged"] or not np.isfinite(score).all():
        raise RuntimeError("propensity logit did not converge; ADR-0009 requires a new decision")
    return score, {"columns": int(X.shape[1]), "converged": True, "iterations": int(r.mle_retvals["iterations"])}


def nearest_matches(d: pd.DataFrame, caliper: float) -> pd.DataFrame:
    """1:1 nearest neighbour on `score` within `purchase_week`, with replacement.

    Returns one row per matched late order (index labels of `d`). Ties go to the lowest order_id:
    controls are sorted by order_id and argmin returns the first minimum.
    """
    pairs = []
    for week, g in d.groupby("purchase_week", sort=True):
        t = g[g["late"] == 1].sort_values("order_id")
        c = g[g["late"] == 0].sort_values("order_id")
        if t.empty or c.empty:
            continue
        dist = np.abs(t["score"].to_numpy()[:, None] - c["score"].to_numpy()[None, :])
        j = dist.argmin(axis=1)
        best = dist[np.arange(len(t)), j]
        ok = best <= caliper
        pairs.append(pd.DataFrame({"treated": t.index[ok], "control": c.index[j[ok]],
                                   "distance": best[ok], "purchase_week": week}))
    if not pairs:
        raise RuntimeError("no late order found a control within the caliper")
    return pd.concat(pairs, ignore_index=True)


def matched_sample(d: pd.DataFrame, pairs: pd.DataFrame, caliper: float) -> pd.DataFrame:
    """Matched late orders (weight 1) plus controls weighted by times matched; checks ADR-0008 §4."""
    if not pairs["treated"].is_unique:
        raise RuntimeError("a late order was matched more than once")
    if (pairs["distance"] > caliper).any():
        raise RuntimeError("a match exceeds the caliper")
    weeks = d["purchase_week"]
    if not (weeks.loc[pairs["treated"]].to_numpy() == weeks.loc[pairs["control"]].to_numpy()).all():
        raise RuntimeError("a match crosses purchase weeks")
    w = pairs["control"].value_counts().sort_index()
    out = pd.concat([d.loc[pairs["treated"]].assign(w=1.0), d.loc[w.index].assign(w=w.to_numpy(dtype=float))])
    if out.loc[out["late"] == 0, "w"].sum() != len(pairs):
        raise RuntimeError("control weights do not sum to the matched late count")
    return out


def att(ms: pd.DataFrame) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = pf.feols("low_review ~ late", data=ms, weights="w", vcov={"CRV1": CLUSTER})
    ci = r.confint()
    late = ms["late"] == 1
    direct = ms.loc[late, "low_review"].mean() - np.average(ms.loc[~late, "low_review"], weights=ms.loc[~late, "w"])
    if not np.isclose(direct, r.coef()["late"]):
        raise RuntimeError("weighted OLS does not reproduce the matched mean difference")
    return {
        "estimate": float(r.coef()["late"]), "se": float(r.se()["late"]),
        "ci95_low": float(ci.loc["late"].iloc[0]), "ci95_high": float(ci.loc["late"].iloc[1]),
        "p_value": float(r.pvalue()["late"]), "clusters": int(ms[CLUSTER].nunique()),
        "mean_late": float(ms.loc[late, "low_review"].mean()),
        "mean_control_weighted": float(np.average(ms.loc[~late, "low_review"], weights=ms.loc[~late, "w"])),
    }


def balance(d: pd.DataFrame, ms: pd.DataFrame) -> list[dict]:
    """SMD per numeric control and per category/state level; denominator = pre-match pooled SD."""
    cov = pd.concat([d[NUMERIC_CONTROLS], pd.get_dummies(d[CATEGORICAL_CONTROLS], dtype=float)], axis=1)
    late = d["late"] == 1
    sd = np.sqrt((cov[late].var() + cov[~late].var()) / 2)
    t_idx, c = ms.index[ms["late"] == 1], ms[ms["late"] == 0]
    after_t = cov.loc[t_idx].mean()
    after_c = pd.Series(np.average(cov.loc[c.index], weights=c["w"], axis=0), index=cov.columns)
    rows = []
    for col in cov.columns:
        s = sd[col]
        rows.append({
            "covariate": col, "mean_late": float(after_t[col]), "mean_control_matched": float(after_c[col]),
            "smd_before": float((cov.loc[late, col].mean() - cov.loc[~late, col].mean()) / s) if s > 0 else 0.0,
            "smd_after": float((after_t[col] - after_c[col]) / s) if s > 0 else 0.0,
        })
    return sorted(rows, key=lambda r: (-abs(round(r["smd_after"], 6)), r["covariate"]))


def run(m0: pd.DataFrame) -> dict:
    """Matching on the model sample `m0` (headline orders with a review)."""
    d, dropped = drop_separated(m0)
    score, logit = logit_score(d)
    d = d.assign(score=score)
    caliper = C.MATCH_CALIPER_SD * float(d["score"].std())
    pairs = nearest_matches(d, caliper)
    ms = matched_sample(d, pairs, caliper)
    bal = balance(d, ms)
    n_late = int((d["late"] == 1).sum())
    return {
        "att": att(ms),
        "sample": {
            "orders_before_separation_drop": len(m0),
            "orders_dropped_separation": len(m0) - len(d),
            "late_orders_dropped_separation": int(m0["late"].sum() - d["late"].sum()),
            "separated_levels": dropped,
            "orders": len(d), "late_orders": n_late,
            "matched_late": len(pairs), "unmatched_late": n_late - len(pairs),
            "distinct_controls_used": int(pairs["control"].nunique()),
            "max_control_weight": int(pairs["control"].value_counts().max()),
            "weeks_with_matches": int(pairs["purchase_week"].nunique()),
        },
        "propensity": {**logit, "score_sd": float(d["score"].std()), "caliper_sd": C.MATCH_CALIPER_SD, "caliper": caliper},
        "balance": {"max_abs_smd_after": max(abs(r["smd_after"]) for r in bal),
                    "covariates_above_0.1_after": sum(abs(r["smd_after"]) > 0.1 for r in bal),
                    "covariates": len(bal), "table": bal},
    }


def to_markdown(d: dict) -> str:
    a, s, p, b = d["att"], d["sample"], d["propensity"], d["balance"]
    num = "{:.4f}"
    return "\n\n".join([
        "# Propensity-score matching",
        "Generated by `make matching`. **Corroborating estimate, not the headline** (ADR-0007 §3-4): effect of a late "
        "delivery on the share of 1-2 star reviews (`low_review`, 0-1 scale) among matched late orders (ATT). "
        "Specification: ADR-0008 §4 and ADR-0009. Unlike the headline, matching has no seller fixed effects.",
        md_table([{"estimate": a["estimate"], "se": a["se"], "ci95_low": a["ci95_low"], "ci95_high": a["ci95_high"],
                   "p_value": _PValue(a["p_value"]), "matched_late": s["matched_late"], "clusters": a["clusters"]}],
                 {c: num for c in ("estimate", "se", "ci95_low", "ci95_high")} | {"p_value": "{:.3g}"}),
        f"95% CI from weighted OLS with SEs clustered by seller (CRV1). {SE_NOTE} Matched late orders: "
        f"{a['mean_late']:.4f} low-review share; their weighted matched controls: {a['mean_control_weighted']:.4f}.",
        "## Sample",
        f"Headline orders with a review: {s['orders_before_separation_drop']:,}. Dropped before fitting because their "
        f"week, category or state has no late orders (ADR-0009): {s['orders_dropped_separation']:,} orders "
        f"({s['late_orders_dropped_separation']} late). Remaining: {s['orders']:,} orders, {s['late_orders']:,} late.",
        md_table(s["separated_levels"]) if s["separated_levels"] else "No level was dropped.",
        f"Matched late orders: {s['matched_late']:,}; unmatched (no control in the same week within the caliper): "
        f"{s['unmatched_late']:,}. Distinct controls used: {s['distinct_controls_used']:,} (most uses of one control: "
        f"{s['max_control_weight']}). Weeks with matches: {s['weeks_with_matches']}.",
        "## Propensity model",
        f"statsmodels Logit of `late` on {', '.join(NUMERIC_CONTROLS)} and dummies for {', '.join(PS_CATEGORICAL)} "
        f"({p['columns']} columns with the constant); converged in {p['iterations']} iterations. Logit-score SD "
        f"{p['score_sd']:.4f}; caliper {p['caliper_sd']:g} SD = {p['caliper']:.4f}.",
        "## Balance (standardized mean differences)",
        f"Pre-match pooled SD as denominator; matched controls weighted by times matched. Week is matched exactly. "
        f"Max |SMD| after matching: {b['max_abs_smd_after']:.4f}; covariates with |SMD| > 0.1 after matching: "
        f"{b['covariates_above_0.1_after']} of {b['covariates']}.",
        md_table(b["table"], {c: "{:.4f}" for c in ("mean_late", "mean_control_matched")}
                 | {c: "{:+.4f}" for c in ("smd_before", "smd_after")}),
    ]) + "\n"


def main() -> None:
    f = analysis_frame(pd.read_parquet(C.ORDERS_PARQUET))
    result = rounded({
        "label": "Propensity-score matching (ADR-0007 §3, ADR-0008 §4, ADR-0009); corroborating",
        "spec": {
            "outcome": "low_review", "estimand": "ATT on matched late orders", "sample": "headline orders with a review",
            "propensity": "statsmodels Logit; control set minus seller, week dummies included",
            "matching": "exact on purchase_week; 1:1 nearest neighbour on the logit score with replacement; "
                        "ties to the lowest order_id",
            "estimator": "weighted OLS low_review ~ late (pyfixest, aweights = times matched)",
            "vcov": "CRV1 clustered by seller_id", "se_note": SE_NOTE,
        },
        **run(f[f["has_review"]].reset_index(drop=True)),
    })
    C.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (C.OUTPUTS_DIR / "matching.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "matching.md").write_text(to_markdown(result))
    a, s, b = result["att"], result["sample"], result["balance"]
    print(f"Matching ATT: {a['estimate']:+.4f} [95% CI {a['ci95_low']:+.4f}, {a['ci95_high']:+.4f}], "
          f"matched late {s['matched_late']:,}, unmatched {s['unmatched_late']:,}, max |SMD| {b['max_abs_smd_after']:.4f}")
    print(f"Wrote {C.OUTPUTS_DIR / 'matching.md'}")


if __name__ == "__main__":
    main()
