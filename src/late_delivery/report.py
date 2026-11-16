"""Traceable Markdown reports from analysis JSON and assumptions (ADR-0015)."""

import json
from pathlib import Path
import re
import tomllib
from urllib.parse import unquote, urlsplit

from late_delivery import config as C
from late_delivery.diagnostics import md_table, rounded


def derived(sources: dict) -> dict:
    """Sole home for report arithmetic and exact-match list selections."""
    money = sources["money"]
    horizon = one(money["tornado"], input="horizon_days")
    scale = 100  # ADR-0015 / T34: unhappy reviews per this many late orders.
    checks = sources["robustness"]["checks"]
    disruption = one(checks, id=10)
    sensitivity = one(checks, id=6)
    repeat_rows = []
    for window in (90, 180):  # ADR-0004: primary and check repeat windows.
        model = one(sources["fe"]["models"], id=f"repeat_{window}d/a")
        estimate = one(model["estimates"], term="late")
        repeat_rows.append({"Window (days)": window, "Eligible first orders": model["n_sample"],
                            "Regression observations": model["n_obs"], "Effect (pp)": estimate["estimate"] * scale,
                            "95% CI (pp)": f"[{estimate['ci95_low'] * scale:.3f}, {estimate['ci95_high'] * scale:.3f}]"})
    ladder_rows = [one(sources["ladder"]["rows"], method=method)
                   for method in ("Naive difference", "FE regression", "Donut RD", "Matching")]
    ladder_table = [{"Method": row["method"], "Role": row["role"], "Effect (share)": row["estimate"],
                     "95% CI": f"[{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]"} for row in ladder_rows]
    robust_table = [{"Check": row["id"], "Sample change": row["label"], "Effect (share)": row["estimate"],
                     "95% CI": f"[{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]",
                     "Flag": "yes" if row["fired"] else "no"}
                    for row in (one(checks, id=i) for i in (3, 7, 10))]
    return {
        "memo_review_scale": scale,
        "memo_review_more": sources["fe"]["primary"]["estimate"] * scale,
        "memo_rd_more": one(sources["ladder"]["rows"], method="Donut RD")["estimate"] * scale,
        "memo_disruption_more": disruption["estimate"] * scale,
        "memo_horizon_low_brl": horizon["low_revenue"],
        "memo_horizon_high_brl": horizon["high_revenue"],
        "memo_horizon_low_usd": horizon["low_revenue"] / money["fx"]["brl_per_usd"],
        "memo_horizon_high_usd": horizon["high_revenue"] / money["fx"]["brl_per_usd"],
        "writeup_primary": one(sources["fe"]["models"], id="low_review/a"),
        "writeup_repeat_table": md_table(repeat_rows, {"Eligible first orders": "{:,}",
                                                       "Regression observations": "{:,}", "Effect (pp)": "{:.3f}"}),
        "writeup_repeat_power": one(sources["diagnostics"]["repeat_mde"], window_days=90),
        "writeup_ladder_table": md_table(ladder_table, {"Effect (share)": "{:.3f}"}),
        "writeup_rd": one(sources["rd"]["estimates"], spec="main"),
        "writeup_continuity": one(one(checks, id=5)["covariates"], covariate="promised_days"),
        "writeup_disruption": disruption,
        "writeup_sensitivity": sensitivity,
        "writeup_state_benchmark": one(sensitivity["benchmarks"], benchmark="customer_state"),
        "writeup_post_delivery": one(checks, id=8),
        "writeup_checks_count": len(checks),
        "writeup_flags_count": len(sources["robustness"]["flags_fired"]),
        "writeup_robust_table": md_table(robust_table, {"Effect (share)": "{:.3f}"}),
        "writeup_measured_share": one(money["flags"], id=1)["value"],
    }


def load_sources(outputs_dir: Path | None = None, assumptions_path: Path | None = None) -> dict:
    outputs_dir = C.OUTPUTS_DIR if outputs_dir is None else outputs_dir
    assumptions_path = C.ASSUMPTIONS_TOML if assumptions_path is None else assumptions_path
    sources = {p.stem: json.loads(p.read_text(encoding="utf-8"))
               for p in sorted(outputs_dir.glob("*.json")) if p.stem != "report"}
    with assumptions_path.open("rb") as f:
        sources["assumptions"] = tomllib.load(f)
    sources["report"] = rounded(derived(sources))
    return sources


