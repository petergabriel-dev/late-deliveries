"""Phase 1 design diagnostics (T6): can the planned designs work on this data?

No outcome is split by treatment (invariant 3). review_score and low_review are never
loaded. The only outcome statistic is the pooled repeat-purchase base rate, used for
the minimum detectable effect. review_created_before_delivery is a survey-timing
mechanism (timestamps), not a satisfaction outcome.

Writes outputs/diagnostics.json, outputs/diagnostics.md and two PNG figures.
"""

import json
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from rddensity import rddensity  # noqa: E402

from late_delivery import config as C  # noqa: E402
from late_delivery.build import exclusion_counts  # noqa: E402

COLUMNS = [  # invariant 3 guard: review_score and low_review deliberately absent
    "order_id", "purchase_month", "bf_2017", "days_late", "late", "review_created_before_delivery",
    "is_first_order", "repeat_90d_eligible", "repeat_90d", "repeat_180d_eligible", "repeat_180d",
    "price", "freight", "n_items", "distance_km", "promised_days", "customer_state", "seller_state",
    "main_category", "seller_id", "exclusion_reason", "in_headline",
]
Z_ALPHA, Z_POWER = 1.959964, 0.841621  # two-sided alpha = 0.05, power = 0.80
RV_RANGE = range(-15, 16)
BANDWIDTHS = (5, 7, 10)
SURVEY_BUCKETS = [(-np.inf, 0, "<= 0 (on time)"), (1, 1, "1"), (2, 2, "2"), (3, 3, "3"),
                  (4, 7, "4-7"), (8, 14, "8-14"), (15, np.inf, "15+")]

# Reference palette (dataviz skill), light mode; single-series charts need one hue.
SERIES, INK, INK_2, GRID, SURFACE = "#2a78d6", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def monthly(h: pd.DataFrame) -> pd.DataFrame:
    g = h.groupby("purchase_month")
    return pd.DataFrame({"orders": g.size(), "late_share": g["late"].mean().astype(float)})


def density_tests(h: pd.DataFrame) -> list[dict]:
    """rddensity at the cutoff between day 0 and day +1 (c=1: X >= 1 is late)."""
    x = h["days_late"].astype(float).to_numpy()
    rows = []
    specs = [(p, bw) for p in (1, 2) for bw in BANDWIDTHS] + [(2, None)]
    for p, bw in specs:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # mass-point notices; massPoints=True handles them
            r = rddensity(X=x, c=1, p=p, h=[bw, bw] if bw else [])
        rows.append({
            "poly_order": p,
            "bandwidth_days": bw if bw else f"auto ({float(r.h['left']):g})",
            "density_left": float(r.hat["left"]),
            "density_right": float(r.hat["right"]),
            "t_jackknife": float(r.test["t_jk"]),
            "p_value": float(r.test["p_jk"]),
        })
    return rows


def survey_timing(h: pd.DataFrame) -> list[dict]:
    r = h.dropna(subset=["review_created_before_delivery"])
    rows = []
    for lo, hi, label in SURVEY_BUCKETS:
        s = r[r["days_late"].between(lo, hi)]
        rows.append({"days_late": label, "reviews": len(s),
                     "created_before_delivery_share": float(s["review_created_before_delivery"].astype(float).mean())})
    return rows


def smd(a: pd.Series, b: pd.Series) -> float:
    a, b = a.dropna().astype(float), b.dropna().astype(float)
    pooled_sd = np.sqrt((a.var() + b.var()) / 2)
    return float((a.mean() - b.mean()) / pooled_sd) if pooled_sd > 0 else 0.0


def covariate_balance(h: pd.DataFrame) -> list[dict]:
    late = h["late"].astype(bool)
    top_categories = h["main_category"].value_counts().index[:5]
    covariates = {
        "price": h["price"], "freight": h["freight"], "n_items": h["n_items"],
        "distance_km": h["distance_km"], "promised_days": h["promised_days"], "bf_2017": h["bf_2017"],
        "customer_state_SP": h["customer_state"].eq("SP"), "seller_state_SP": h["seller_state"].eq("SP"),
        **{f"category_{c}": h["main_category"].eq(c) for c in top_categories},
    }
    return [{"covariate": k, "mean_late": float(v[late].astype(float).mean()),
             "mean_on_time": float(v[~late].astype(float).mean()), "smd": smd(v[late], v[~late])}
            for k, v in covariates.items()]


