# Annual report industry learning

## Goal
Build a reusable skill in finance-macro/annual-report-industry-learning taking an annual-report PDF URL and delivering selected source text and an industry learning summary in Markdown.

## Requirements
- Download and preserve the supplied PDF; also accept a local PDF for retry and testing.
- Extract complete industry situation, principal business, and core competitiveness sections.
- Select only industry trends and risks from future outlook; include separately located risk sections within management discussion.
- Locate by headings and meaning rather than fixed pages or subsection numbers. Prefer third-section management discussion; report alternative locations explicitly.
- Preserve source wording, tables and PDF page provenance. Clearly distinguish extraction candidates from verified final text.
- Agent delivers one industry-learning.md containing a 1,200–1,600-character textbook summary (hard maximum 1,800) followed by reviewed source text. Summaries use only supplied report evidence; absent facts are marked undisclosed.
- Scanned, unreadable or ambiguous documents must not produce false complete results; retain intermediates and explain OCR/manual recovery.

## Acceptance
- CLI downloads a valid PDF atomically, rejects HTML responses, and fails clearly on invalid input.
- Extraction provides page-tagged Markdown and structured section candidates with missing-section warnings.
- Tests cover section boundaries, TOC duplicates, absent headings and invalid downloads.
- Real annual report extraction is inspected; skill validation passes.

## Scope
A-share Chinese annual reports first. No external industry research, stock rating, full-report translation or bundled OCR engine.

## Authorization
User approved task creation and development, including download and extraction scripts.

## Approved optimization scope
- Locate text candidates before extracting tables; allow explicitly selected pages for fallback review.
- Recognize 可能面临的风险 and nested Chinese/numeric heading boundaries.
- Assemble reviewed summary and source Markdown using a reusable CLI, without rewriting source.
- Count visible summary characters automatically; reject totals over 1,800 and warn on section budgets.
