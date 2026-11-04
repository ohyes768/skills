# Design

Self-contained Python CLI using urllib for bounded PDF download and pdfplumber for page text and table extraction. Preserve source.pdf, pages.json, pages.md, candidates.json and candidates.md. Section recognition is a heuristic proposal, never a completeness guarantee: identify management discussion after TOC, split numbered headings, map aliases to requested topics, and retain full outlook for agent-level paragraph selection. Agent verifies boundaries, tables and mixed risk/strategy paragraphs before assembling industry-learning.md. PDF physical page numbers are one-based and explicit. Textless pages require OCR outside the helper; errors and missing sections remain visible.

No model API or credentials in scripts. Summarization and semantic selection are the invoking agent's responsibility. Existing financial analysis skill contains no reusable downloader/extractor found by search. Keep runtime dependencies local via inline uv metadata.

Optimization: two passes separate text/heading detection from table extraction. Explicit --table-pages supports missed-heading recovery. A dependency-free assembler consumes reviewed Markdown parts, preserves source content and enforces the summary length contract. Semantic selection and table reconstruction remain agent review responsibilities.
