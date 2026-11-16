.PHONY: all check-data build test diagnostics naive fe rd matching ladder robustness

# One command rebuilds every result from the committed raw CSVs.
all: test diagnostics ladder robustness

# Verify committed raw CSVs are byte-identical to the published dataset.
check-data:
	cd data/raw && shasum -a 256 -c SHA256SUMS

# Order-level analysis table -> data/processed/orders.parquet, outputs/exclusions.json
build: check-data
	uv run python -m late_delivery.build

test: build
	uv run pytest

# Phase 1 design diagnostics (no outcome contrasts) -> outputs/diagnostics.{md,json}, figures
diagnostics: build
	uv run python -m late_delivery.diagnostics

# Naive late vs on-time baseline (biased; allowed after ADR-0007) -> outputs/naive.{md,json}
naive: build
	uv run python -m late_delivery.naive

# Pre-registered FE regression grid (ADR-0007, ADR-0008) -> outputs/fe.{md,json}
fe: build
	uv run python -m late_delivery.fe

# Donut RD at the promised date (corroborating; ADR-0008 §3) -> outputs/rd.{md,json}, fig_rd.png
rd: build
	uv run python -m late_delivery.rd

# Propensity-score matching (corroborating; ADR-0008 §4, ADR-0009) -> outputs/matching.{md,json}
matching: build
	uv run python -m late_delivery.matching

# Method ladder: all estimates, ADR-0007 §4 verdicts and falsification flags -> outputs/ladder.{md,json}, fig_ladder.png
ladder: naive fe rd matching
	uv run python -m late_delivery.ladder

# Phase 3: the 12 pre-registered robustness checks and their flags (ADR-0011) -> outputs/robustness.{md,json}, fig_robustness.png
robustness: fe rd
	uv run python -m late_delivery.robustness
