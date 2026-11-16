# Dev workflow

## Prerequisites

- [uv](https://docs.astral.sh/uv/) 0.11+ (installs Python 3.12 from `.python-version` and the locked dependencies)
- `make`
- `shasum` (macOS built-in; on Linux it ships with Perl)

No credentials or downloads: the raw data is committed.

## Commands

| Command | What it does |
|---|---|
| `uv sync` | Create `.venv` with the exact versions in `uv.lock`, including the `late_delivery` package (editable). |
| `make all` | Full rebuild: check-data → build → test → diagnostics → naive, fe, rd, matching → ladder → robustness → money → report. Warm Phase 5 run: 30.65 s on 2026-11-16; owner accepted the 0.65 s overrun against the original 30 s budget at T36. The first run on a new machine is slower while font and numba caches build. |
| `make check-data` | Verify `data/raw/*.csv` against `data/raw/SHA256SUMS`. |
| `make build` | Write `data/processed/orders.parquet` and `outputs/exclusions.json`. |
| `make test` | Build, then run `pytest` (unit tests on fixtures, planted-effect estimator tests, data-quality tests on real data). |
| `make diagnostics` | Write `outputs/diagnostics.{md,json}`, `fig_monthly.png`, `fig_days_late.png`. |
| `make naive` | Write `outputs/naive.{md,json}` (biased baseline). |
| `make fe` | Write `outputs/fe.{md,json}`: the 25 pre-registered fixed-effects models, headline included (about 9 s). |
| `make rd` | Write `outputs/rd.{md,json}` and `fig_rd.png`: donut RD plus sensitivity runs (about 3 s). |
| `make matching` | Write `outputs/matching.{md,json}`: propensity-score matching and balance table (about 4 s). |
| `make ladder` | Runs naive, fe, rd and matching, then writes `outputs/ladder.{md,json}` and `fig_ladder.png`: every estimate side by side with the computed verdicts and flags. |
| `make robustness` | Runs fe and rd, then writes `outputs/robustness.{md,json}` and `fig_robustness.png`: the 12 pre-registered Phase 3 checks with their computed flags (ADR-0011). 13.4 s warm including fe and rd; the robustness step alone takes about 5 s (measured 2026-11-16). |
| `make money` | Runs fe, then writes `outputs/money.{md,json}` and `fig_money_tornado.png`: cost per late delivery, tornado, flags and disruption scenario (ADR-0013), from `orders.parquet`, `fe.json` and `assumptions.toml`. About 10 s warm including build and fe (measured 2026-11-16: 10.1 s and 9.7 s). |
| `make report` | Refresh diagnostics, ladder, robustness and money, then render `docs/report/{memo,writeup}.md`, root `README.md` and `outputs/report.json`. Prints document word counts; validates the memo cap, placeholders, relative links and unused derived keys (ADR-0015). |
| `make check-outputs` | Runs `make all`, then rejects and lists non-PNG Git changes, including untracked files, under `outputs/`, `docs/report/` and `README.md`. Commit regenerated results before expecting a clean check. T36: full check 31.03 s; isolated guard 0.031 s (2026-11-16). |

## Editing reports

Edit `docs/report/memo.template.md`, `writeup.template.md` or `README.template.md`, then run `make report`; never edit the rendered documents directly. `config.REPORT_TEMPLATES` maps each template to its target, including the README at the repo root. Numbers use placeholders, with report arithmetic and exact-match list selections in `report.derived()`; see conventions and invariant 6.

All estimator targets are phony, so `make report` includes their rebuild time. To render only from existing, current analysis outputs, use `uv run python -m late_delivery.report`. The approved ≤2 s budget applies to the renderer alone, not `make report` with prerequisites; renderer-only timing was 1.38 s at T33 (2026-11-16).

## Clean-clone rebuild

```bash
git clone <repo> late-delivery && cd late-delivery
uv sync && make check-outputs
```

Outputs and report templates are committed; `data/processed/` stays ignored. JSON and rendered Markdown were byte-identical across repeated same-machine runs. Cross-machine byte identity remains unverified; PNG bytes are excluded from the guard.

## Dependencies

| Package | Used by |
|---|---|
| pandas, numpy, pyarrow | every step |
| matplotlib | figures |
| rddensity | Phase 1 density test (`diagnostics.py`) |
| pyfixest | fixed-effects models (`fe.py`), weighted OLS for matching (`matching.py`) |
| rdrobust | donut RD (`rd.py`) |
| statsmodels | propensity logit (`matching.py`); test oracle for the sensitivity fits (`test_estimators.py`) |
| scipy | t quantiles for robustness values (`robustness.py`); also required by pyfixest and statsmodels |
| pytest (dev) | tests |

`money.py` reads `assumptions.toml` with the standard library's `tomllib`; Phase 4 added no dependency.
`report.py` uses stdlib parsing, formatting and link checks plus existing `diagnostics.rounded` and `md_table`; Phase 5 added no dependency.

## Adding a dependency

`uv add <package>` updates `pyproject.toml` and `uv.lock`; commit both. Add a dependency only in the task that needs it (ADR-0002).

## Recording a decision

1. Copy `docs/engineering/decisions/ADR-template.md` to `ADR-NNNN-<slug>.md` and fill every section, including Options considered and Falsification test. End the title with "(JC n)" if it settles a brief judgment call.
2. Run `/docs update-index` in Pi (Build mode) to regenerate `decisions/README.md`; never edit the index by hand. From Claude Code, see "Decision index" in `traps.md`.
3. Check the regenerated index lists the new ADR before committing.

## Working with Pi Build

Each saved-plan task is committed separately, then ticked in the Pi tracker. If the Claude Code session changes mid-build, Pi's hook blocks writes until the old lease is released (`/build-lease release`) and the new request is approved (`/build-lease approve`).
