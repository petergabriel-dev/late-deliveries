# What does a late delivery actually cost an e-commerce marketplace?

**Answer:** about **R$2 [US$0.62] in lost platform commission per late delivery**, with bounds of R$0.60–R$4.42 [US$0.18–US$1.33]; almost all of this rests on outside estimates of later sales lost through lower ratings. The directly measured repeat-purchase loss is R$0.06 [US$0.02]. The preferred review estimate is 52 more unhappy reviews per 100 late orders, corroborated by matching. Fund improvements only where avoiding a late delivery costs less than the modeled loss; make promises accurate first, and test longer promises before rollout.

**Read:** [stakeholder memo](docs/report/memo.md) · [technical write-up](docs/report/writeup.md).

## Limitations

- **Observational, not experimental.** Seller and purchase-week controls do not remove every possible confounder; carrier identity is absent. Matching agrees but shares the observed controls.
- **Review effects depend on context.** Removing disruption periods moves the estimate outside the headline interval. The promised-date discontinuity cannot identify a reliable local effect because the groups differ. Survey timing includes customers still waiting; repeat purchases show no detectable effect.
- **Money is mostly assumption-driven.** Review persistence is illustrative, seller-rating visibility is unverified, and commission is gross of channel fees. Support costs are unmeasured and outside the range.
- **Scope is delivered single-seller orders.** Canceled and never-delivered orders are excluded. Longer promises could deter checkout purchases, a cost these data cannot measure.

See the [full limitations and evidence](docs/report/writeup.md#limitations) before treating the estimate as an investment budget.

## Status

| Phase | State |
|---|---|
| 1 Foundation: data, definitions, diagnostics and pre-registration | Done |
| 2 Identification: fixed-effects regression, donut RD and matching | Done |
| 3 Robustness: 12 pre-registered checks | Done |
| 4 Business translation: cost range and recommendation | Done |
| 5 Communication: rendered reports, repo polish and rebuild audit | In progress |

## Reproduce

```bash
uv sync && make all
```

Needs [uv](https://docs.astral.sh/uv/), `make` and `shasum`. Raw data are committed; no data credentials are required. The first run builds caches and is slower than subsequent runs. To rebuild and check committed results:

```bash
make check-outputs
```

The guard rebuilds, then fails if Git reports non-PNG changes in `outputs/`, `docs/report/` or `README.md`. PNGs are committed and regenerated but excluded from the byte-staleness check. Direct edits to generated Markdown are overwritten: edit `docs/report/*.template.md`, then run `make report`.

**Traceability, invariant 6:** every reported statistic, count, money figure and input value in the README, memo and write-up resolves through a placeholder from analysis JSON, `assumptions.toml` or derived `outputs/report.json`. Report arithmetic lives in `report.py`; no hand-copied results. ADR identifiers and documented definitions may remain literal. See [ADR-0015](docs/engineering/decisions/ADR-0015-phase5-communication-choices.md).

## Outputs

- [exclusions.json](outputs/exclusions.json): how 99,441 orders become the 94,931-order headline sample.
- [diagnostics.md](outputs/diagnostics.md): design diagnostics, exclusions and repeat-purchase power.
- [naive.md](outputs/naive.md): biased late-versus-on-time baseline.
- [fe.md](outputs/fe.md): 25 pre-registered models, including the review headline.
- [rd.md](outputs/rd.md) and [RD figure](outputs/fig_rd.png): promised-date discontinuity and sensitivity runs.
- [matching.md](outputs/matching.md): propensity-score matching and balance diagnostics.
- [ladder.md](outputs/ladder.md) and [ladder figure](outputs/fig_ladder.png): method comparison and pre-registered verdicts.
- [robustness.md](outputs/robustness.md) and [robustness figure](outputs/fig_robustness.png): check results and computed flags.
- [money.md](outputs/money.md) and [money sensitivity figure](outputs/fig_money_tornado.png): cost channels, bounds, assumptions and disruption scenario.
- [report.json](outputs/report.json): derived report values and summary tables; [docs/report/](docs/report/): prose templates and rendered memo and write-up.

Each estimator also writes machine-readable JSON beside its Markdown, including the specification and sample counts. Relative links resolve from the rendered document's location, not its template's location.

## Decision log

Every analytical and engineering judgment is an ADR in the [decision index](docs/engineering/decisions/README.md), with options, reasons and a falsification test. JC 1–6 map to the records tagged with their judgment-call identifiers. [ADR-0007](docs/engineering/decisions/ADR-0007-pre-registration.md) fixed the estimation hierarchy before outcome comparisons. ADR-0008 and ADR-0009 closed implementation choices; ADR-0010 reconciled the methods. ADR-0011 and ADR-0012 govern robustness; ADR-0013 and ADR-0014 govern money inputs and interpretation. [ADR-0015](docs/engineering/decisions/ADR-0015-phase5-communication-choices.md) governs rendered communication, committed outputs and the staleness guard.

## Repository

- [data/raw/](data/raw/): unmodified Olist CSVs and checksums; `data/processed/` remains local and ignored.
- [src/late_delivery/](src/late_delivery/): `config.py`, `build.py`, `diagnostics.py`, `naive.py`, `fe.py`, `rd.py`, `matching.py`, `ladder.py`, `robustness.py`, `money.py` and `report.py`.
- [assumptions.toml](assumptions.toml): money inputs with sources, measured references or illustrative labels.
- [tests/](tests/): synthetic definition, estimator, money and renderer tests, plus real-data quality checks.
- [docs/report/](docs/report/): memo, technical write-up and their templates, including the README template.
- [docs/engineering/](docs/engineering/): architecture, invariants, conventions, workflow, traps and decisions.
- [Project brief](docs/Project%20Brief%20What%20Does%20a%20Late%20Delivery%20Actually%20Cost.md): question, phases and deliverables.

## Data

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), published by Olist on Kaggle. Raw CSVs are unmodified; see [data/raw/README.md](data/raw/README.md).

Results in `outputs/` and `docs/report/` derive from the Olist data and are shared under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

<!-- generated from docs/report/README.template.md; edit there, then make report -->
