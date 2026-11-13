"""Method ladder (T14): every estimate side by side, with the pre-registered verdicts and flags.

ADR-0007 §4 and the falsification tests, ADR-0008 §5. Reads outputs/{naive,fe,rd,matching}.json.
Verdicts and flags are computed here, never judged by hand:

- A corroborating estimate (donut RD main spec, matching) "converges" if its point estimate lies
  inside the headline 95% CI. The headline is flagged fragile if both diverge in the same direction.
- Balance: any post-match |SMD| > 0.1 -> the matching estimate is not interpretable.
- Bin order: in `low_review` model (b), the 1-2 day bin's estimate is larger than the 3-7 day bin's.
- Repeat window: `repeat_90d` and `repeat_180d` estimates in model (a) have opposite signs.
- Star trigger: the `low_review` CI includes 0 while the 5-star CI excludes 0.

The headline is the pre-registered FE estimate and never switches. Writes outputs/ladder.json,
outputs/ladder.md and outputs/fig_ladder.png.
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from late_delivery import config as C  # noqa: E402
from late_delivery.diagnostics import GRID, INK, INK_2, SERIES, SURFACE, _style, md_table, rounded  # noqa: E402

SMD_FLAG = 0.1  # ADR-0007 falsification test / ADR-0008 §5


def _model(fe: dict, model_id: str) -> dict:
    return {e["term"]: e for e in next(m for m in fe["models"] if m["id"] == model_id)["estimates"]}


def ladder_rows(naive: dict, fe: dict, rd: dict, matching: dict) -> list[dict]:
    nv = next(o for o in naive["outcomes"] if o["outcome"].startswith("low_review"))
    p = fe["primary"]
    rows = [
        {"method": "Naive difference", "role": "biased baseline", "estimand": "all late vs all on-time orders",
         "estimate": nv["difference"], "ci95_low": nv["ci95_low"], "ci95_high": nv["ci95_high"],
         "n": nv["n_late"] + nv["n_on_time"]},
        {"method": "FE regression", "role": "headline (pre-registered)",
         "estimand": "average effect over all late orders, seller + week FE",
         "estimate": p["estimate"], "ci95_low": p["ci95_low"], "ci95_high": p["ci95_high"], "n": p["n_obs"]},
    ]
    for r in rd["estimates"]:
        main = r["role"].startswith("corroborating")
        rows.append({
            "method": "Donut RD" + ("" if main else f" ({r['spec']})"), "role": "corroborating" if main else "sensitivity",
            "estimand": f"jump at the promised date, days {min(r['days_left'])}..{max(r['days_right'])}"
                        + (", donut 0/+1" if r["dropped_days"] else ""),
            "estimate": r["estimate"], "ci95_low": r["ci95_low"], "ci95_high": r["ci95_high"],
            "n": r["n_left"] + r["n_right"],
        })
    a = matching["att"]
    rows.append({"method": "Matching", "role": "corroborating", "estimand": "ATT on matched late orders, no seller FE",
                 "estimate": a["estimate"], "ci95_low": a["ci95_low"], "ci95_high": a["ci95_high"],
                 "n": matching["sample"]["matched_late"]})
    return rows


def verdict(estimate: float, headline: dict) -> str:
    """ADR-0007 §4: converges if the point estimate lies inside the headline 95% CI."""
    if estimate < headline["ci95_low"]:
        return "diverges (below)"
    if estimate > headline["ci95_high"]:
        return "diverges (above)"
    return "converges"


def reconcile(rows: list[dict]) -> dict:
    headline = next(r for r in rows if r["role"].startswith("headline"))
    for r in rows:
        r["verdict"] = verdict(r["estimate"], headline) if r["role"] == "corroborating" else ""
    v = {r["method"]: r["verdict"] for r in rows if r["role"] == "corroborating"}
    rd_v, m_v = v["Donut RD"], v["Matching"]
    return {
        "headline": {k: headline[k] for k in ("method", "estimate", "ci95_low", "ci95_high")},
        "verdicts": v,
        "headline_fragile": rd_v != "converges" and rd_v == m_v,
        "rule": "converges = point estimate inside the headline 95% CI; fragile = donut RD and matching both "
                "diverge in the same direction (ADR-0007 §4)",
    }


def _ci_includes_zero(e: dict) -> bool:
    return e["ci95_low"] <= 0 <= e["ci95_high"]


def flags(fe: dict, matching: dict) -> list[dict]:
    bins = _model(fe, "low_review/b")
    r90, r180 = _model(fe, "repeat_90d/a")["late"], _model(fe, "repeat_180d/a")["late"]
    low, star5 = _model(fe, "low_review/a")["late"], _model(fe, "star_5/a")["late"]
    smd = matching["balance"]["max_abs_smd_after"]
    return [
        {"flag": "balance", "fired": smd > SMD_FLAG,
         "rule": f"any post-match abs(SMD) > {SMD_FLAG:g}", "values": f"max abs(SMD) = {smd:.4f}",
         "if_fired": "matching failed to balance; its estimate is not interpretable (ADR-0007)"},
        {"flag": "bin order", "fired": bins["late_1_2"]["estimate"] > bins["late_3_7"]["estimate"],
         "rule": "low_review model (b): 1-2 day bin estimate > 3-7 day bin estimate",
         "values": f"1-2: {bins['late_1_2']['estimate']:.4f}; 3-7: {bins['late_3_7']['estimate']:.4f}",
         "if_fired": "the 'waiting adds harm' reading of the bins is wrong (ADR-0007)"},
        {"flag": "repeat window", "fired": r90["estimate"] * r180["estimate"] < 0,
         "rule": "model (a): repeat_90d and repeat_180d estimates have opposite signs",
         "values": f"90d: {r90['estimate']:.4f}; 180d: {r180['estimate']:.4f}",
         "if_fired": "the repeat window drives the conclusion (ADR-0004)"},
        {"flag": "star distribution", "fired": _ci_includes_zero(low) and not _ci_includes_zero(star5),
         "rule": "low_review 95% CI includes 0 while the 5-star 95% CI excludes 0",
         "values": f"low_review CI [{low['ci95_low']:.4f}, {low['ci95_high']:.4f}]; "
                   f"5-star CI [{star5['ci95_low']:.4f}, {star5['ci95_high']:.4f}]",
         "if_fired": "the primary metric misses the effect (ADR-0004)"},
    ]


def build(naive: dict, fe: dict, rd: dict, matching: dict) -> dict:
    rows = ladder_rows(naive, fe, rd, matching)
    rec = reconcile(rows)
    return {
        "label": "Method ladder, outcome low_review (ADR-0007 §4, ADR-0008 §5)",
        "outcome": "low_review (share of 1-2 star reviews, 0-1 scale)",
        "rows": rows,
        "reconciliation": rec,
        "flags": flags(fe, matching),
    }


def plot(result: dict, path) -> None:
    # Bottom to top: naive, RD sensitivity runs, RD, matching, headline.
    sensitivity = [r["method"] for r in result["rows"] if r["role"] == "sensitivity"]
    order = ["Naive difference", *sensitivity, "Donut RD", "Matching", "FE regression"]
    rows = sorted(result["rows"], key=lambda r: order.index(r["method"]))
    h = result["reconciliation"]["headline"]
    fig, ax = plt.subplots(figsize=(10, 5.6), facecolor=SURFACE)
    ax.axvspan(h["ci95_low"] * 100, h["ci95_high"] * 100, color=SERIES, alpha=0.15, linewidth=0)
    ax.axvline(0, color=INK_2, linewidth=1)
    for y, r in enumerate(rows):
        recessive = r["role"] in ("sensitivity", "biased baseline")
        color = INK_2 if recessive else SERIES
        # CI drawn as a segment: the RD's robust CI is centred on the bias-corrected estimate, so the
        # conventional estimate of record can sit outside it (rd.md).
        ax.hlines(y, r["ci95_low"] * 100, r["ci95_high"] * 100, color=color, linewidth=2 if not recessive else 1.5)
        ax.plot(r["estimate"] * 100, y, "o", color=color, markersize=7 if not recessive else 5)
        right = max(r["ci95_high"], r["estimate"]) * 100
        ax.annotate(f"{r['estimate'] * 100:+.1f}", (right, y), xytext=(6, 0), textcoords="offset points",
                    va="center", color=INK_2, fontsize=9)
    ax.set_yticks(range(len(rows)), [f"{r['method']}\n{r['role']}" for r in rows], color=INK)
    ax.annotate("headline 95% CI", (h["ci95_low"] * 100, len(rows) - 0.5), xytext=(-4, 0), textcoords="offset points",
                ha="right", va="center", color=INK_2, fontsize=9)
    ax.set_title("Effect of a late delivery on the 1-2 star review share (percentage points, 95% CI)",
                 loc="left", color=INK, fontsize=11)
    ax.set_ylim(-0.5, len(rows))
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.tick_params(axis="y", colors=INK, labelsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)


def to_markdown(d: dict) -> str:
    num = "{:.4f}"
    rec = d["reconciliation"]
    fired = [f["flag"] for f in d["flags"] if f["fired"]]
    rows = [{k: r[k] for k in ("method", "role", "estimand", "estimate", "ci95_low", "ci95_high", "n", "verdict")}
            for r in d["rows"]]
    return "\n\n".join([
        "# Method ladder",
        "Generated by `make ladder` from `naive.json`, `fe.json`, `rd.json` and `matching.json`. Outcome: share of 1-2 "
        "star reviews (`low_review`, 0-1 scale). The headline is the pre-registered FE estimate and never switches "
        "(ADR-0007 §4). Verdicts and flags below are computed by code (ADR-0008 §5); ADR-0010 explains them.",
        "## Estimates",
        md_table(rows, {c: num for c in ("estimate", "ci95_low", "ci95_high")}),
        "## Reconciliation (ADR-0007 §4)",
        f"Rule: {rec['rule']}.",
        md_table([{"method": k, "verdict": v} for k, v in rec["verdicts"].items()]),
        f"Headline fragile: **{'yes' if rec['headline_fragile'] else 'no'}**.",
        "## Falsification flags",
        md_table([{"flag": f["flag"], "fired": "yes" if f["fired"] else "no", "rule": f["rule"], "values": f["values"],
                   "if fired": f["if_fired"]} for f in d["flags"]]),
        f"Flags fired: {', '.join(fired) if fired else 'none'}.",
        "Figure: `fig_ladder.png`.",
    ]) + "\n"


def main() -> None:
    inputs = {name: json.loads((C.OUTPUTS_DIR / f"{name}.json").read_text()) for name in ("naive", "fe", "rd", "matching")}
    result = rounded(build(**inputs))
    (C.OUTPUTS_DIR / "ladder.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "ladder.md").write_text(to_markdown(result))
    plot(result, C.OUTPUTS_DIR / "fig_ladder.png")
    rec = result["reconciliation"]
    print("Verdicts: " + "; ".join(f"{k} {v}" for k, v in rec["verdicts"].items())
          + f". Headline fragile: {rec['headline_fragile']}. Flags fired: "
          + (", ".join(f["flag"] for f in result["flags"] if f["fired"]) or "none"))
    print(f"Wrote {C.OUTPUTS_DIR / 'ladder.md'}")


if __name__ == "__main__":
    main()
