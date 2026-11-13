# Project Brief: What Does a Late Delivery Actually Cost?

Nov 13, 2026 · @Peter

## Overview

Estimate the causal effect of late deliveries on customer satisfaction and repeat purchases, then translate it into a dollar figure leadership can act on.

**Scenario.** You are an analyst at an e-commerce marketplace. Leadership is deciding whether to invest in faster logistics and asks: *what does a late delivery actually cost us?*

**Why this project.** The dataset is public and widely used for exploratory charts, but rarely for careful causal work. The goal is not to show tooling. It is to show an answer a business would pay for, and why that answer can be trusted.

**Working principle.** AI agents build; I make and record every analytical judgment. The decision log is a first-class deliverable, not an afterthought.

## Data

The source is the Olist Brazilian E-Commerce public dataset on Kaggle: about 100k real orders from 2016 to 2018, split across linked tables.

| Table | What it gives this project |
| --- | --- |
| Orders | Purchase, carrier handoff, actual delivery and **estimated (promised) delivery** timestamps |
| Reviews | Review score (1–5) and comment per order |
| Customers | `customer_id` (per order) and `customer_unique_id` (per person), location |
| Order items | Product, seller, price, freight value |
| Payments | Payment type, installments, value |
| Sellers / Products | Seller location, product category and attributes |

The promised-vs-actual delivery dates are what make a causal design possible. Note the Black Friday 2017 volume spike and the thin data at the start and end of the period.

## Judgment calls to make and log

These are deliberately left open. Each one gets a decision-log entry: options considered, choice, reasoning, and what evidence would prove it wrong.

1. **Defining "late."** Late against the promised date, or against typical delivery time? A binary flag, or days late (dose-response)?
2. **Confounders.** Late orders are not random. Seller quality, product category, distance, freight cost and seasonal volume may drive both lateness and bad reviews. Which can be controlled for, and which cannot?
3. **Identification strategy.** Build a ladder of methods and compare their estimates:
   - Naive late vs. on-time comparison (expected to be biased)
   - Regression with controls and seller fixed effects
   - Propensity score matching
   - Regression discontinuity around the promised date: orders arriving just before vs. just after it
4. **Reconciling estimates.** If the methods disagree, which one do you trust, and why?
5. **The repeat-purchase trap.** Use `customer_unique_id`, not `customer_id`, to track people. Repeat purchases are rare. Is the repeat-purchase question answerable, or does it need reframing?
6. **Effect to money.** What assumptions turn "lower review score" into lost revenue, and how sensitive is the final number to each?

## Goals and phases

The project has three goals; each phase below moves forward only when its exit criteria are met.

**Goals**

- **Answer the question:** a defensible causal estimate of what late delivery costs, as a dollar range.
- **Show the judgment:** every analytical fork is visible in the decision log.
- **Prove reproducibility:** one command rebuilds every result from raw data.

**Phase 1 — Foundation.** Join the tables, define the grain (one row per order), write data-quality checks, and define the treatment and outcome variables.

- Exit: data-quality tests pass; "late" and outcome definitions are logged; naive comparison is computed as the baseline.

**Phase 2 — Identification.** Build the method ladder: controlled regression, seller fixed effects, matching, and the regression discontinuity at the promised date.

- Exit: each method has an estimate with uncertainty; where they converge or diverge is explained in the log.

**Phase 3 — Robustness.** Stress-test the preferred estimate: alternative "late" definitions, excluding the Black Friday spike, placebo tests, sensitivity to unobserved confounding.

- Exit: you can state how much the estimate moves under each check, and which assumptions it rests on.

**Phase 4 — Business translation.** Convert the effect into money: review score to repeat purchase or customer value, then to revenue. Run a sensitivity analysis on each assumption.

- Exit: a dollar range with explicit assumptions, plus a recommendation.

**Phase 5 — Communication.** Write the stakeholder memo and technical write-up; polish the repo.

- Exit: a non-technical reader can act on the memo; a technical reviewer can audit every step.

## Deliverables

| Deliverable | Audience | Contents |
| --- | --- | --- |
| Stakeholder memo (1 page) | Manager / leadership | The answer, a dollar range, a recommendation, key caveats; no jargon |
| Technical write-up | Analysts, hiring reviewers | Method ladder, robustness checks, limitations up front |
| Decision log | Anyone auditing the work | Every judgment call: options, choice, reasoning, falsification test |
| Reproducible repo | Technical reviewers | One command from raw CSVs to final figures; README leads with question and answer |

## Definition of done

- [ ] The README states the question and the answer in its first three lines
- [ ] At least three identification methods are compared, with disagreements explained
- [ ] Limitations are stated near the top, not buried at the end
- [ ] Every number in the memo traces to code in the repo
- [ ] The decision log covers all six judgment calls above
- [ ] A cold reviewer can rebuild all results with one command
- [ ] The memo ends with a recommendation, not just a finding
