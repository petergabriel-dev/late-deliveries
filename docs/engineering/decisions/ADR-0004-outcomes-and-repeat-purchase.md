---
id: ADR-0004
title: Outcomes - share of 1-2 star reviews primary; repeat purchase secondary at 90 days (JC 5)
status: Active
date: 2026-11-13
kind: analytical
judgment_call: 5
readWhen: Building or analyzing review or repeat-purchase outcomes
---

# ADR-0004: Outcomes - share of 1-2 star reviews primary; repeat purchase secondary at 90 days (JC 5)

## Options considered

Primary review metric:

- Share of 1-2 star reviews — easy to read ("X more unhappy customers per 100 late orders") and maps onto money assumptions.
- Mean 1-5 score — the brief's wording; treats every star gap as equal and is harder to turn into money.
- Both co-primary — no single headline; adds a path for choosing results after the fact.

Reviews written before delivery (Olist emails the survey at delivery or once the promised date passes, whichever comes first):

- Keep all reviews — the full effect as customers experience it on Olist; post-delivery-only subset as a mechanism check.
- Post-delivery reviews only — cleaner story, but filters on something lateness itself causes, which biases the estimate.
- Defer until Phase 1 data checks.

Orders with several reviews (547 orders):

- Latest-answered review — one row per order, the customer's last-stated opinion.
- Drop those orders — about 0.6% of orders; small selection risk.
- Average the scores — fractional scores blur the 1-2 star outcome.

Repeat purchase:

- Secondary outcome with power set first — honest about rarity; may end as an upper bound.
- Drop it — skips judgment call 5 instead of answering it.
- Primary outcome — closest to revenue but likely too imprecise.

Repeat window and start:

- 90 days primary, 180 days as a check — about twice the late orders (5,245 vs 2,661 in profiling) and covers early 2018; similar relative power.
- 180 days primary — captures more repeat behavior but drops most of 2018.
- Count from purchase (skipping orders within 24 hours) — counts orders placed while the first was in transit.
- Count only orders placed after the first order's delivery — the customer has experienced the delivery.

## Decision

- Primary outcome `low_review` = review score of 1 or 2. Secondary: mean `review_score` (1-5).
- One review per order: the latest-answered review. A `review_id` attached to several orders counts for each of them. Orders with no review (768) drop out of review outcomes only.
- Headline estimates use all reviews, including those written before delivery. A post-delivery-only subset is reported as a mechanism check and labeled biased, because review timing is caused by lateness.
- `review_created_before_delivery` is recorded for that mechanism check.
- Repeat purchase is a secondary outcome. `repeat_90d` = the same `customer_unique_id` places a new order after the first order's delivery timestamp and within 90 days of it. `repeat_180d` is the same with 180 days, reported as a check.
- Repeat outcomes use first orders only (a customer's earliest order in the data). A first order is eligible only if delivery + window falls on or before 2018-08-31.
- The minimum detectable effect is computed before any repeat estimate. Repeat effects are estimated with regression and matching only; the RD is expected to be underpowered.
- If the repeat effect's confidence interval excludes zero, it is the direct link to money. Otherwise it is reported as an upper bound, and money translation falls back to the assumption-based link (ADR-0006).

## Why

- Project owner chose each option above (discuss and plan sessions, 2026-11-13).
- The score distribution is lopsided (1 star: 11,424; 5 stars: 57,328), so a change in the mean can hide where the shift happens.
- Profiling confirmed the survey mechanism: late orders' reviews are created at the promised date + 2 days, and 74.5% are created before delivery. Excluding them would condition on a consequence of lateness.
- 30.9% of second orders come within one day of the first (one session split into two orders); counting from delivery excludes them.
- Profiling put the 90-day minimum detectable effect at about 0.43 percentage points on a 1.15% base (about 37% relative), so a precise repeat estimate is unlikely.

## Falsification test

- Lateness shifts scores mostly between 5 and 4 stars while the 1-2 star share barely moves: the primary metric misses the effect. Check the full star distribution in Phase 2.
- Results change materially when multi-review orders are dropped: the dedup rule matters and must be reported.
- Repeat estimates at 90 and 180 days point in different directions: the window drives the conclusion.
- The minimum detectable effect on the headline sample is so large that only an implausible drop could be detected: channel 1 of the money translation cannot be measured at all.

## Affects

Docs:

- `docs/engineering/invariants.md`
- `docs/engineering/decisions/ADR-0006-money-framing.md`

Code:

- None yet (`src/late_delivery/build.py` implements this in T4)

## Consequences

- Good: a headline leadership can read and convert to money.
- Good: the repeat definition excludes split orders and in-transit orders.
- Bad/risk: the headline effect includes the "still waiting" experience specific to Olist's survey timing; it may not transfer to platforms that survey only after delivery. The memo must say so.
- Bad/risk: repeat purchase will likely end as an upper bound, which pushes the dollar range toward assumptions.

## Read when

- building `low_review`, `review_score`, `review_created_before_delivery`, `repeat_90d`, `repeat_180d`, or `is_first_order`
- estimating or interpreting any review or repeat-purchase effect

## Supersedes

- None