def one(rows: list[dict], **match) -> dict:
    matches = [row for row in rows if all(key in row and row[key] == value for key, value in match.items())]
    if len(matches) != 1:
        raise ValueError(f"one({match!r}): expected exactly one row, found {len(matches)}")
    return matches[0]


def resolve(placeholder: str, sources: dict) -> str:
    """Resolve a complete {source:dot.path[:fmt]} token, never evaluating code."""
    m = re.fullmatch(r"\{([A-Za-z_]\w*):([^{}:]+)(?::([^{}]*))?\}", placeholder)
    if m is None:
        raise ValueError(f"{placeholder}: invalid placeholder")
    source, path, spec = m.groups()
    if source not in sources:
        raise ValueError(f"{placeholder}: unknown source {source!r}")
    value = sources[source]
    for key in path.split("."):
        if not isinstance(value, dict):
            raise ValueError(f"{placeholder}: dictionary-only traversal; use one() for list values")
        if not key or key not in value:
            raise ValueError(f"{placeholder}: missing key {key!r}")
        value = value[key]
    if isinstance(value, list):
        raise ValueError(f"{placeholder}: use one() for list values")
    try:
        return format(value, spec or "")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{placeholder}: invalid format {spec!r}: {exc}") from exc


def word_count(text: str) -> int:
    return len(re.findall(r"[^\W_]+(?:[-'’][^\W_]+)*", text))


def render(text: str, sources: dict, *, template_name: str = "<template>",
           used: set | None = None, max_words: int | None = None) -> str:
    def replace(m):
        token = m.group()
        if token in ("{{", "}}"):
            return token[0]
        try:
            value = resolve(token, sources)
        except ValueError as exc:
            raise ValueError(f"{template_name}: {exc}") from exc
        if used is not None and token.startswith("{report:"):
            used.add(token[1:-1].split(":", 2)[1].split(".")[0])
        return value

    result = re.sub(r"\{\{|\}\}|\{[^{}]*\}|[{}]", replace, text)
    if max_words is not None and word_count(result) > max_words:
        raise ValueError(f"{template_name}: memo has {word_count(result)} words; maximum {max_words}")
    return result


def check_unused_derived(sources: dict, used: set, *, template_name: str = "report templates") -> None:
    unused = sources["report"].keys() - used
    if unused:
        tokens = ", ".join("{report:" + key + "}" for key in sorted(unused))
        raise ValueError(f"{template_name}: unused derived placeholders: {tokens}")


def _link_destinations(text: str):
    # Inline links/images: balance parentheses so ordinary filenames and URL paths work.
    for m in re.finditer(r"!?\[[^\]\n]*\]\(\s*", text):
        start = m.end()
        if text[start:start + 1] == "<":
            end = text.find(">", start + 1)
            if end == -1:
                raise ValueError("unterminated angle-bracket link")
            yield text[start + 1:end]
            continue
        depth = 0
        end = start
        while end < len(text):
            char = text[end]
            if (char == ")" or char.isspace()) and depth == 0:
                break
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            end += 1
        yield text[start:end]
    # Reference definitions apply to both links and images; optional titles are ignored.
    for m in re.finditer(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", text, re.MULTILINE):
        yield m[1].removeprefix("<").removesuffix(">")


def check_links(text: str, target: Path, *, template_name: str = "<template>") -> None:
    try:
        for destination in _link_destinations(text):
            url = urlsplit(destination)
            if url.scheme or url.netloc or not url.path:
                continue
            if not (target.parent / unquote(url.path)).exists():
                raise ValueError(f"broken relative link/image {destination!r} from {target}")
    except ValueError as exc:
        raise ValueError(f"{template_name}: {exc}") from exc


def main() -> None:
    sources = load_sources()
    used = set()
    documents = []
    for template, target in C.REPORT_TEMPLATES:
        text = render(template.read_text(encoding="utf-8"), sources, template_name=str(template), used=used,
                      max_words=C.MEMO_MAX_WORDS if target == C.REPORT_DIR / "memo.md" else None)
        check_links(text, target, template_name=str(template))
        documents.append((target, text))
    check_unused_derived(sources, used, template_name=", ".join(str(t) for t, _ in C.REPORT_TEMPLATES)
                         or "report templates")
    # Validate the whole batch before writing report.json or any rendered document.
    C.REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    C.REPORT_JSON.write_text(json.dumps(sources["report"], indent=2) + "\n", encoding="utf-8")
    for target, text in documents:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"Wrote {target}: {word_count(text)} words")
    print(f"Wrote {C.REPORT_JSON}")


if __name__ == "__main__":
    main()
