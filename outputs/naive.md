# Naive baseline: BIASED BASELINE, NOT A CAUSAL ESTIMATE

Late minus on-time difference on the headline sample (ADR-0005), with 95% confidence intervals from a normal approximation. Late orders differ from on-time orders in observed and unobserved ways, so this difference is **not** the effect of lateness. The estimates of record come from the pre-registered methods in ADR-0007.

| outcome | population | n_late | n_on_time | mean_late | mean_on_time | difference | ci95_low | ci95_high |
|---|---|---|---|---|---|---|---|---|
| low_review (primary) | headline orders with a review | 6366 | 87936 | 0.6239 | 0.0871 | 0.5368 | 0.5248 | 0.5488 |
| review_score | headline orders with a review | 6366 | 87936 | 2.2714 | 4.3113 | -2.0398 | -2.0791 | -2.0005 |
| repeat_90d | eligible first orders | 5242 | 66888 | 0.0080 | 0.0118 | -0.0038 | -0.0063 | -0.0012 |
| repeat_180d | eligible first orders | 2658 | 49046 | 0.0135 | 0.0187 | -0.0051 | -0.0097 | -0.0006 |

low_review and repeat outcomes are shares (0-1); review_score is on the 1-5 scale.
