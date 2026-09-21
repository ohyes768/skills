# Live Data Sources And Cross-Checks

## Required Rule

Fetch sources during every invocation. Do not answer availability from local CSV files, cached datasets, previous run outputs, screenshots, or legacy ML/model artifacts.

For each candidate IPO, try to confirm the subscription window with at least two independent sources. If only one source is available, mark the data confidence lower and state the limitation.

## Source Priority

Use a mix of exchange/issuer, financial portals, and broker calendars:

- AASTOCKS IPO main page: `https://www.aastocks.com/sc/stocks/market/ipo/mainpage.aspx`
- ETNet IPO calendar/info: `https://www.etnet.com.hk/www/tc/stocks/ipo-calendar.php` and `https://www.etnet.com.hk/www/tc/stocks/ipo-info.php`
- Futu/Moomoo HK IPO pages: `https://www.moomoo.com/hans/quote/hk/ipo?from=futunn` and related issuer pages
- CNYES HK IPO: `https://www.cnyes.com/hkstock/ipo`
- Third-party prediction/calculator tools such as TradeSmart HK IPO Predictor when available: `https://www.lowrisktradesmart.org/`
- Hong Kong broker IPO calendars such as 新質證券 and 耀才/財華 pages when search finds them
- HKEX listing documents or the prospectus when issue details need confirmation

Do not use HKEX PDFs as the default source for financial fundamentals. For revenue, profit/loss, margins, cash flow, customer concentration, R&D and shareholder data, follow `financial-research.md` and search live public web sources during every invocation. Use HKEX only to confirm offer terms and formal announcements.

The key fields to extract are stock code, company name, application start date, application close date, listing date, offer price/range, lot size or entry fee, sponsor, industry, public subscription multiple, margin/孖展 subscription amount and multiple, applicant count, one-lot success rate, broker or third-party predicted allocation, final allotment details when relevant, and the subscription day number for the user's as-of date.

When available, collect a heat curve rather than one snapshot: first-day margin, latest margin before the user's time, final margin/public subscription multiple, and whether demand accelerated or faded.

Also collect fundamentals and deal-quality evidence: revenue growth, profitability, gross margin, cash flow, R&D intensity, market share or industry rank, customer concentration, regulatory or litigation risks, use of proceeds, cornerstone investors, sponsor quality, valuation range, and comparable-company multiples.

For A/H or dual-listed candidates, collect the existing listed share price, A/H premium or discount, recent A-share momentum and turnover, and whether the H-share offer valuation is anchored by a visible public-market comparable.

## Conflict Handling

- If sources disagree on dates, prefer issuer/prospectus/HKEX documents, then exchange-style IPO calendars, then financial portals, then broker calendars.
- If a candidate appears on a listing calendar but no application dates can be confirmed, do not count it as "available to subscribe"; list it separately as unconfirmed if relevant.
- If the user's date is in the past, use archived/current pages and contemporaneous news to reconstruct the subscription window, but score from information that would reasonably have been available on that date unless the user asks for hindsight.
- Distinguish "as-of-date" demand metrics from final allotment results. For example, a margin multiple reported during the offer period is contemporaneous evidence; a final public subscription multiple or one-lot rate published after close is hindsight unless the user explicitly requests it.
- For backtests, fetch actual outcomes only after they have occurred: dark-pool/gray-market close, listing-day open, listing-day close, and first-day percentage changes versus offer price. Do not backtest future or not-yet-listed IPOs.
- Futu/Moomoo may provide IPO centers, key dates, financing tools, commentary, and allotment education, but publicly crawlable pages may not expose a stable predicted-allocation field for every IPO. Treat any broker prediction as optional and cite it when present; otherwise use third-party calculators or estimate from disclosed demand assumptions and label it clearly.

## Known Limitations

- Some source systems disagree on stock code formatting. Normalize codes to five digits plus `.HK` where possible.
- Some pages update after listing and may hide old subscription details; use dated news articles or prospectus files to reconstruct past windows.
- Broker pages may include financing deadlines that differ from public offer close times. Distinguish broker financing cutoff from the official retail application close date.
- Broker predicted allocation statistics are model estimates, not official allotment results. Label them clearly.
