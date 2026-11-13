.PHONY: check-data test

# Verify committed raw CSVs are byte-identical to the published dataset.
check-data:
	cd data/raw && shasum -a 256 -c SHA256SUMS

test: check-data
	uv run pytest
