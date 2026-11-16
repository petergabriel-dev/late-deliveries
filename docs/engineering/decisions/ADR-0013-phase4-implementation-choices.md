---
id: ADR-0013
title: Phase 4 implementation choices - money formulas, inputs and flag rules fixed before any money figure (JC 6)
status: Active
date: 2026-11-16
kind: analytical
judgment_call: 6
readWhen: Implementing, running, or interpreting the Phase 4 money translation, its inputs, its flags, or the disruption scenario
---

# ADR-0013: Phase 4 implementation choices - money formulas, inputs and flag rules fixed before any money figure (JC 6)

Supplements ADR-0006 (closes its three deferrals) and ADR-0012 (fixes its Phase 4 scenario method); both stay unchanged. Committed with `assumptions.toml` before any money figure was computed.
Evidence base: ADR-0004, ADR-0006, ADR-0007 §5, ADR-0011, ADR-0012, `outputs/fe.json`, plan-session profiling of `data/processed/orders.parquet`, and the outside sources cited in `assumptions.toml` (opened 2026-11-16).

## Options considered

Lead unit:

- Cost per late delivery, annual total second — independent of volume; gives a break-even per late delivery avoided.
- Annual total — the budgeting unit, but depends on the dataset's volume and on an annualization window.
- Both with equal weight — two anchors in a one-page memo.

Channel 1 (lost repeat purchases):

- 90-day effect, range 0 to the CI's far end; value per lost repeat measured from data — the pre-registered window (ADR-0004).
- 180-day window as main — a check outcome with a wider CI.
- Add an assumed customer lifetime — an unsourced multiplier on a null effect.
- Drop the channel — would supersede ADR-0006 in part.

Channel 2 (rating spillover):

- Cited ε x the measured star drop / the seller's review count x the seller's later sales, per seller — only ε and the horizon assumed.
- The same with platform averages — less code; the ratio of averages understates sellers with few reviews.
- Estimate spillover in the data — confounded by seller quality trends; not pre-registered.
- Break-even only — no unsourced number, but no dollar range for the channel.

Channel 2 horizon and dilution:

- 90 days; each later order takes the hit at the seller's review count at that moment.
- 90 days with a fixed hit at the late order's review count — ignores dilution.
- To the end of the data — the horizon then depends on when the order happened.
- 30 days as main — smallest figure.

Channel 2 anchor:

- The late order's review answer time — orders placed before the review exists cannot be hurt by it.
- The late order's purchase time — the repeat-eligibility anchor; counts 3-4 weeks before the review exists.

Channel 3 (operating costs):

- Inside the range if sourced; otherwise an illustrative add-on line outside it.
- Always inside the range, labeled illustrative — an unsourced number moves the headline.
- Named but unpriced — supersedes ADR-0006's "price all three" for this channel.

GMV: item price (commission base) or item price plus freight (overstates platform revenue unless freight is commissioned).

Exchange rate: BCB PTAX averaged over the headline window; FRED DEXBZUS over the same window; 2017 annual average only.

Assumptions file: TOML with measured inputs as references; CSV with references; TOML with every value copied (hand-copied values can drift from code output).

Range: all-low to all-high corners plus a one-at-a-time tornado; a Monte Carlo interval (needs unsourced distributions and correlations); tornado only (no range, which the brief requires).

Disruption scenario (ADR-0012): re-fit the bin effects on the check-10 sample and run the full pipeline there; scale by the check-10 / headline ratio (assumes star scores move with the 1-2 star share); re-weight Phase 2 bins by the check-10 mix only (captures about 57% of the shift).

Recommendation: break-even plus promise-first in effect sizes; the same plus a priced "one day faster" line; break-even only; an illustrative ROI (every input invented).

Source bar: causal or official figures from any setting, mismatch stated; e-commerce or Brazil only; any published figure.

Flag rules: the three rules in §6; the same with rule 2 firing when any illustrative input swings the central figure by more than 25%; report numbers only and judge by hand.

ε values: 0.05 / 0.075 / 0.10; 0.05 / 0.10 / 0.10 (central = the e-commerce estimate); 0.10 fixed.

Take rate: 0.20 fixed, sourced; 0.20 with an illustrative low for net-of-channel-fee revenue.

Channel 3 values: 0.5 / 1 / 2 contacts x the CIP cost range; 1 contact x the CIP midpoint; no number.

## Decision

All choices by the project owner, 2026-11-16 (discuss, plan and build sessions). The first option in each group above was chosen.

### 1. Lead unit, money unit, exchange rate

