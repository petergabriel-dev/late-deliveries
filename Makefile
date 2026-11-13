.PHONY: all check-data build test diagnostics naive

# One command rebuilds every Phase 1 result from the committed raw CSVs.
all: test diagnostics naive

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
