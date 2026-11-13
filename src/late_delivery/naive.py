"""Naive late vs on-time comparison (T8): a BIASED BASELINE, not a causal estimate.

Runs only after the pre-registration (ADR-0007) was committed. Late orders differ from
on-time orders in observed and unobserved ways (Phase 1 diagnostics), so this difference
mixes the effect of lateness with those differences. The estimates of record come from
the pre-registered methods.

Writes outputs/naive.json and outputs/naive.md.
"""

import json

import numpy as np
import pandas as pd

from late_delivery import config as C
from late_delivery.diagnostics import md_table, rounded

LABEL = "biased baseline, not a causal estimate"
Z = 1.959964  # two-sided 95%


def diff_ci(late: pd.Series, on_time: pd.Series) -> dict:
    """Difference in means (late minus on-time) with a normal-approximation 95% CI, unequal variances."""
    a, b = late.dropna().astype(float), on_time.dropna().astype(float)
    diff = a.mean() - b.mean()
    se = np.sqrt(a.var() / len(a) + b.var() / len(b))
    return {
        "n_late": len(a), "n_on_time": len(b),
        "mean_late": float(a.mean()), "mean_on_time": float(b.mean()),
        "difference": float(diff), "ci95_low": float(diff - Z * se), "ci95_high": float(diff + Z * se),
    }


def naive_rows(t: pd.DataFrame) -> list[dict]:
    h = t[t["in_headline"]]
    late = h["late"].astype(bool)
    outcomes = [
        ("low_review (primary)", "headline orders with a review", h["low_review"]),
        ("review_score", "headline orders with a review", h["review_score"]),
    ]
    for w in C.REPEAT_WINDOWS:
        eligible = h["is_first_order"] & h[f"repeat_{w}d_eligible"]
        outcomes.append((f"repeat_{w}d", "eligible first orders", h[f"repeat_{w}d"].where(eligible)))
    return [{"outcome": name, "population": pop, **diff_ci(s[late], s[~late])} for name, pop, s in outcomes]


def to_markdown(rows: list[dict]) -> str:
    num = "{:.4f}"
    return "\n\n".join([
        f"# Naive baseline: {LABEL.upper()}",
        "Late minus on-time difference on the headline sample (ADR-0005), with 95% confidence intervals "
        "from a normal approximation. Late orders differ from on-time orders in observed and unobserved "
        "ways, so this difference is **not** the effect of lateness. The estimates of record come from "
        "the pre-registered methods in ADR-0007.",
        md_table(rows, {c: num for c in ("mean_late", "mean_on_time", "difference", "ci95_low", "ci95_high")}),
        "low_review and repeat outcomes are shares (0-1); review_score is on the 1-5 scale.",
    ]) + "\n"


def main() -> None:
    t = pd.read_parquet(C.ORDERS_PARQUET)
    rows = naive_rows(t)
    result = rounded({
        "label": LABEL,
        "sample": "headline (ADR-0005)",
        "interval": "95%, normal approximation, unequal variances",
        "outcomes": rows,
    })
    C.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (C.OUTPUTS_DIR / "naive.json").write_text(json.dumps(result, indent=2) + "\n")
    (C.OUTPUTS_DIR / "naive.md").write_text(to_markdown(result["outcomes"]))
    print(f"Wrote {C.OUTPUTS_DIR / 'naive.md'} ({LABEL})")


if __name__ == "__main__":
    main()
