# What does a late delivery actually cost an e-commerce marketplace?

**Answer:** pending (Phase 1 of 5 complete). The causal estimate and dollar range arrive in Phases 2-4.

## Limitations so far

- **Observational data.** The pre-registered headline estimate (ADR-0007) adjusts for observed confounders only. Carrier identity is not in the data.
- **The regression discontinuity is weak here.** Orders bunch just before the promised date, so the RD corroborates rather than heads the analysis.
- **Survey timing is specific to Olist.** Most customers whose order is 3+ days late are surveyed before it arrives, so the effect includes the experience of waiting.
- **Repeat purchases are rare** (about 1% within 90 days). Only large drops are detectable; that channel will likely be an upper bound.
- **Two of three money channels will rest on outside assumptions** (ADR-0006), kept in one versioned file and shown separately from measured effects.
- **Conservative sample.** Canceled, undelivered and multi-seller orders are excluded, so the worst outcomes are left out.
- **The Phase 1 naive comparison is biased** (`outputs/naive.md`): late orders differ from on-time ones in many ways, so it is a baseline, not the answer.

## Status

| Phase | State |
|---|---|
| 1 Foundation: data, definitions, diagnostics, naive baseline, pre-registration | Done |
| 2 Identification: FE regression, donut RD, matching | Not started |
| 3 Robustness: 12 pre-registered checks | Not started |
| 4 Business translation: dollar range | Not started |
| 5 Communication: memo and write-up | Not started |

## Reproduce

```bash
uv sync && make all
```

Needs [uv](https://docs.astral.sh/uv/), `make` and `shasum`; no credentials. Rebuilds every result from the committed raw CSVs in about 5 seconds. Outputs land in `outputs/`:

- `exclusions.json`: how 99,441 orders become the 94,931-order headline sample
- `diagnostics.md`: Phase 1 design diagnostics (no outcome comparisons)
- `naive.md`: biased late vs on-time baseline

## Decision log

Every analytical and engineering judgment is an ADR in [`docs/engineering/decisions/`](docs/engineering/decisions/README.md), each with options considered and a falsification test. The brief's six judgment calls map to ADRs tagged "(JC n)". ADR-0007 is the pre-registration, committed before any outcome was compared between late and on-time orders.

## Repository

- `data/raw/`: Olist CSVs (unmodified) + checksums
- `src/late_delivery/`: `config.py`, `build.py`, `diagnostics.py`, `naive.py`
- `tests/`: unit and data-quality tests
- `docs/`: project brief and engineering docs

## Data

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), published by Olist on Kaggle under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Files in `data/raw/` are unmodified and stay under that license; see `data/raw/README.md`.
