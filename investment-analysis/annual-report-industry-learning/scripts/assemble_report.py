"""Assemble reviewed Markdown and enforce the summary length contract (no dependencies)."""
import argparse
import html
import json
from pathlib import Path
import re
import sys

BUDGETS = [("行业全貌", 150, 200), ("生意逻辑", 200, 300), ("竞争逻辑", 200, 250),
           ("行业变化", 250, 300), ("风险机制", 150, 200), ("学习结论", 100, 150)]


def visible_text(markdown):
    """Visible text for the skill's headings, paragraphs, lists and pipe tables."""
    text = re.sub(r'<!--.*?-->', '', markdown, flags=re.S)
    text = re.sub(r'!\[([^\]]*)\]\([^\n)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\([^\n)]*\)', r'\1', text)
    text = re.sub(r'^\s*\|?[ :\-|]+\|?\s*$', '', text, flags=re.M)
    text = re.sub(r'^\s*(?:#{1,6}\s+|>\s*|[-+*]\s+|\d+[.)]\s+)', '', text, flags=re.M)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', '', html.unescape(text.translate(str.maketrans('', '', '*_`|'))))


def summary_stats(summary):
    count = len(visible_text(summary))
    warnings, sections = [], {}
    if count < 1200 or count > 1600:
        warnings.append(f"Summary has {count} characters; target is 1200–1600")
    # The heading uses the stable topic name, while explanatory titles may vary.
    parts = re.split(r'^###\s+(.+?)\s*$', summary, flags=re.M)
    for topic, low, high in BUDGETS:
        matches = [(parts[i], parts[i+1]) for i in range(1, len(parts), 2) if topic in parts[i]]
        if len(matches) != 1:
            warnings.append(f"Expected one section for {topic}, found {len(matches)}")
            continue
        heading, body = matches[0]
        # Source index belongs to the total, not the learning-conclusion budget.
        body = re.split(r'^####\s+', body, maxsplit=1, flags=re.M)[0]
        length = len(visible_text(body))
        sections[topic] = length
        if not low <= length <= high:
            warnings.append(f"{topic}: {length} characters; soft budget {low}–{high}")
    return {"summary_characters": count, "section_characters": sections, "warnings": warnings}


def assemble(title, summary, source):
    if not visible_text(summary) or not visible_text(source):
        raise ValueError("Reviewed summary and source must both be nonempty")
    stats = summary_stats(summary)
    if stats["summary_characters"] > 1800:
        raise ValueError(f"Summary exceeds 1800 characters: {stats['summary_characters']}")
    if re.search(r'【PDF\s*第\s*\d+\s*页】', source):
        raise ValueError("Remove inline PDF page markers from reviewed source")
    # Inputs include their part headings; preserve reviewed content verbatim.
    return f"# {title}\n\n{summary.rstrip()}\n\n---\n\n{source.rstrip()}\n", stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--title', required=True)
    parser.add_argument('--summary', type=Path, required=True, help='Reviewed first-part Markdown, including ## part heading')
    parser.add_argument('--source', type=Path, required=True, help='Reviewed second-part Markdown, including ## part heading')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        inputs = {args.summary.resolve(), args.source.resolve()}
        if args.output.resolve() in inputs:
            raise ValueError("Output must not overwrite an input")
        document, stats = assemble(args.title, args.summary.read_text(encoding='utf-8'), args.source.read_text(encoding='utf-8'))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document, encoding='utf-8')
        print(json.dumps(stats, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(f"Assembly failed: {exc}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