def seller_support(h: pd.DataFrame) -> dict:
    s = h.groupby("seller_id")["late"].agg(["sum", "size"])
    both = s[(s["sum"] > 0) & (s["sum"] < s["size"])]
    return {
        "sellers": len(s),
        "sellers_with_late_and_on_time": len(both),
        "late_orders_at_those_sellers_share": float(both["sum"].sum() / s["sum"].sum()),
        "orders_at_those_sellers_share": float(both["size"].sum() / s["size"].sum()),
    }


def repeat_mde(h: pd.DataFrame) -> list[dict]:
    rows = []
    for w in C.REPEAT_WINDOWS:
        e = h[h["is_first_order"] & h[f"repeat_{w}d_eligible"]]
        n_late = int(e["late"].sum())
        n_on_time = len(e) - n_late
        p = float(e[f"repeat_{w}d"].astype(float).mean())  # pooled over both arms: power input only
        mde = (Z_ALPHA + Z_POWER) * np.sqrt(p * (1 - p) * (1 / n_late + 1 / n_on_time))
        rows.append({"window_days": w, "eligible_first_orders": len(e), "late": n_late, "on_time": n_on_time,
                     "pooled_base_rate": p, "mde_pp": float(100 * mde), "mde_relative": float(mde / p)})
    return rows


def _style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)


def plot_monthly(m: pd.DataFrame, path) -> None:
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, facecolor=SURFACE)
    x = np.arange(len(m))
    top.bar(x, m["orders"], width=0.6, color=SERIES)
    top.set_title("Headline orders per purchase month", loc="left", color=INK, fontsize=11)
    bottom.plot(x, m["late_share"] * 100, color=SERIES, linewidth=2, marker="o", markersize=4)
    bottom.set_title("Share delivered after the promised date (%)", loc="left", color=INK, fontsize=11)
    bf = list(m.index).index(C.BLACK_FRIDAY_2017.strftime("%Y-%m"))
    top.annotate("Black Friday 2017", (bf, m["orders"].iloc[bf]), xytext=(0, 6), textcoords="offset points",
                 ha="center", color=INK_2, fontsize=9)
    for ax in (top, bottom):
        _style(ax)
    bottom.set_xticks(x, m.index, rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)


def plot_running_variable(counts: dict, path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4), facecolor=SURFACE)
    days = list(counts)
    ax.bar(days, list(counts.values()), width=0.6, color=SERIES)
    ax.axvline(0.5, color=INK_2, linestyle="--", linewidth=1)
    ax.annotate("promised date", (0.5, max(counts.values())), xytext=(6, -2), textcoords="offset points",
                color=INK_2, fontsize=9, va="top")
    ax.set_title("Headline orders by days late (delivery date minus promised date)", loc="left", color=INK, fontsize=11)
    ax.set_xticks(days[::5])
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)


