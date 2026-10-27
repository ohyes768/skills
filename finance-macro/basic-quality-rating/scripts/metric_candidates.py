"""Shared, bounded raw metric candidates from an integrity-checked PDF cache."""

from __future__ import annotations

import re
from pathlib import Path

from pdf_evidence import DEFAULT_MAX_CHARS, _load_cache, _packet

_NUMBER = re.compile(r"(?<![\d.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*[%％]?")


def find_metric_candidates(
    document_dir: Path | str,
    labels: dict[str, tuple[str, ...]],
    *,
    selection_id: str,
    confirmation: str,
    search_scope: str,
    max_chars=DEFAULT_MAX_CHARS,
    cursor=None,
) -> dict:
    """Find the first occurrence of each named metric per PDF page.

    Long aliases consume contained labels before shorter alternatives. Whitespace
    in a label is tolerated. No year, entity, unit or table column is selected.
    Cursor selection binds both the mode ID and labels, as well as cache hashes.
    """
    aliases = {label: metric for metric, options in labels.items() for label in options}
    pattern = re.compile(
        "|".join(
            r"\s*".join(map(re.escape, label)) for label in sorted(aliases, key=len, reverse=True)
        )
    )
    loaded = _load_cache(document_dir)
    entries = []
    for page in loaded[3]:
        text = "\n".join(block["text"] for block in page["blocks"])
        seen = set()
        for match in pattern.finditer(text):
            label = re.sub(r"\s+", "", match.group())
            metric = aliases[label]
            if metric in seen:
                continue
            seen.add(metric)
            start, end = max(0, match.start() - 100), min(len(text), match.end() + 260)
            entries.append(
                {
                    "metric": metric,
                    "label": label,
                    "page": page["pdf_page"],
                    "printed_page": page.get("printed_page"),
                    "page_text_start": start,
                    "label_start": match.start(),
                    "context_length": end - start,
                    "text": text[start:end],
                    "needs_confirmation": True,
                }
            )
    packet = _packet(loaded, entries, [selection_id, labels], max_chars=max_chars, cursor=cursor)
    for item in packet["items"]:
        # Only returned text participates; a truncated/hidden value isn't usable.
        numbers = list(_NUMBER.finditer(item["text"]))
        item["numeric_strings"] = [match.group().strip() for match in numbers[:16]]
        item["numeric_strings_truncated"] = len(numbers) > 16
        item["context_complete"] = (
            item["start_offset"] == 0 and item["end_offset"] == item["context_length"]
        )
    packet.update(candidate_count=len(entries), needs_confirmation=True, search_scope=search_scope)
    packet["warnings"].append(confirmation)
    if not entries:
        packet["warnings"].append("未找到候选标签不代表指标或风险不存在；查看原文或记录资料缺口。")
    return packet
