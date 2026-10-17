"""下载财报 PDF：重定向、超时、有限重试、哈希缓存与来源记录。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pymupdf
from artifacts import emit_status, write_json

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 45.0
DEFAULT_MAX_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1, 2)
CHUNK_SIZE = 64 * 1024
PARSER_VERSION = f"pymupdf/{getattr(pymupdf, '__version__', 'unknown')}"

_cli_client: httpx.Client | None = None
_cli_sleep: Callable[[float], None] | None = None


class FetchError(RuntimeError):
    """致命下载失败：退出 1。"""


class _TransientError(RuntimeError):
    """可重试的临时错误。"""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_pdf_file(path: Path) -> bool:
    with open(path, "rb") as f:
        if f.read(5) != b"%PDF-":
            return False
    try:
        with pymupdf.open(filename=str(path)) as doc:
            return doc.page_count >= 1
    except Exception:  # noqa: BLE001 - 任意解析库异常都视为不可打开
        return False


def _read_cached(run_dir: Path) -> dict | None:
    source_json = run_dir / "source.json"
    source_pdf = run_dir / "source.pdf"
    if not (source_json.exists() and source_pdf.exists()):
        return None
    try:
        record = json.loads(source_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not _validate_pdf_file(source_pdf):
        return None
    if record.get("sha256") != _file_sha256(source_pdf):
        return None
    return record


def _download_once(client: httpx.Client, url: str, tmp_path: Path, max_bytes: int) -> dict:
    try:
        with client.stream("GET", url) as response:
            if 500 <= response.status_code < 600:
                raise _TransientError(f"HTTP {response.status_code}")
            if response.status_code != 200:
                raise FetchError(f"HTTP {response.status_code} for {url}")
            declared = response.headers.get("content-length")
            if declared is not None and int(declared) > max_bytes:
                raise FetchError(f"content-length {declared} exceeds limit {max_bytes}")
            digest = hashlib.sha256()
            size = 0
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError(f"download exceeds limit {max_bytes} bytes")
                    digest.update(chunk)
                    f.write(chunk)
                if declared is not None and size != int(declared):
                    raise FetchError(f"incomplete download: {size} of {declared} bytes")
    except httpx.TransportError as exc:
        raise _TransientError(str(exc)) from exc
    return {
        "sha256": digest.hexdigest(),
        "size_bytes": size,
        "final_url": str(response.url),
        "etag": response.headers.get("etag"),
        "last_modified": response.headers.get("last-modified"),
    }


def fetch_pdf(
    url: str,
    output_dir: Path,
    *,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    refresh: bool = False,
) -> dict:
    """下载 PDF 到 output_dir/source.pdf 并写 source.json；返回含 reused 标记的记录。"""
    run_dir = Path(output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    if not refresh:
        cached = _read_cached(run_dir)
        if cached is not None:
            return {**cached, "reused": True}

    previous_sha256: str | None = None
    source_json = run_dir / "source.json"
    if refresh and source_json.exists():
        try:
            previous_sha256 = json.loads(source_json.read_text(encoding="utf-8")).get("sha256")
        except (OSError, ValueError):
            previous_sha256 = None

    owned_client = client is None
    if client is None:
        client = httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(connect_timeout, read=read_timeout),
        )

    tmp_path = run_dir / "source.pdf.tmp"
    try:
        info: dict | None = None
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                info = _download_once(client, url, tmp_path, max_bytes)
                last_error = None
                break
            except _TransientError as exc:
                last_error = exc
                tmp_path.unlink(missing_ok=True)
                if attempt < max_attempts:
                    sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
        if last_error is not None or info is None:
            raise FetchError(f"download failed after {max_attempts} attempts: {last_error}")

        if not _validate_pdf_file(tmp_path):
            raise FetchError(f"downloaded content is not a parsable PDF: {url}")

        os.replace(tmp_path, run_dir / "source.pdf")
    finally:
        tmp_path.unlink(missing_ok=True)
        if owned_client:
            client.close()

    record = {
        "schema_version": 1,
        "requested_url": url,
        "final_url": info["final_url"],
        "downloaded_at": datetime.now(UTC).isoformat(),
        "sha256": info["sha256"],
        "size_bytes": info["size_bytes"],
        "etag": info["etag"],
        "last_modified": info["last_modified"],
        "parser_version": PARSER_VERSION,
    }
    if refresh and previous_sha256 and previous_sha256 != info["sha256"]:
        record["previous_sha256"] = previous_sha256
    write_json(source_json, record)
    return {**record, "reused": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载财报 PDF 并记录来源")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--refresh", action="store_true", help="绕过缓存强制重新下载")
    parser.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT)
    parser.add_argument("--read-timeout", type=float, default=DEFAULT_READ_TIMEOUT)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    args = parser.parse_args(argv)

    try:
        result = fetch_pdf(
            args.url,
            Path(args.output_dir),
            client=_cli_client,
            sleep=_cli_sleep if _cli_sleep is not None else time.sleep,
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
            max_attempts=args.max_attempts,
            refresh=args.refresh,
        )
    except FetchError as exc:
        print(f"fetch_pdf failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    run_dir = Path(args.output_dir)
    emit_status(
        "ok" if not result["reused"] else "reused",
        {"source_pdf": str(run_dir / "source.pdf"), "source_json": str(source_path(run_dir))},
        [],
    )
    return 0


def source_path(run_dir: Path) -> Path:
    return run_dir / "source.json"


if __name__ == "__main__":
    raise SystemExit(main())
