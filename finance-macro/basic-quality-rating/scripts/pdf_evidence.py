"""Cache PDF sources once and return bounded, page-cited text evidence packets.

Uses the sibling financial-statement-analysis download/index implementation.
Runtime setup: uv sync --project <basic-quality-rating directory>.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

INDEX_VERSION = 1
DEFAULT_MAX_CHARS = 6000
MAX_CHARS = 12000
MAX_SELECTED_PAGES = 100
DEFAULT_TOOLS = Path(__file__).resolve().parents[2] / "financial-statement-analysis/scripts"
_BOUND_FILES = ("source.pdf", "source.json", "document.json", "pages.jsonl")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


@lru_cache(maxsize=4)
def _load_tools(tools_dir: str):
    directory = Path(tools_dir)
    paths = [directory / f"{name}.py" for name in ("artifacts", "fetch_pdf", "inspect_pdf")]
    if not all(path.is_file() for path in paths):
        raise ValueError(
            "PDF dependency scripts unavailable; retain the sibling financial-statement-analysis "
            "directory or pass --tools-dir <its scripts directory>"
        )
    modules = []
    old_artifacts = sys.modules.get("artifacts")
    try:
        for path in paths:
            spec = importlib.util.spec_from_file_location(f"_quality_pdf_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
            if path.stem == "artifacts":
                sys.modules["artifacts"] = module
    except ModuleNotFoundError as exc:
        raise ValueError(
            "PDF dependencies missing; run uv sync --project <basic-quality-rating directory> "
            "during setup, then invoke this script with uv run --project <directory> python"
        ) from exc
    finally:
        if old_artifacts is None:
            sys.modules.pop("artifacts", None)
        else:
            sys.modules["artifacts"] = old_artifacts
    return modules[1], modules[2]


def _load_cache(document_dir: Path | str):
    directory = Path(document_dir)
    try:
        manifest = _json(directory / "evidence_index.json")
        if manifest.get("index_version") != INDEX_VERSION:
            raise ValueError("unsupported index version")
        for name in _BOUND_FILES:
            if _sha(directory / name) != manifest["hashes"][name]:
                raise ValueError(f"hash mismatch for {name}")
        source = _json(directory / "source.json")
        if source["sha256"] != manifest["hashes"]["source.pdf"]:
            raise ValueError("source hash mismatch")
        if source["requested_url"] != manifest["requested_url"]:
            raise ValueError("source URL mismatch")
        pages = [
            json.loads(line)
            for line in (directory / "pages.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if len(pages) != manifest["page_count"] or not pages:
            raise ValueError("page count mismatch")
        for number, page in enumerate(pages, 1):
            if page["pdf_page"] != number or not isinstance(page["blocks"], list):
                raise ValueError("invalid page index")
            if not all(isinstance(block.get("text"), str) for block in page["blocks"]):
                raise ValueError("invalid indexed text")
        return directory, manifest, source, pages
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(
            f"PDF cache unavailable or changed under {directory}: {exc}; "
            "run prepare --url <source URL> --cache-dir <cache root> --refresh"
        ) from exc


def _warnings(pages) -> list[str]:
    unavailable = [
        page["pdf_page"]
        for page in pages
        if not page["blocks"] or page.get("text_quality") in ("scanned", "poor_text")
    ]
    if not unavailable:
        return []
    return [
        (
            f"PDF pages {','.join(map(str, unavailable[:20]))}"
            f"{' …' if len(unavailable) > 20 else ''} have missing/poor extractable text "
            "(no OCR performed); absence of text is not absence of evidence"
        )
    ]


def _summary(directory, manifest, source, pages, *, reused):
    metadata = _json(directory / "document.json")
    return {
        "status": "ready",
        "document_dir": str(directory.resolve()),
        "reused": reused,
        "page_count": len(pages),
        "source": {key: source.get(key) for key in ("requested_url", "final_url", "sha256")},
        "document": {
            key: metadata.get(key)
            for key in ("company_name", "stock_code", "report_type", "period")
        },
        "warnings": _warnings(pages),
    }


def prepare_pdf(
    url: str,
    cache_dir: Path | str,
    *,
    client=None,
    refresh=False,
    tools_dir: Path | str | None = None,
) -> dict:
    if (
        not isinstance(url, str)
        or urlsplit(url).scheme not in ("http", "https")
        or not urlsplit(url).netloc
    ):
        raise ValueError("PDF URL must be an absolute http(s) URL")
    root = Path(cache_dir).resolve()
    directory = root / hashlib.sha256(url.encode()).hexdigest()[:24]
    if directory.exists() and not refresh:
        loaded = _load_cache(directory)
        if loaded[2]["requested_url"] != url:
            raise ValueError("cached URL differs from requested URL; choose another cache root")
        return _summary(*loaded, reused=True)
    fetch, inspect = _load_tools(str(Path(tools_dir or DEFAULT_TOOLS).resolve()))
    root.mkdir(parents=True, exist_ok=True)
    # Finish the replacement in staging first. A failed refresh leaves the last
    # usable PDF/index untouched. The manifest is published last.
    with tempfile.TemporaryDirectory(prefix=".pdf-prepare-", dir=root) as work:
        stage = Path(work)
        fetch.fetch_pdf(url, stage, client=client)
        indexed = inspect.inspect_pdf(stage)
        manifest = {
            "index_version": INDEX_VERSION,
            "requested_url": url,
            "page_count": len(indexed["pages"]),
            "parser_version": fetch.PARSER_VERSION,
            "hashes": {name: _sha(stage / name) for name in _BOUND_FILES},
        }
        _write_json(stage / "evidence_index.json", manifest)
        _load_cache(stage)
        directory.mkdir(parents=True, exist_ok=True)
        for name in (*_BOUND_FILES, "sections.json", "evidence_index.json"):
            os.replace(stage / name, directory / name)
    return _summary(*_load_cache(directory), reused=False)


def _pages_spec(spec: str, page_count: int) -> list[int]:
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError("--pages must be a nonempty PDF page selection, e.g. 1,3-5")
    result = set()
    for part in spec.split(","):
        match = re.fullmatch(r"\s*(\d+)(?:-(\d+))?\s*", part)
        if not match:
            raise ValueError(f"invalid PDF page selection: {part!r}")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= page_count or last - first + 1 > MAX_SELECTED_PAGES:
            raise ValueError(
                f"PDF page range must be inside 1..{page_count}, at most {MAX_SELECTED_PAGES} pages"
            )
        result.update(range(first, last + 1))
        if len(result) > MAX_SELECTED_PAGES:
            raise ValueError(f"select at most {MAX_SELECTED_PAGES} PDF pages at once")
    return sorted(result)


def _packet(loaded, entries: list[dict], selection, *, max_chars, cursor):
    directory, manifest, source, pages = loaded
    if type(max_chars) is not int or not 64 <= max_chars <= MAX_CHARS:
        raise ValueError(f"max_chars must be an integer between 64 and {MAX_CHARS}")
    binding = hashlib.sha256(
        json.dumps(
            [manifest["hashes"], selection],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    index = offset = 0
    if cursor is not None:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            index, offset = token["index"], token["offset"]
            if token["binding"] != binding or type(index) is not int or type(offset) is not int:
                raise ValueError("cursor belongs to different evidence request")
            if not 0 <= index < len(entries) or not 0 <= offset < max(
                1, len(entries[index]["text"])
            ):
                raise ValueError("cursor position outside packet")
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
            raise ValueError(
                "invalid/stale cursor; reuse the same command, selection and source"
            ) from exc
    items = []
    remaining = max_chars
    while index < len(entries) and remaining and len(items) < MAX_SELECTED_PAGES:
        entry = entries[index]
        fragment = entry["text"][offset : offset + remaining]
        items.append(
            {
                **entry,
                "text": fragment,
                "start_offset": offset,
                "end_offset": offset + len(fragment),
            }
        )
        remaining -= len(fragment)
        offset += len(fragment)
        if offset >= len(entry["text"]):
            index += 1
            offset = 0
        else:
            break
    next_cursor = None
    if index < len(entries):
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {"binding": binding, "index": index, "offset": offset},
            ).encode()
        ).decode()
    return {
        "status": "ok",
        "document_dir": str(directory.resolve()),
        "source": {key: source.get(key) for key in ("requested_url", "final_url", "sha256")},
        "items": items,
        "next_cursor": next_cursor,
        "text_chars": max_chars - remaining,
        "warnings": _warnings(pages),
    }


def read_pdf(
    document_dir: Path | str, pages: str, *, max_chars=DEFAULT_MAX_CHARS, cursor=None
) -> dict:
    loaded = _load_cache(document_dir)
    selected = _pages_spec(pages, len(loaded[3]))
    entries = [
        {
            "page": number,
            "printed_page": loaded[3][number - 1].get("printed_page"),
            "text": "\n".join(block["text"] for block in loaded[3][number - 1]["blocks"]),
        }
        for number in selected
    ]
    return _packet(loaded, entries, ["read", selected], max_chars=max_chars, cursor=cursor)


def search_pdf(
    document_dir: Path | str, queries: list[str], *, max_chars=DEFAULT_MAX_CHARS, cursor=None
) -> dict:
    if (
        not isinstance(queries, list)
        or not 1 <= len(queries) <= 16
        or any(
            not isinstance(query, str) or not query.strip() or len(query) > 256 for query in queries
        )
    ):
        raise ValueError("provide 1..16 nonempty literal queries, each at most 256 characters")
    queries = list(dict.fromkeys(queries))
    loaded = _load_cache(document_dir)
    entries = []
    for page in loaded[3]:
        text = "\n".join(block["text"] for block in page["blocks"])
        for query in queries:
            found = text.find(query)
            if found >= 0:
                start, end = max(0, found - 180), min(len(text), found + len(query) + 180)
                entries.append(
                    {
                        "page": page["pdf_page"],
                        "printed_page": page.get("printed_page"),
                        "query": query,
                        "page_text_start": start,
                        "text": text[start:end],
                    }
                )
    packet = _packet(loaded, entries, ["search", queries], max_chars=max_chars, cursor=cursor)
    packet["match_count"] = len(entries)
    packet["search_scope"] = "First literal occurrence of each query on each indexed PDF page"
    return packet


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--url", required=True)
    prepare.add_argument("--cache-dir", required=True)
    prepare.add_argument("--refresh", action="store_true")
    prepare.add_argument(
        "--tools-dir", help="Existing financial-statement-analysis/scripts directory"
    )
    for command in ("search", "read"):
        child = commands.add_parser(command)
        child.add_argument("--document-dir", required=True)
        child.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
        child.add_argument("--cursor")
        if command == "search":
            child.add_argument("--query", action="append", required=True)
        else:
            child.add_argument("--pages", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_pdf(
                args.url, args.cache_dir, refresh=args.refresh, tools_dir=args.tools_dir
            )
        elif args.command == "search":
            result = search_pdf(
                args.document_dir, args.query, max_chars=args.max_chars, cursor=args.cursor
            )
        else:
            result = read_pdf(
                args.document_dir, args.pages, max_chars=args.max_chars, cursor=args.cursor
            )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except Exception as exc:  # noqa: BLE001 - CLI converts dependency/download/parser failures to stderr
        print(f"pdf_evidence: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