- The figure is the cost per late delivery: per late headline order (6,518 late orders, `fe.json` `bin_counts`). BRL first, USD alongside.
- GMV = the order's `price` (sum of item prices; freight excluded). Platform revenue = lost GMV x take rate for channels 1 and 2, with lost GMV shown alongside. Channel 3 is a direct platform cost and is not multiplied by the take rate.
- USD = BRL / rate, where rate = the simple mean of the 20 BCB monthly PTAX averages (2017-01 to 2018-08) in `assumptions.toml`.
- Annual illustration = the central cost per late delivery x late headline orders / 20 months x 12. Labeled illustrative: it uses this dataset's volume, which may not be Olist's full volume.

### 2. Channel 1: lost repeat purchases (measured, upper bound)

- Per late delivery: lost GMV = |e| x V; platform revenue = lost GMV x take rate.
- e = `repeat_90d/a` from `fe.json` (now -0.002404, 95% CI [-0.004878, 0.000071]). Cost ends: low = max(0, -ci95_high) = 0 here, central = max(0, -estimate), high = max(0, -ci95_low).
- V = mean `repeat_90d_gmv` over headline first orders eligible for 90 days with `repeat_90d` true.
- Applied to every late headline order. The effect was estimated on first orders only, so this extrapolates; the channel is an upper bound (ADR-0004).
- Tornado row "repeat window 180 days": e and V replaced by `repeat_180d/a` and `repeat_180d_gmv`, same cost-end rule.

### 3. Channel 2: rating spillover (ε assumed; the rest measured)

Per late delivery: lost GMV = ε x Σ_b w_b x |β_b| x E_b(H) x r; platform revenue = lost GMV x take rate.

- b = the four days-late bins of ADR-0008 §2 (1-2, 3-7, 8-14, 15+).
- β_b = `review_score/b` from `fe.json` (now -0.743567, -1.997445, -2.518684, -2.466503 stars). Cost ends from each bin's 95% CI: low = max(0, -ci95_high), high = max(0, -ci95_low).
- w_b = share of late headline orders with a review that fall in bin b; r = late headline orders with a review / all late headline orders. Both measured.
- E_b(H) = the mean of X_i(H) over eligible late headline orders i with a review in bin b, where X_i(H) = Σ_j price_j / N_j:
  - s = the seller of order i; a_i = its `review_answer_ts`.
  - j runs over single-seller orders of s (any exclusion reason) whose status is not canceled or unavailable and whose `purchase_ts` lies in (a_i, a_i + H days].
  - N_j = the number of single-seller orders of s (any status or window) whose `review_answer_ts` is before j's `purchase_ts`: the reviews visible when j was placed. N_j >= 1 because i's own review counts.
  - Eligible: a_i + H days < 2018-09-01 (`C.FOLLOWUP_END`).
- Meaning: one review |β_b| stars lower moves an average of N_j reviews down by |β_b| / N_j stars, and the seller's sales fall by ε per star. The loss fraction ε x |β_b| / N_j must lie in [0, 1]; otherwise the code raises.
- E_b is computed separately for each H with its own eligible set; w_b stays the full late-with-review mix, so each H keeps the headline's lateness mix but not its period mix. Eligible counts per H and bin are reported. A bin with no eligible late order raises.
- Multi-seller orders carry no `seller_id`, so they are neither later orders j nor reviews counted in N_j (slight understatement).

### 4. Channel 3: operating costs

- Per late delivery: contacts per late order x cost per contact (BRL, direct cost).
- Both inputs are illustrative, so channel 3 is an add-on line with its own low / central / high. It never enters the headline range, the tornado or flags 1-2. It would join the range only if both inputs became sourced, which needs a new ADR.

### 5. Range and tornado

- Headline money per late delivery = channel 1 + channel 2 platform revenue (lost GMV alongside).
- Central: every input at its value; measured inputs at point estimates.
- Low corner: every input at its low-cost end; high corner: every input at its high-cost end. Measured ends come from 95% CIs as in §2-§3. Labeled bounds, not a confidence interval.
- Tornado, from the central case, one row at a time moved to its low-cost and high-cost ends: ε, H, take rate, star-drop bins (all four together), repeat effect 90 days, repeat window 180 days. Swing = high - low; rows sorted by swing.

### 6. Flag rules (computed in code; ADR-0014 reads them)

