# What does a late delivery cost?

A late delivery costs the platform about **R${money:cases.central.brl.total_revenue:.0f} [US${money:cases.central.usd.total_revenue:.2f}] in lost commission** (range R${money:cases.low.brl.total_revenue:.2f}–R${money:cases.high.brl.total_revenue:.2f} [US${money:cases.low.usd.total_revenue:.2f}–US${money:cases.high.usd.total_revenue:.2f}]), but almost all of this rests on outside estimates of how lower ratings cut sellers’ later sales. The directly measured repeat-purchase loss is only R${money:cases.central.brl.channel1_revenue:.2f} [US${money:cases.central.usd.channel1_revenue:.2f}]; a clear change in repeat buying was not detected.

## Evidence and limits

Estimated harm: about **{report:memo_review_more:.0f} more unhappy reviews per {report:memo_review_scale} late orders**. Matching similar orders agrees. On the same scale, a comparison near the promised date gives {report:memo_rd_more:.0f}, but cannot measure the promise’s effect reliably because orders either side differ. Excluding disruption periods lowers the headline to {report:memo_disruption_more:.0f}. Orders were not assigned at random; unmeasured differences may explain some harm.

## What to measure next

The biggest unknown is how long a bad review hurts later sales. At assumed lifetimes of {assumptions:inputs.horizon_days.low:.0f}, {assumptions:inputs.horizon_days.value:.0f} and {assumptions:inputs.horizon_days.high:.0f} days, the cost is R${report:memo_horizon_low_brl:.2f} [US${report:memo_horizon_low_usd:.2f}], R${money:cases.central.brl.total_revenue:.2f} [US${money:cases.central.usd.total_revenue:.2f}] and R${report:memo_horizon_high_brl:.2f} [US${report:memo_horizon_high_usd:.2f}], respectively. Measure that duration in Olist’s own channel sales; check whether buyers see seller ratings.

**Support costs are separate, outside this range.** If each late delivery triggers {assumptions:inputs.contacts_per_late_order.value:.0f} support contact (unmeasured), add about R${money:channel3_addon.central.brl:.0f} [US${money:channel3_addon.central.usd:.2f}]. Measure contacts from Olist’s support records next.

**Illustrative annual loss at this dataset’s volume:** about {money:annual_illustration.late_orders_per_year:,.0f} late deliveries, costing R${money:annual_illustration.central_revenue_brl:,.0f} [US${money:annual_illustration.central_revenue_usd:,.0f}] a year. This may not be Olist’s full volume.

Details: [estimates](../../outputs/fe.md), [checks](../../outputs/robustness.md), [costs](../../outputs/money.md).

## Recommendation

Fund faster logistics only where avoiding a late delivery costs less than about **R${money:recommendation.break_even_per_late_delivery.central.brl:.0f} [US${money:recommendation.break_even_per_late_delivery.central.usd:.2f}]**, using the range above. **Make promised dates accurate before buying speed:** a broken promise hurts reviews as much as about {money:recommendation.broken_promise_equivalent_days:.0f} extra delivery days—a rough comparison, not a tested trade-off. **Test longer promised dates first**, before rolling them out: the data do not show whether longer promises deter purchases.
