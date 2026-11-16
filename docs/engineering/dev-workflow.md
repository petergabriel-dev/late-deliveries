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

## Phase 5 completion audit (T38)

### Fresh-clone rebuild

On **2026-11-16**, cloned committed `5e8f81e` into `/tmp/late-delivery-t38-9imdzh_q/repo` with `git clone --no-hardlinks`. No virtualenv or processed data was inherited. A separate writable copy of the existing uv dependency cache was prepared before timing; this is a same-machine, offline rebuild, not a test of downloading dependencies on another machine.

With `UV_CACHE_DIR=/tmp/late-delivery-t38-9imdzh_q/uv-cache`, `MPLCONFIGDIR=/tmp/late-delivery-t38-9imdzh_q/mpl` and `UV_OFFLINE=1`, timed `uv sync && make check-outputs`: **86.86 s**, exit **0**, **107 tests passed**. Python was 3.12.9; uv was 0.11.0. The new environment included first-run test/compiler/font-cache work, so this is not the warm-build benchmark. Cache preparation and cloning are excluded from that duration. The clone's `config.ROOT` resolved inside the clone, Git status was clean, and processed data remained untracked. All **21 JSON/Markdown outputs and rendered documents** compared byte-identical with the source checkout; PNG bytes were not part of that comparison. The local command log remains at `/tmp/late-delivery-t38-9imdzh_q/rebuild.log` (temporary evidence).

The original warm-build target was not met in T36: 30.65 s versus 30 s; the owner accepted that recorded deviation. The renderer-only budget and timing are described above. This audit does not turn the timing waiver into a claim that the original cap passed, nor establish cross-machine determinism. Owner prose approval preceded memo commit `5a9f6a8`, write-up commit `88dbc2f` and README commit `7417094`; T38 changes only the README's Phase 5 status. Independent peer review and publishing are separate, not claimed complete here.

### Literal-digit inventory

Manually audited all three `docs/report/*.template.md` files. Below, each row lists **every digit run outside placeholders on that source line**, in encounter order, retaining leading zeros and repeats. Source lines are stable across the status-only change. Identifiers include ADR/JC/phase/invariant labels and their filenames; parameters must be defined in the cited ADR. URL escapes are syntax, not reported numbers. No unjustified literal or hand-typed result found; no prose fix required. `memo.template.md` contains **no digits outside placeholders**.

`docs/report/writeup.template.md`:

| Line | Digit runs | Justification |
|---|---|---|
| 7 | `95` | Confidence level fixed in ADR-0007. |
| 11 | `0014, 0014, 4` | ADR-0014 label/path and phase identifier in filename. |
| 17 | `2018, 2018` | Surge/strike window years defined in ADR-0011. |
| 25 | `0012, 0012, 3` | ADR-0012 label/path and phase identifier. |
| 31 | `2017, 01, 01, 2018, 08, 31` | Purchase-window dates defined in ADR-0005. |
| 37 | `0005, 0005` | ADR identifiers. |
| 39 | `1, 5` | JC identifiers. |
| 41 | `1` | JC identifier. |
| 43 | `1, 2` | Low-review star definition, ADR-0004. |
| 45 | `5, 90, 180` | JC identifier; repeat windows defined in ADR-0004. |
| 49 | `90` | Repeat-window definition, ADR-0004. |
| 51 | `0003, 0003, 0004, 0004` | ADR identifiers. |
| 53 | `3` | JC identifier. |
| 55 | `3` | JC identifier. |
| 67 | `0007, 0007, 0008, 0008, 2, 0009, 0009` | ADR identifiers and phase identifier in filename. |
| 69 | `4` | JC identifier. |
| 71 | `4, 95` | JC identifier; confidence level defined in ADR-0007. |
| 73 | `0, 1` | Cutoff/donut-day definitions, ADR-0003 and ADR-0007. |
| 79 | `0010, 0010, 2, 0012, 0012, 3` | ADR identifiers and phase identifiers in filenames. |
| 81 | `2` | JC identifier. |
| 83 | `2` | JC identifier. |
| 95 | `0011, 0011, 3, 0012, 0012, 3` | ADR identifiers and phase identifiers in filenames. |
| 97 | `6` | JC identifier. |
| 99 | `6` | JC identifier. |
| 113 | `0006, 0006, 0013, 0013, 4, 0014, 0014, 4` | ADR identifiers and phase identifiers in filenames. |
| 129 | `0002, 0002, 0015, 0015, 5` | ADR identifiers and phase identifier in filename. |

`docs/report/README.template.md`:

| Line | Digit runs | Justification |
|---|---|---|
| 20 | `1` | Phase identifier. |
| 21 | `2` | Phase identifier. |
| 22 | `3` | Phase identifier; check count is a placeholder, not a literal. |
| 23 | `4` | Phase identifier. |
| 24 | `5` | Phase identifier. |
| 40 | `6, 0015, 0015, 5` | Invariant/ADR identifiers and phase identifier in filename. |
| 59 | `1, 6, 0007, 0007, 0008, 0009, 0010, 0011, 0012, 0013, 0014, 0015, 0015, 5` | JC/ADR identifiers and phase identifier in filename. |
| 69 | `20, 20, 20, 20, 20, 20, 20, 20` | `%20` encodes spaces in the brief's filename; no numerical claim. |
| 75 | `4, 0, 4, 0` | CC BY-NC-SA version in license label and URL, as required by ADR-0002/ADR-0015. |

### Brief definition of done

All seven brief items checked, with version-controlled evidence paths:

| Brief item | Evidence |
|---|---|
| Question and answer in README's first three lines | [README.md](../../README.md), lines 1–3. |
| Identification methods compared; disagreement explained | [Method ladder](../report/writeup.md#method-ladder-jc-3), [reconciliation](../report/writeup.md#reconciling-disagreement-jc-4), [full ladder](../../outputs/ladder.md). |
| Limitations near the top | Second write-up section: [limitations](../report/writeup.md#limitations); also near the top of [README.md](../../README.md). |
| Every memo number traces to code | [Memo template](../report/memo.template.md), [renderer/derived calculations](../../src/late_delivery/report.py), [money JSON](../../outputs/money.json), [assumptions](../../assumptions.toml). All placeholders resolved; literal inventory above. |
| Decision log covers JC 1–6 | [Decision index](decisions/README.md), including ADR-0003 (JC 1), ADR-0007 (JC 2/3/4), ADR-0004 (JC 5), ADR-0006 (JC 6), plus later implementation and reading records. |
| One-command rebuild from a fresh clone | [Makefile](../../Makefile), `uv sync && make check-outputs`; successful fresh-clone run and conditions recorded above. |
| Memo ends with a recommendation | Last section of [memo](../report/memo.md#recommendation): break-even, promise-first and test longer promises. |

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