| Flag | Test it implements | Fires when |
|---|---|---|
| 1 | ADR-0006: the assumed channels make up nearly all of the range | channel 1 central platform revenue < 10% of the central headline total (`MONEY_MEASURED_SHARE_MIN` = 0.10 in `config.py`) |
| 2 | ADR-0006: one unsourced assumption flips the recommendation | the tornado row with the largest swing is an illustrative input (`illustrative = true`). The recommendation is a threshold, not a yes/no, so "flips" is read as "drives the figure most" |
| 3 | ADR-0012: the disruption scenario changes the recommendation | the scenario's central figure lies outside [headline low corner, headline high corner] |

A fired flag stands as computed. ADR-0014 states what the memo must lead with.

### 7. Disruption scenario (ADR-0012 Phase 4)

- Frame: `robustness.check_frames(t)[10]` (surge and strike excluded, ADR-0011 §3); the models keep orders with a review.
- `fe.fit` with `LATE_BIN_COLS` (model (b): ADR-0007 §1 controls, seller and purchase-week fixed effects, singletons dropped, CRV1 by seller) for `review_score` and `low_review`, plus model (a) for `low_review` (the observed check-10 estimate; it must equal `robustness.json` check 10).
- Channel 2 recomputed with the re-fit `review_score` bins, the check-10 late orders' mix w'_b and review share r', and E'_b(H) over eligible check-10 late orders. Later orders j are not restricted: sales in the disrupted periods happened.
- Channel 1 unchanged (Phase 2 repeat effect and value).
- Reported: low / central / high per late delivery, and flag 3.
- Lateness-mix decomposition (ADR-0012, now from code): Σ_b w_b x Phase 2 `low_review/b` (headline mix) and Σ_b w'_b x the same Phase 2 bins (check-10 mix); predicted drop = their difference; observed drop = `fe.json` headline - the check-10 model (a) estimate. ADR-0012 quotes 0.5206, 0.5066 and a predicted drop of 0.0140; a mismatch triggers ADR-0012's falsification test.

### 8. Assumptions file and source bar

- `assumptions.toml` at the repo root, read with stdlib `tomllib`. Assumed inputs carry value, low, high, unit, tag, and at least one source (citation, URL, verbatim quote, date opened) or `illustrative = true`. Measured inputs carry a `ref` to `fe.json` (model id and terms) or to `orders.parquet` columns, with no number.
- The loader raises on a missing field, low > value or value > high, an assumed input with neither source nor `illustrative = true`, or a `ref` that does not resolve.
- Source bar: an input is sourced if it rests on a peer-reviewed or working-paper causal estimate from any online-review setting, or on a company's or regulator's own figure (a company figure reported in the press counts). E-commerce or Brazilian sources are preferred; any setting mismatch is stated next to the input. Industry blogs, vendor documentation and trade-press surveys are illustrative only.
- Values (details and quotes in `assumptions.toml`):

| Input | Low | Value | High | Status |
|---|---|---|---|---|
| ε (share of sales per star) | 0.05 | 0.075 | 0.10 | sourced: Luca (Yelp restaurants, 5-9% per star) and Magnusson 2022 (Wayfair products, 5% per half star, doubled); mismatch stated |
| Take rate | 0.20 | 0.20 | 0.20 | sourced: Olist's 20% commission (Mercado&Consumo 2017-06-26; Exame 2019-10-23); gross of channel fees |
| H (days) | 30 | 90 | 180 | illustrative (owner choice) |
| Contacts per late order | 0.5 | 1 | 2 | illustrative (no source) |
| Cost per contact (BRL) | 6.06 | 6.32 | 6.58 | illustrative (CIP study via Consumidor Moderno 2019) |
| BRL per USD | | 20 monthly values | | BCB SGS 3698 = monthly mean of the daily PTAX selling rate (SGS 1), verified for all 20 months |

### 9. Recommendation numbers

- Break-even: the headline platform-revenue range per late delivery (low, central, high; BRL and USD). Logistics spending is worth it only where its cost per late delivery avoided is below this.
- Promise-first: broken-promise-equivalent days = `low_review/c` late / `low_review/c` delivery_days, a ratio of point estimates without a CI (now 0.431842 / 0.004106). Model (e) slowness bins are quoted from `fe.json`.
- Caveat stated with the recommendation: the data has no checkout conversion, so the cost of padding promised dates is unmeasured.

### 10. Build columns, code placement, outputs

