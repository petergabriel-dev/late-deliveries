"""Donut regression discontinuity at the promised date (T12): a corroborating estimate.

ADR-0007 §3 and ADR-0008 §3. Outcome `low_review` on headline orders with a review; running
variable `days_late`; cutoff 0.5 (day +1 and later are late); local-linear fit, triangular
kernel, fixed bandwidth; donut drops days 0 and +1; rdrobust with mass-point adjustment and
SEs clustered by seller (CR1). Reported: the conventional estimate with the robust
bias-corrected 95% CI as the CI of record.

Caveat: local to orders near the promised date, and from day 3 on most late-order reviews are
written before the order arrives (survey timing, traps.md), so the right side mixes in the
waiting experience.

Writes outputs/rd.json, outputs/rd.md and outputs/fig_rd.png.
"""

import contextlib
import io
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from rdrobust import rdrobust  # noqa: E402

from late_delivery import config as C  # noqa: E402
from late_delivery.diagnostics import INK, INK_2, SERIES, SURFACE, _style, md_table, rounded  # noqa: E402
from late_delivery.fe import analysis_frame  # noqa: E402

# ADR-0008 §3: main specification first, then the pre-registered sensitivity runs.
SPECS = [
    {"spec": "main", "bandwidth": C.RD_BANDWIDTH, "donut": True, "role": "corroborating (ADR-0007 §3)"},
    *[{"spec": f"h = {h:g}", "bandwidth": h, "donut": True, "role": "sensitivity"} for h in C.RD_SENSITIVITY_BANDWIDTHS],
    {"spec": "no donut", "bandwidth": C.RD_BANDWIDTH, "donut": False, "role": "sensitivity"},
]


def rd_sample(f: pd.DataFrame, bandwidth: float, donut: bool) -> pd.DataFrame:
    """Headline orders with a review inside the window (|days_late - c| < h, positive kernel weight)."""
    d = f[f["has_review"]]
    keep = (d["days_late"] - C.RD_CUTOFF).abs() < bandwidth
    if donut:
        keep = keep & ~d["days_late"].isin(C.RD_DONUT_DAYS)
    return d[keep]


def estimate(d: pd.DataFrame, bandwidth: float, donut: bool) -> dict:
    """Donut RD on a pre-restricted window sample; raises if the spec is not run as written."""
    x = d["days_late"].to_numpy(dtype=float)
    if donut and np.isin(x, C.RD_DONUT_DAYS).any():
        raise ValueError("donut days present in a donut RD sample")
    if d["low_review"].isna().any():
        raise ValueError("low_review missing inside the RD sample")
    clusters = pd.factorize(d["seller_id"], sort=True)[0]
    with contextlib.redirect_stdout(io.StringIO()):  # rdrobust prints a mass-point notice
        r = rdrobust(d["low_review"].to_numpy(dtype=float), x, c=C.RD_CUTOFF, h=bandwidth, kernel="tri", p=1,
                     vce="cr1", cluster=clusters, masspoints="adjust")
    used = r.bws.loc["h"].to_numpy(dtype=float)
    if not np.allclose(used, bandwidth):
        raise RuntimeError(f"rdrobust used bandwidth {used.tolist()}, not the requested {bandwidth}")
    n_left, n_right = (int(v) for v in r.N)
    if [int(v) for v in r.N_h] != [n_left, n_right]:
        raise RuntimeError("observations outside the bandwidth reached rdrobust")
    side = x > C.RD_CUTOFF
    return {
        "estimate": float(r.coef.loc["Conventional"].iloc[0]),
        "ci95_low": float(r.ci.loc["Robust"].iloc[0]),
        "ci95_high": float(r.ci.loc["Robust"].iloc[1]),
        "p_value_robust": float(r.pv.loc["Robust"].iloc[0]),
        # The robust CI is centered here, not on the conventional estimate of record.
        "estimate_bias_corrected": float(r.coef.loc["Bias-Corrected"].iloc[0]),
        "se_conventional": float(r.se.loc["Conventional"].iloc[0]),
        "se_robust": float(r.se.loc["Robust"].iloc[0]),
        "ci95_conventional_low": float(r.ci.loc["Conventional"].iloc[0]),
        "ci95_conventional_high": float(r.ci.loc["Conventional"].iloc[1]),
        "n_left": n_left,
        "n_right": n_right,
        "days_left": sorted(int(v) for v in np.unique(x[~side])),
        "days_right": sorted(int(v) for v in np.unique(x[side])),
        "clusters": int(r.n_clust),
        "fit_left": [float(v) for v in np.ravel(r.beta_p_l)],
        "fit_right": [float(v) for v in np.ravel(r.beta_p_r)],
    }


def run(f: pd.DataFrame) -> list[dict]:
    rows = []
    for s in SPECS:
        e = estimate(rd_sample(f, s["bandwidth"], s["donut"]), s["bandwidth"], s["donut"])
        rows.append({**s, "dropped_days": list(C.RD_DONUT_DAYS) if s["donut"] else [], **e})
    return rows


def daily_means(f: pd.DataFrame, max_bandwidth: float) -> list[dict]:
    d = f[f["has_review"] & ((f["days_late"] - C.RD_CUTOFF).abs() < max_bandwidth)]
    g = d.groupby("days_late")["low_review"].agg(["mean", "size"])
    return [{"days_late": int(k), "low_review_share": float(v["mean"]), "orders": int(v["size"])} for k, v in g.iterrows()]