def _rounded(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _rounded(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rounded(v) for v in obj]
    return obj


def _md_table(rows: list[dict], fmt: dict | None = None) -> str:
    fmt = fmt or {}
    cols = list(rows[0])
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(fmt.get(c, "{}").format(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def to_markdown(d: dict) -> str:
    ex = d["exclusions"]
    m = d["monthly"]
    rv = d["running_variable_counts"]
    pct = "{:.1%}"
    return "\n\n".join([
        "# Phase 1 design diagnostics",
        "Generated by `make diagnostics`. No review score or repeat-purchase outcome is compared between "
        "late and on-time orders here (invariant 3); the only outcome statistic is the pooled repeat base "
        "rate used for power.",
        "## 1. Exclusion waterfall",
        _md_table([{"step": e["reason"], "orders_removed": e["orders"]} for e in ex["excluded"]]
                  + [{"step": "in headline sample", "orders_removed": ex["in_headline"]}]),
        f"Total orders: {ex['total_orders']:,}. Headline late orders: {d['headline']['late']:,} "
        f"({d['headline']['late_share']:.2%}).",
        "## 2. Monthly volume and late share (headline sample)",
        _md_table([{"month": k, "orders": v["orders"], "late_share": v["late_share"]} for k, v in m.items()],
                  {"late_share": pct}),
        "Figure: `fig_monthly.png`.",
        "## 3. Running variable and density test at the promised date",
        _md_table([{"days_late": k, "orders": v} for k, v in rv.items()]),
        "Figure: `fig_days_late.png`. Test: `rddensity` (Cattaneo, Jansson, Ma), cutoff c = 1 "
        "(day +1 and later = late), mass-point adjustment on. A significant difference means the density "
        "of orders changes at the promised date.",
        _md_table(d["density_tests"], {"density_left": "{:.5f}", "density_right": "{:.5f}",
                                      "t_jackknife": "{:.2f}", "p_value": "{:.2g}"}),
        "Read with care: the estimates swing with bandwidth and polynomial order (sign and significance "
        "change across rows), because the count of orders falls sharply at days -6/-5, inside the wider "
        "windows. The automatic bandwidth returns an invalid negative density. The raw counts are the "
        f"steadier evidence: orders fall {-d['cutoff_step']['day_0_to_1']:.0%} from day 0 to day +1, versus "
        f"an average fall of {-d['cutoff_step']['mean_step_day_-5_to_0']:.0%} per day over the five days before.",
        "## 4. Survey timing: share of reviews created before delivery, by days late",
        _md_table(d["survey_timing"], {"created_before_delivery_share": pct}),
        "## 5. Covariate balance, late vs on-time (standardized mean difference)",
        _md_table(d["covariate_balance"], {"mean_late": "{:.3f}", "mean_on_time": "{:.3f}", "smd": "{:+.3f}"}),
        "|SMD| > 0.1 is a common flag for imbalance worth adjusting for.",
        "## 6. Seller support for seller fixed effects",
        _md_table([d["seller_support"]], {"late_orders_at_those_sellers_share": pct,
                                          "orders_at_those_sellers_share": pct}),
        "## 7. Repeat purchase: minimum detectable effect (naive two-arm, alpha 0.05, power 0.80)",
        _md_table(d["repeat_mde"], {"pooled_base_rate": "{:.2%}", "mde_pp": "{:.2f}", "mde_relative": pct}),
        "MDE in percentage points; relative = MDE / pooled base rate. Controls and matching reduce power "
        "further, so these are best cases.",
    ]) + "\n"


def main() -> None:
    t = pd.read_parquet(C.ORDERS_PARQUET, columns=COLUMNS)
    h = t[t["in_headline"]]
    counts = h["days_late"].value_counts()
    rv_counts = {int(dd): int(counts.get(dd, 0)) for dd in RV_RANGE}
    m = monthly(h)
    result = _rounded({
        "exclusions": exclusion_counts(t),
        "headline": {"orders": len(h), "late": int(h["late"].sum()), "late_share": float(h["late"].mean())},
        "monthly": {k: {"orders": int(r.orders), "late_share": float(r.late_share)} for k, r in m.iterrows()},
        "running_variable_counts": {str(k): v for k, v in rv_counts.items()},
        "density_tests": density_tests(h),
        "cutoff_step": {
            "day_0_to_1": rv_counts[1] / rv_counts[0] - 1,
            "mean_step_day_-5_to_0": float(np.mean([rv_counts[dd + 1] / rv_counts[dd] - 1 for dd in range(-5, 0)])),
        },
        "survey_timing": survey_timing(h),
        "covariate_balance": covariate_balance(h),
        "seller_support": seller_support(h),
        "repeat_mde": repeat_mde(h),
    })
    C.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (C.OUTPUTS_DIR / "diagnostics.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "diagnostics.md").write_text(to_markdown(result))
    plot_monthly(m, C.OUTPUTS_DIR / "fig_monthly.png")
    plot_running_variable(rv_counts, C.OUTPUTS_DIR / "fig_days_late.png")
    print(f"Wrote {C.OUTPUTS_DIR / 'diagnostics.md'}")


if __name__ == "__main__":
    main()