- `build.py` adds `review_answer_ts` (the kept review's answer timestamp) and `repeat_{w}d_gmv` (item price of the same person's orders under the exact `repeat_{w}d` rule; eligible first orders only, 0 when no repeat). No ADR-0003..0005 definition changes.
- `money.py`: pure functions plus `main()`. It reuses `fe.fit`, `fe.LATE_BIN_COLS` and `robustness.check_frames`; it copies no mask.
- Parameters in `config.py` with a comment naming this ADR: `ASSUMPTIONS_TOML`, `MONEY_MEASURED_SHARE_MIN` = 0.10, `LATER_ORDER_EXCLUDED_STATUSES` = (canceled, unavailable).
- Outputs: `outputs/money.{md,json}` and `fig_money_tornado.png`, from `make money` (after `fe`), which joins `make all`. The JSON echoes every input with its tag and source, the eligible counts, and the rule text of each flag.

### 11. What was known when this was written

- Every Phase 2 and Phase 3 estimate (ADR-0010, ADR-0012). No money figure had been computed.
- From the discuss session: channel 1 is roughly R$0.34 of GMV per late delivery, at most about R$0.69 (one repeat order at the mean order price), so flag 1 is likely to fire.
- From plan-session profiling: the share of late orders with purchase + H before 2018-09-01 is 94.4% (H 30), 89.7% (H 90) and 62.0% (H 180); the answer-time anchor keeps fewer.

## Why

- Closing every fork before the first money figure keeps the pre-registration order of Phases 2 and 3; git order shows it.
- Channel 2 uses data for everything except ε and H, so only two numbers rest on judgment. Per-later-order dilution follows how an average rating actually moves.
- Starting the horizon when the review is posted counts only sales that could have seen it.
- Corners and a tornado are deterministic and need no distribution guesses; the tornado shows which input drives the figure, which is what ADR-0006's falsification test asks.
- Flags computed in code by rules fixed now cannot be bent after the results.
- Measured inputs stay as references, so the file cannot drift from code output (invariant 6).
- Re-fitting the bins on the check-10 sample measures the disruption scenario's own effects instead of assuming they scale.

## Falsification test

- A hand-computed exposure, a loader guard or a flag-branch unit test fails: the implementation does not match this specification.
- The specification echo in `outputs/money.json` differs from this ADR (inputs, H, anchor, statuses, thresholds): the implementation drifted, and the figure is not the pre-registered one.
- The check-10 model (a) estimate in `money.json` differs from `robustness.json` check 10: the frames diverged, and no scenario result is reported until fixed.
- A loss fraction above 1, or a bin with no eligible late order: the formula does not fit the data; a superseding ADR comes before any workaround.
- A cited source turns out not to say what its quote says, or is withdrawn: the input becomes illustrative and the flags are recomputed.
- Evidence that buyers on Olist's channels do not see seller ratings: channel 2's mechanism does not apply, and a superseding ADR must drop or relabel it.

## Affects

Docs:

- `docs/engineering/decisions/ADR-0006-money-framing.md` (supplemented; its deferrals closed here; text unchanged)
- `docs/engineering/decisions/ADR-0012-phase3-robustness-reading.md` (its Phase 4 scenario method fixed here; text unchanged)
- `docs/engineering/decisions/ADR-0004-outcomes-and-repeat-purchase.md` (channel 1 reuses its repeat rule)
- `docs/engineering/invariants.md` (invariant 6 to name `assumptions.toml`; planned, T30)

Code:

- `assumptions.toml` (this commit)
- `src/late_delivery/build.py` (`review_answer_ts`, `repeat_{w}d_gmv`; planned, T26)
- `src/late_delivery/config.py` (Phase 4 parameters; planned, T27)
- `src/late_delivery/money.py` (planned, T27-T28)
- `tests/test_money.py` (planned, T27)
- `Makefile` (`money` target; planned, T28)

## Consequences

- Good: every Phase 4 fork is closed before any money figure; every input is versioned with its source or its illustrative label.
- Good: the measured and assumed parts stay separable, and the flags are computed, not judged.
- Bad/risk: ε comes from product and restaurant ratings, and its high end doubles a half-star threshold effect linearly; neither study measures small moves in a seller's average rating.
- Bad/risk: the take rate is Olist's gross commission; any channel fees Olist pays are not netted, so platform revenue may be overstated.
- Bad/risk: H is illustrative and may drive the figure most, in which case flag 2 fires.
- Bad/risk: corners stack every extreme, so the range is wide; the period mix differs across H.
- Bad/risk: channel 1 is extrapolated to non-first orders, multi-seller orders are ignored in channel 2, and channel 3 rests only on illustrative inputs.

## Read when

- implementing or running `money.py`, the Phase 4 build columns, or `assumptions.toml`
- interpreting any Phase 4 money figure, flag, tornado row, or the disruption scenario

## Supersedes

- None (supplements ADR-0006 and ADR-0012)
