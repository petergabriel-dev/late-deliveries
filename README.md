# What does a late delivery actually cost an e-commerce marketplace?

**Interim answer (Phase 2 of 5):** a late delivery raises the share of 1-2 star reviews by about 52 percentage points (95% CI 50 to 53), corroborated by matching; the dollar range arrives in Phase 4. Details: `outputs/ladder.md`, ADR-0010.

## Limitations so far

- **Observational data.** The pre-registered headline estimate (ADR-0007) adjusts for observed confounders only. Carrier identity is not in the data. Matching agrees with the headline, but it uses the same observed controls, so it does not rule out unobserved confounding; Phase 3 tests that.
- **The regression discontinuity cannot pin down the jump at the promised date.** Orders bunch just before the promised date, so days 0 and +1 are dropped, and every RD specification's confidence interval includes zero (ADR-0010). The RD neither confirms nor rules out the headline, which rests on the fixed-effects regression and is corroborated by matching.
- **Survey timing is specific to Olist.** Most customers whose order is 3+ days late are surveyed before it arrives, so the effect includes the experience of waiting. It grows with lateness: small at 1-2 days late, large from 3 days on (`outputs/fe.md`).
- **Repeat purchases show no detectable effect.** At both 90 and 180 days the confidence interval includes zero, so the repeat-purchase effect is an upper bound (ADR-0004), and that money channel will lean on assumptions.
- **Two of three money channels will rest on outside assumptions** (ADR-0006), kept in one versioned file and shown separately from measured effects.
- **Conservative sample.** Canceled, undelivered and multi-seller orders are excluded, so the worst outcomes are left out.
- **The naive comparison is biased** (`outputs/naive.md`): late orders differ from on-time ones in many ways, so it is a baseline, not the answer.

## Status

| Phase | State |
|---|---|
| 1 Foundation: data, definitions, diagnostics, naive baseline, pre-registration | Done |
| 2 Identification: FE regression, donut RD, matching | Done |
| 3 Robustness: 12 pre-registered checks | Not started |
| 4 Business translation: dollar range | Not started |
| 5 Communication: memo and write-up | Not started |

## Reproduce

```bash
uv sync && make all
```

Needs [uv](https://docs.astral.sh/uv/), `make` and `shasum`; no credentials. Rebuilds every result from the committed raw CSVs in about 20 seconds (the first run on a new machine is slower while it builds caches). Outputs land in `outputs/`:

- `exclusions.json`: how 99,441 orders become the 94,931-order headline sample
- `diagnostics.md`: Phase 1 design diagnostics (no outcome comparisons)
- `naive.md`: biased late vs on-time baseline
- `fe.md`: the 25 pre-registered fixed-effects models, including the headline
- `rd.md`, `fig_rd.png`: donut regression discontinuity at the promised date
- `matching.md`: propensity-score matching and its balance table
- `ladder.md`, `fig_ladder.png`: every estimate side by side, with the pre-registered verdicts and falsification checks

## Decision log

Every analytical and engineering judgment is an ADR in [`docs/engineering/decisions/`](docs/engineering/decisions/README.md), each with options considered and a falsification test. The brief's six judgment calls map to ADRs tagged "(JC n)". ADR-0007 is the pre-registration, committed before any outcome was compared between late and on-time orders. ADR-0008 and ADR-0009 fixed the remaining Phase 2 choices before each estimate was computed, and ADR-0010 records how the methods were reconciled.

## Repository

- `data/raw/`: Olist CSVs (unmodified) + checksums
- `src/late_delivery/`: `config.py`, `build.py`, `diagnostics.py`, `naive.py`, `fe.py`, `rd.py`, `matching.py`, `ladder.py`
- `tests/`: unit, estimator and data-quality tests
- `docs/`: project brief and engineering docs

## Data

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), published by Olist on Kaggle under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Files in `data/raw/` are unmodified and stay under that license; see `data/raw/README.md`.
