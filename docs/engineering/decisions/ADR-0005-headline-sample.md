---
id: ADR-0005
title: Headline sample - delivered single-seller orders purchased 2017-01-01 to 2018-08-31
status: Active
date: 2026-11-13
kind: analytical
judgment_call: none
readWhen: Building the sample flags or explaining who the estimate covers
---

# ADR-0005: Headline sample - delivered single-seller orders purchased 2017-01-01 to 2018-08-31

## Options considered

Which orders:

- Delivered, single-seller orders — clean seller fixed effects; canceled and undelivered orders counted but excluded; multi-seller orders as a robustness check.
- All delivered orders — keeps multi-seller orders by assigning each to its largest-value seller; muddier fixed effects and one more rule to log.
- Include never-delivered orders as a "never arrived" extreme — captures the worst harm, but cancellations have many causes besides delivery.

Date window:

- 2017-01-01 to 2018-08-31 — drops only the near-empty 2016 and late-2018 months.
- 2017-02-01 to 2018-08-31 — also drops the January 2017 ramp-up month (800 orders).

## Decision

- Headline sample (`in_headline`): order status delivered, customer delivery timestamp present, exactly one seller, purchase timestamp from 2017-01-01 through 2018-08-31 inclusive.
- Every one of the 99,441 orders stays in the built table with an `exclusion_reason`; the exclusion counts are reported.
- Canceled and undelivered orders are excluded from the headline. Because the worst outcomes drop out, the estimate is labeled conservative.
- Multi-seller orders (1,278) are excluded from the headline and used only as a robustness check.
- Black Friday 2017 (2017-11-24) stays in the headline sample; excluding it is a robustness check.

## Why

- Project owner chose these options (discuss and plan sessions, 2026-11-13).
- Profiling: 2016 has at most 324 orders per month; 2018-09 and 2018-10 have 16 and 4. The share of orders never delivered stays at 1.1-2.9% per month through 2018-08, so there is no sign that late deliveries are missing at the end of the window.
- Single-seller orders give each order one seller, which seller fixed effects require.

## Falsification test

- Including multi-seller orders, or excluding Black Friday, moves the estimate beyond its confidence interval (Phase 3): the sample choice drives the result.
- The never-delivered share is strongly concentrated among sellers or periods with high lateness: excluding those orders biases the estimate by more than "conservative" implies.
- Starting the window at 2017-02-01 changes the estimate materially: the ramp-up month behaves differently.

## Affects

Docs:

- `docs/engineering/invariants.md`

Code:

- None yet (`src/late_delivery/config.py` and `build.py` implement this in T4)

## Consequences

- Good: clean seller fixed effects and a well-populated window.
- Good: every excluded order is still counted, so the exclusions can be audited.
- Bad/risk: the estimate covers delivered single-seller orders only and understates harm from orders that never arrive.

## Read when

- building `in_headline` or `exclusion_reason`
- explaining which orders an estimate covers

## Supersedes

- None
