# Scoring Reference

## Active IPO Filter

An IPO is considered active for an `as_of` date when:

1. `apply_start_date <= as_of`, and
2. `as_of <= apply_end_date`.

Confirm application dates from live or archived web sources fetched during the current invocation. Do not infer an active window from listing date alone.

## LLM Scoring Rubric

Assign the final 0-100 score manually from extracted evidence:

- Demand / heat, 30 points: public subscription multiple, margin/孖展 multiple, subscriber count, relative heat versus concurrent IPOs, demand acceleration, and market attention. Strong positive when demand is high but not obviously overheated. Do not rank by a single day's margin multiple alone.
- Allocation practicality, 15 points: one-lot success rate, broker or third-party predicted allocation, entry fee, financing cost, and whether a retail subscriber has a realistic allocation chance.
- Deal quality and fundamentals, 20 points: sponsor quality, industry, profitability or commercialization status, revenue growth, margins, cash flow, cornerstone information, issue size, valuation clues, pricing range, A/H or comparable-company valuation anchors, and whether the business story is likely to convert into trading demand.
- Market/listing signal, 20 points: gray market data, first-day data if already known, recent HK IPO sentiment, and days to listing.
- Data confidence, 15 points: completeness, source quality, and cross-source agreement. Penalize heavily when key facts are missing or only one source confirms the window.

For a past-date analysis, avoid using post-date trading outcomes unless the user explicitly requests a hindsight review.

## Heat Curve Adjustments

Apply these corrections before final ranking:

- Early-offer adjustment: if the as-of date is day 1 of subscription, treat margin/孖展 multiple as immature. Do not penalize a stock heavily for low first-day margin if deal quality, sponsor quality, low entry fee, or market theme are strong. Label the heat as `首日未充分发酵`.
- Mature-offer adjustment: if the as-of date is near the final subscription day, margin/孖展 multiple is more reliable and should carry more weight.
- Overheated narrative discount: high margin plus a fashionable theme is not enough. Discount stocks where the heat is mostly narrative-driven and there is weak evidence of profitability, valuation support, cornerstone quality, or broad aftermarket buyer demand.
- Underappreciated quality boost: raise stocks with moderate heat but stronger fundamentals, lower valuation pressure, or clearer profit visibility because they may outperform hotter narrative names in dark-pool/open trading.
- Same-day comparison rule: compare IPOs at similar subscription stages when possible. If candidates are at different stages, explicitly adjust for days since application opened.
- Backtest learning rule: use historical cases only to improve general feature checks. Do not memorize company-specific outcomes or add name-specific patches. Generalize lessons into features such as subscription stage, heat acceleration, relative demand, fundamentals, valuation support, and narrative-to-aftermarket conversion risk.

## Relative Heat And Fundamentals

When multiple IPOs are active on the same date, compute a relative view before ranking:

- Stage-adjusted heat: compare each IPO's margin/public subscription multiple against candidates at a similar subscription day. If stages differ, say so and reduce confidence.
- Relative percentile: classify each candidate as top-tier, above-average, average, or weak versus concurrent IPOs by demand metrics.
- Heat acceleration: prefer demand that is accelerating into close over a static one-day number.
- Fundamentals overlay: a high-heat IPO with weak fundamentals can score below a lower-heat IPO with clearer profit visibility, stronger sponsor/cornerstones, better valuation support, or A/H valuation anchor.
- AH overlay: for A/H listings, compare H-share pricing to the A-share market value and liquidity. A large discount, strong A-share momentum, or clear valuation anchor can support aftermarket demand; a stretched premium can be a warning.

## Rating Bands

- `A`: score >= 80
- `B`: score >= 65
- `C`: score >= 50
- `D`: score < 50

## Interpretation

Prefer explaining the top 3 positive and negative drivers. Mention missing data explicitly when it affects confidence. Always add that IPO subscriptions can lose money and that the score is only a decision aid.

## Allocation Difficulty Labels

When enough evidence exists, label 中签难度 in plain Chinese:

- `极难`: very high oversubscription/margin multiple or very low predicted one-lot chance.
- `偏难`: demand is clearly hot, but not at extreme levels.
- `中等`: moderate subscription evidence or mixed broker signals.
- `较易`: weak demand, high entry barrier, or high expected allocation chance.

Always show the numerical basis next to the label, such as `孖展约 650x`, `公开认购约 120x`, `预测一手中签率约 15%`, or `未找到预测中签率`.
