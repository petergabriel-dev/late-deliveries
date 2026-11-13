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
| `make all` | Full rebuild: check-data → build → test → diagnostics → naive. About 5 seconds once the matplotlib font cache exists (the first run builds it, about 30 seconds). |
| `make check-data` | Verify `data/raw/*.csv` against `data/raw/SHA256SUMS`. |
| `make build` | Write `data/processed/orders.parquet` and `outputs/exclusions.json`. |
| `make test` | Build, then run `pytest` (unit tests on fixtures + data-quality tests on real data). |
| `make diagnostics` | Write `outputs/diagnostics.{md,json}`, `fig_monthly.png`, `fig_days_late.png`. |
| `make naive` | Write `outputs/naive.{md,json}` (biased baseline). |

## Clean-clone rebuild

```bash
git clone <repo> late-delivery && cd late-delivery
uv sync && make all
```

Outputs are deterministic: JSON outputs are byte-identical across runs.

## Adding a dependency

`uv add <package>` updates `pyproject.toml` and `uv.lock`; commit both. Add a dependency only in the task that needs it (ADR-0002).

## Recording a decision

1. Copy `docs/engineering/decisions/ADR-template.md` to `ADR-NNNN-<slug>.md` and fill every section, including Options considered and Falsification test. End the title with "(JC n)" if it settles a brief judgment call.
2. Run `/docs update-index` in Pi (Build mode) to regenerate `decisions/README.md`; never edit the index by hand.
3. Check the regenerated index lists the new ADR before committing.

## Working with Pi Build

Each saved-plan task is committed separately, then ticked in the Pi tracker. If the Claude Code session changes mid-build, Pi's hook blocks writes until the old lease is released (`/build-lease release`) and the new request is approved (`/build-lease approve`).
