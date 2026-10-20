"""Run alongside stock-info-dingding tests; never submits a real analysis."""

from unittest.mock import Mock, patch

import hermes_client


def test_submission_enables_host_artifact_delivery():
    cfg = hermes_client.HermesConfig("http://test", "test", "test", 0, 60, "test", "test")
    response = Mock(status_code=202)
    response.json.return_value = {"run_id": "run_test"}
    with patch.object(hermes_client.requests, "post", return_value=response) as post:
        hermes_client.submit_report(cfg, "https://example.com/report.pdf", "test")
    body = post.call_args.kwargs["json"]
    assert body["completion_mode"] == "financial_statement_analysis"
    assert body["completion_source_url"] == "https://example.com/report.pdf"
    assert "finish --semantic-reviewed" in body["input"]
