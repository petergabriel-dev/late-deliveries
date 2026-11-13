---
id: ADR-0009
title: Matching - drop orders perfectly predicted by the propensity model (supersedes ADR-0008 §4 in part) (JC 3)
status: Active
date: 2026-11-13
kind: analytical
judgment_call: 3
readWhen: Running, changing, or interpreting the propensity-score matching estimate
---

# ADR-0009: Matching - drop orders perfectly predicted by the propensity model (supersedes ADR-0008 §4 in part) (JC 3)

Triggered by ADR-0008's falsification test ("the logit does not converge: a superseding ADR is needed before any workaround").
Committed before the matching estimate was computed on any outcome. The FE grid (T11) and donut RD (T12) results already existed; this choice uses only the treatment model, not outcomes.

## Options considered

The ADR-0008 §4 propensity logit (`late` on the control set minus seller, with week dummies; 94,302 headline orders with a review, 192 columns) stops at 100 iterations without converging. Eight dummy levels contain no late orders: purchase week 2018-08-27 (113 orders) and seven main categories (99 orders), 211 orders in all. Their coefficients diverge (-12 to -19), their logit scores reach -16 to -38, and the SD of the logit score that sets the caliper rises from 1.150 to 1.408.

- Drop perfectly predicted orders — remove each level with no late orders (or no on-time orders) and its orders from the matching sample before fitting; Stata's logit does this by default. No late order is lost here; the dropped orders could never be valid matches.
- Merge the rare levels — pool the categories into a level that has late orders and the last week into the one before it, for the logit only. Needs an arbitrary pooling rule; a merged week conflicts with exact matching on week.
- Penalized logit (ridge or Firth) — keeps every row with finite coefficients; changes the estimator and adds a penalty strength to choose; Firth is not in statsmodels.
- Keep the specification and raise the iteration limit — the maximum likelihood estimate does not exist, so the scores depend on when the optimizer stops, and the caliper stays inflated.

## Decision

Project owner, 2026-11-13 (build session, T13). The first option above.

- Before fitting the propensity model, drop from the matching sample every order in a level of `purchase_week`, `main_category` or `customer_state` that has no late orders, or no on-time orders, among the remaining orders. Repeat until no such level remains.
- Report the number of orders dropped, split into late and on-time, and the levels involved.
- The caliper SD, the balance table (pre-match pooled SD) and the matched sample all use the remaining orders.
- The logit must converge on the remaining sample; otherwise matching stops again.
- Everything else in ADR-0008 §4 is unchanged: exact match on week, 1:1 nearest neighbor with replacement, caliper 0.2 SD, ties to the lowest `order_id`, ATT by weighted OLS with seller-clustered SEs, per-level weighted SMD.
- ADR-0008 stays Active; only its §4 propensity sample is superseded.

## Why

- A late order can only be matched within its own week, and an order in a level with no late orders has an estimated propensity of about zero, so it can never be a valid match for a late order.
- Without the drop, the logit never converges, so the scores depend on when the optimizer stops.
- The divergent scores inflate the SD that sets the caliper by about 22%, which loosens every match.
- Dropping perfectly predicted observations is the standard convention (Stata's `logit` default), so no new tuning choice is introduced.
- In the current data no late order is dropped, so the ATT still covers every late order with a review.

## Falsification test

- The logit still fails to converge after the drop: the remaining problem is not separation, and matching stops for a new decision.
- The drop removes late orders: the ATT no longer covers all late orders, and the report must say how many were lost.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0008-phase2-implementation-choices.md` (§4 propensity sample superseded; text unchanged)

Code:

- `src/late_delivery/matching.py` (planned, T13)

## Consequences

- Good: the propensity model converges, the scores are well defined, and the caliper has the width ADR-0008 intended.
- Good: no late order is lost, so the estimand is unchanged.
- Bad/risk: 211 on-time orders (0.2% of the matching sample) are left out of matching only; the regression models keep every row.
- Bad/risk: this choice was made after the FE and RD results were seen, though before any matching outcome was computed and using the treatment model only.

## Read when

- running, changing, or interpreting the propensity-score matching estimate
- auditing why the matching sample is smaller than the FE review sample

## Supersedes

- ADR-0008 §4, the propensity-model sample only