def plot(means: list[dict], main: dict, path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5), facecolor=SURFACE)
    days = np.array([m["days_late"] for m in means])
    share = np.array([m["low_review_share"] for m in means]) * 100
    donut = np.isin(days, C.RD_DONUT_DAYS)
    ax.plot(days[~donut], share[~donut], "o", color=SERIES, markersize=6, label="daily share")
    ax.plot(days[donut], share[donut], "o", markerfacecolor=SURFACE, markeredgecolor=SERIES, markersize=6,
            label="donut days (dropped)")
    for lo, hi, (b0, b1) in [(min(main["days_left"]), C.RD_CUTOFF, main["fit_left"]),
                             (C.RD_CUTOFF, max(main["days_right"]), main["fit_right"])]:
        xs = np.array([lo, hi])
        ax.plot(xs, (b0 + b1 * (xs - C.RD_CUTOFF)) * 100, color=INK_2, linewidth=1.5)
    ax.axvline(C.RD_CUTOFF, color=INK_2, linestyle="--", linewidth=1)
    ax.annotate("promised date", (C.RD_CUTOFF, share.max()), xytext=(6, -2), textcoords="offset points",
                color=INK_2, fontsize=9, va="top")
    ax.set_title("Share of 1-2 star reviews by days late (%), with the main donut RD fit", loc="left", color=INK, fontsize=11)
    ax.set_xticks(days)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="upper left")
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)


def to_markdown(d: dict) -> str:
    num = "{:.4f}"
    rows = [{"spec": r["spec"], "role": r["role"], "bandwidth": r["bandwidth"],
             "dropped_days": ", ".join(map(str, r["dropped_days"])) or "none", "estimate": r["estimate"],
             "bias_corrected": r["estimate_bias_corrected"], "ci95_low": r["ci95_low"], "ci95_high": r["ci95_high"],
             "n_left": r["n_left"], "n_right": r["n_right"],
             "days_left": f"{min(r['days_left'])}..{max(r['days_left'])} ({len(r['days_left'])})",
             "days_right": f"{min(r['days_right'])}..{max(r['days_right'])} ({len(r['days_right'])})",
             "clusters": r["clusters"]} for r in d["estimates"]]
    return "\n\n".join([
        "# Donut regression discontinuity at the promised date",
        "Generated by `make rd`. **Corroborating estimate, not the headline** (ADR-0007 §3-4). Outcome: share of "
        "1-2 star reviews (`low_review`, 0-1 scale) on headline orders with a review. Running variable: days late; "
        f"cutoff {C.RD_CUTOFF:g} (day +1 and later are late); local-linear fit, triangular kernel, fixed bandwidth h "
        "(days with |days_late - cutoff| < h); rdrobust with mass-point adjustment and SEs clustered by seller "
        "(CR1, rdrobust's `vce='cr1'`). Estimate of record: conventional. 95% CI: robust bias-corrected, which is "
        "centered on the bias-corrected estimate (shown for reference), so the conventional estimate can fall outside "
        "it. Specification: ADR-0008 §3.",
        md_table(rows, {c: num for c in ("estimate", "bias_corrected", "ci95_low", "ci95_high")} | {"bandwidth": "{:g}"}),
        "Days columns: range of days late used on each side (number of distinct days).",
        "Caveats: the estimate is local to orders near the promised date, while the money translation needs the "
        f"average over all late orders (median {d['late_median_days_late']:g} days late). From day 3 late on, most reviews are written before the "
        "order arrives (survey timing), so the right side mixes in the experience of waiting. Orders bunch just "
        "before the promised date (Phase 1 diagnostics), which is why the donut drops days 0 and +1.",
        "## Daily share of 1-2 star reviews",
        md_table(d["daily_means"], {"low_review_share": num}),
        "Figure: `fig_rd.png` (hollow markers: donut days, dropped from the main fit).",
    ]) + "\n"


def main() -> None:
    f = analysis_frame(pd.read_parquet(C.ORDERS_PARQUET))
    estimates = run(f)
    means = daily_means(f, max(s["bandwidth"] for s in SPECS))
    result = rounded({
        "label": "Donut RD at the promised date (ADR-0007 §3, ADR-0008 §3); corroborating",
        "spec": {
            "outcome": "low_review", "sample": "headline orders with a review", "running_variable": "days_late",
            "cutoff": C.RD_CUTOFF, "kernel": "triangular", "polynomial": 1, "bias_correction_polynomial": 2,
            "vce": "CR1 clustered by seller_id (rdrobust vce='cr1')", "masspoints": "adjust",
            "window": "|days_late - cutoff| < h", "estimate": "conventional", "ci": "95% robust bias-corrected",
        },
        "estimates": estimates,
        "late_median_days_late": float(f.loc[f["late"] == 1, "days_late"].median()),
        "daily_means": means,
    })
    C.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (C.OUTPUTS_DIR / "rd.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "rd.md").write_text(to_markdown(result))
    plot(result["daily_means"], result["estimates"][0], C.OUTPUTS_DIR / "fig_rd.png")
    m = result["estimates"][0]
    print(f"Donut RD (main, h = {m['bandwidth']:g}): {m['estimate']:+.4f} "
          f"[robust 95% CI {m['ci95_low']:+.4f}, {m['ci95_high']:+.4f}], n = {m['n_left']:,} + {m['n_right']:,}")
    print(f"Wrote {C.OUTPUTS_DIR / 'rd.md'}")


if __name__ == "__main__":
    main()
