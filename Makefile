.PHONY: check-data build test

# Verify committed raw CSVs are byte-identical to the published dataset.
check-data:
	cd data/raw && shasum -a 256 -c SHA256SUMS

# Order-level analysis table -> data/processed/orders.parquet, outputs/exclusions.json
build: check-data
	uv run python -m late_delivery.build

test: build
	uv run pytest
