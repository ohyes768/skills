import hashlib
import json

import fetch_pdf
import httpx
import pymupdf
import pytest


def build_pdf_bytes(text: str = "annual report") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


class RequestCounter:
    def __init__(self, handler):
        self.count = 0
        self.handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.count += 1
        return self.handler(request)


def pdf_response(data: bytes) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "application/pdf"}, content=data)


def test_valid_pdf_downloaded_and_recorded(run_dir):
    data = build_pdf_bytes()
    client = make_client(lambda request: pdf_response(data))

    result = fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)

    stored = run_dir / "source.pdf"
    assert stored.read_bytes() == data
    source = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))
    assert source["requested_url"] == "https://example.com/report.pdf"
    assert source["final_url"] == "https://example.com/report.pdf"
    assert source["sha256"] == hashlib.sha256(data).hexdigest()
    assert source["size_bytes"] == len(data)
    assert source["parser_version"]
    assert result["sha256"] == source["sha256"]


def test_redirect_final_url_recorded(run_dir):
    data = build_pdf_bytes("redirected")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old.pdf":
            return httpx.Response(302, headers={"location": "https://cdn.example.com/new.pdf"})
        return pdf_response(data)

    client = make_client(handler)
    fetch_pdf.fetch_pdf("https://example.com/old.pdf", run_dir, client=client)
    source = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))
    assert source["final_url"] == "https://cdn.example.com/new.pdf"


def test_html_response_rejected(run_dir):
    client = make_client(
        lambda request: httpx.Response(200, text="<html><body>not a pdf</body></html>")
    )
    with pytest.raises(fetch_pdf.FetchError):
        fetch_pdf.fetch_pdf("https://example.com/page", run_dir, client=client)
    assert not (run_dir / "source.pdf").exists()
    assert not (run_dir / "source.json").exists()
    assert list(run_dir.glob("*.tmp")) == []


def test_oversize_rejected(run_dir):
    data = build_pdf_bytes() + b"padding" * 10
    client = make_client(lambda request: pdf_response(data))
    with pytest.raises(fetch_pdf.FetchError):
        fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client, max_bytes=32)
    assert not (run_dir / "source.pdf").exists()


def test_content_length_over_limit_rejected_before_download(run_dir):
    data = b"x" * 64
    client = make_client(
        lambda request: httpx.Response(
            200, headers={"content-length": str(300 * 1024 * 1024)}, content=b""
        )
    )
    with pytest.raises(fetch_pdf.FetchError):
        fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    assert not (run_dir / "source.pdf").exists()
    assert client is not None and len(data) > 0


def test_interrupted_download_leaves_no_cache_marker(run_dir):
    data = build_pdf_bytes("truncated")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf", "content-length": str(len(data) + 100)},
            content=data,
        )

    client = make_client(handler)
    with pytest.raises(fetch_pdf.FetchError):
        fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    assert not (run_dir / "source.json").exists()
    assert list(run_dir.glob("*.tmp")) == []


def test_transient_error_then_success(run_dir):
    data = build_pdf_bytes("retry ok")
    attempts = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] <= 2:
            return httpx.Response(503)
        return pdf_response(data)

    client = make_client(handler)
    fetch_pdf.fetch_pdf(
        "https://example.com/report.pdf", run_dir, client=client, sleep=sleeps.append
    )
    assert attempts["n"] == 3
    assert sleeps == [1, 2]
    assert (run_dir / "source.pdf").exists()


def test_persistent_failure_raises(run_dir):
    attempts = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503)

    client = make_client(handler)
    with pytest.raises(fetch_pdf.FetchError):
        fetch_pdf.fetch_pdf(
            "https://example.com/report.pdf", run_dir, client=client, sleep=sleeps.append
        )
    assert attempts["n"] == 3
    assert sleeps == [1, 2]
    assert not (run_dir / "source.json").exists()


def test_client_error_not_retried(run_dir):
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(404)

    client = make_client(handler)
    with pytest.raises(fetch_pdf.FetchError):
        fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    assert attempts["n"] == 1


def test_same_content_reused_without_request(run_dir):
    data = build_pdf_bytes("cached")
    counter = RequestCounter(lambda request: pdf_response(data))
    client = make_client(counter)

    fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    assert counter.count == 1

    result = fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    assert counter.count == 1
    assert result["reused"] is True


def test_refresh_redownloads_when_content_changes(run_dir):
    first = build_pdf_bytes("v1")
    second = build_pdf_bytes("v2 restated")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return pdf_response(first if calls["n"] == 1 else second)

    client = make_client(handler)

    fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    first_sha = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))["sha256"]

    result = fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client, refresh=True)
    source = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))
    assert calls["n"] == 2
    assert source["sha256"] != first_sha
    assert source["previous_sha256"] == first_sha
    assert result["reused"] is False


def test_corrupted_cache_marker_not_reused(run_dir):
    data = build_pdf_bytes("intact")
    counter = RequestCounter(lambda request: pdf_response(data))
    client = make_client(counter)

    fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    (run_dir / "source.pdf").write_bytes(b"%PDF-1.4 broken")
    source = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))

    result = fetch_pdf.fetch_pdf("https://example.com/report.pdf", run_dir, client=client)
    assert counter.count == 2
    assert source["sha256"] == result["sha256"]


def test_cli_reports_failure_without_network(run_dir, capsys, monkeypatch):
    client = make_client(lambda request: httpx.Response(404))
    monkeypatch.setattr(fetch_pdf, "_cli_client", client)
    monkeypatch.setattr(fetch_pdf, "_cli_sleep", lambda seconds: None)

    with pytest.raises(SystemExit) as exc_info:
        fetch_pdf.main(["--url", "https://example.com/missing.pdf", "--output-dir", str(run_dir)])
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert err.strip() != ""
    assert not (run_dir / "source.json").exists()


def test_cli_injection_point_for_tests(run_dir, monkeypatch):
    """CLI 允许通过模块属性注入 client/sleep，供离线测试使用。"""
    data = build_pdf_bytes("inject")
    client = make_client(lambda request: pdf_response(data))

    monkeypatch.setattr(fetch_pdf, "_cli_client", client)
    monkeypatch.setattr(fetch_pdf, "_cli_sleep", lambda seconds: None)

    code = fetch_pdf.main(["--url", "https://example.com/r.pdf", "--output-dir", str(run_dir)])
    assert code == 0
    assert (run_dir / "source.pdf").exists()
