# Markdown output contract

Deliver one file: `industry-learning.md`. First comes an explicitly labeled AI industry-textbook summary, then the reviewed selected source text. Separate source/summary files may be internal intermediates, never the required final deliverables. Keep the preserved PDF as supporting evidence.

## Second part — selected source text

Use Chinese for user-facing output. Include report title, company, reporting period, supplied URL/local path, PDF SHA-256 from candidates.json, extraction scope and review status. PDF page references mean one-based physical file pages; printed page numbers may be added separately.

Organize the source into the four requested topics. Preserve original subsection titles and ordering, paragraphs, numbers, units, source attributions, footnotes and selected tables. Do not insert page-transition markers such as `【PDF 第 N 页】` into the source body. Consolidate page ranges in the opening metadata or section headings so the source reads continuously. Remove only verified page headers/footers and repair obvious line wraps; do not paraphrase, translate, compress, silently drop tables, or reconstruct unreadable numbers.

For future outlook, state that the text is selected industry trend/risk paragraphs rather than the full outlook. Mark omitted spans between selected paragraphs with `〔省略：公司经营计划等非本次范围内容〕` or an accurate description. Record separately sourced risk headings and their pages. Preserve context without duplicating overlapping source text.

For each requested topic distinguish: verified extracted / genuinely not disclosed after review / heading not found / unreadable or incomplete. Include exact affected pages and any OCR uncertainty. Only call selected text complete when its boundaries and selected pages/tables have been checked.

## First part — AI industry-textbook summary

Identify the company and reporting period; link or refer to the source portion within the same document. Explain this is one company's report perspective, not an independently researched industry report.

Organize the narrative around six connected questions, not the report's original subsection order:

1. Industry overview: what need is met, how the value chain is organized, and who participates.
2. Business logic: what is sold, how value is delivered, what customers care about, and what drives economics. Do not infer undisclosed revenue models or margins as facts.
3. Competition logic: explain why capabilities matter; use company claims as examples rather than independently verified industry truths.
4. Industry change: connect scale and growth to policy, technology and competition. Embed only the data needed to support the explanation, preserving units, periods and cited sources. Keep forecasts distinct from observations.
5. Risk mechanisms: explain trigger → affected activity → business consequence, distinguishing report statements from AI deductions.
6. Learning conclusions: three durable takeaways, followed by one or two useful unanswered research questions.

### Length budget

The first part should normally contain 1,200–1,600 Chinese characters, with a hard maximum of 1,800. Count all visible non-whitespace text in this part, including headings, introduction, table cells and the source index; exclude Markdown formatting syntax and link destinations. The second part (source text) is not subject to this limit and must not be shortened to meet it.

Section budgets are soft targets:

| Section | Chinese characters | Priority |
|---|---:|---|
| Industry overview | 150–200 | Need addressed and value-chain roles |
| Business logic | 200–300 | What is sold, purchase drivers and economic drivers |
| Competition logic | 200–250 | Two or three decisive competitive factors; company as example |
| Industry change | 250–300 | Two or three major changes supported by a few key figures |
| Risk mechanisms | 150–200 | Three principal risks and their transmission paths |
| Learning conclusions | 100–150 | Three takeaways and one or two open questions |

Keep the introduction within 60 characters and use one compact source-index table. Use only three to five key quantitative indicators across the narrative; retain the units, period, necessary comparisons and attribution. Do not append a separate data-card section. Explain only terms needed to follow the argument, at first use.

Avoid repeating an idea across sections: competition explains what enables a company to win; industry change explains how conditions are changing; risk explains how adverse changes affect the business. If source evidence is thin, write less rather than padding or inventing facts. Before delivery, check the first-part length and shorten repetitions and secondary examples to stay under 1,800 characters; do not remove essential evidence qualifications to save space.

Explain essential terms at first use. Do not append disconnected policy lists, exhaustive data dumps or standalone glossaries by default. Mark unsupported dimensions as undisclosed in the selected source; do not fill them from memory. This is a reusable teaching framework, not a wind-industry-specific template.

Maintain a compact source index at the end of the summary mapping its substantive topics to physical PDF page ranges; do not interrupt the teaching narrative with page markers. Preserve forecasts as forecasts and company claims as claims. Do not convert a company's revenue into industry market size, or treat a reporting-period statistic as current data. Clearly label deductions and cite supporting pages. No investment recommendation or rating is needed.

Use `scripts/assemble_report.py` after semantic review to assemble the two reviewed Markdown parts. Its JSON output includes total visible summary characters, six section body counts and budget warnings. It counts the supported headings/paragraphs/lists/pipe-table Markdown, omitting formatting, comments and inline link destinations. Avoid reference-style links or raw HTML in the summary to keep counts unambiguous. A total above 1,800 is a hard error that leaves any existing output unchanged; section budgets remain warnings. The assembler preserves source content rather than attempting automatic paraphrase or table repair.

Before delivery compare selected source paragraphs against page text/visuals, verify numerical values and units, and check that every summary claim can be traced to the source portion. A missing dimension does not justify external browsing by default.
