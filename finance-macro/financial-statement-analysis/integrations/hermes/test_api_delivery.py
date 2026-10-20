"""Run in the Hermes test environment after installing the opt-in bridge."""

import asyncio
import shutil
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer
from tests.gateway.test_api_server_runs import _create_runs_app, _make_adapter


class Delivery:
    instructions = "Use a unique financial directory and finish receipt"
    terminal = False
    accept = True

    def __init__(self, *args):
        self.terminal = False

    def configure_agent(self, agent):
        pass

    async def check_once(self, agent, publish):
        if self.accept and not self.terminal:
            self.terminal = True
            publish(output="# Accepted report from disk")
            agent.interrupt("receipt delivered")

    async def watch(self, agent, publish):
        await self.check_once(agent, publish)


async def status_until(cli, run_id, expected):
    for _ in range(500):
        response = await cli.get(f"/v1/runs/{run_id}")
        result = await response.json()
        if result["status"] == expected:
            return result
        await asyncio.sleep(.01)
    pytest.fail(f"run did not reach {expected}: {result}")


@pytest.mark.asyncio
async def test_accepted_artifact_completes_while_worker_is_still_cleaning_up():
    adapter = _make_adapter()
    cleanup = threading.Event()
    agent = MagicMock()
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_total_tokens = 0

    def run(**kwargs):
        cleanup.wait(5)
        return {"failed": True, "error": "late cleanup failure"}

    agent.run_conversation.side_effect = run
    async with TestClient(TestServer(_create_runs_app(adapter))) as cli:
        with patch.object(adapter, "_create_agent", return_value=agent), patch(
            "gateway.financial_delivery.FinancialDelivery", Delivery
        ):
            try:
                response = await cli.post("/v1/runs", json={
                    "input": "analyze", "completion_mode": "financial_statement_analysis",
                    "completion_source_url": "https://example.com/report.pdf"})
                assert response.status == 202
                run_id = (await response.json())["run_id"]
                result = await status_until(cli, run_id, "completed")
                assert result["output"] == "# Accepted report from disk"
                assert run_id in adapter._active_run_tasks
                assert not cleanup.is_set()
                agent.interrupt.assert_called_once()
            finally:
                cleanup.set()
            for _ in range(100):
                if run_id not in adapter._active_run_tasks:
                    break
                await asyncio.sleep(.01)
            result = await status_until(cli, run_id, "completed")
            assert result["output"] == "# Accepted report from disk"


@pytest.mark.asyncio
async def test_financial_text_without_receipt_is_failed():
    adapter = _make_adapter()
    agent = MagicMock()
    agent.run_conversation.return_value = {"final_response": "unverified model summary"}
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_total_tokens = 0

    class NoReceipt(Delivery):
        accept = False

    async with TestClient(TestServer(_create_runs_app(adapter))) as cli:
        with patch.object(adapter, "_create_agent", return_value=agent), patch(
            "gateway.financial_delivery.FinancialDelivery", NoReceipt
        ):
            response = await cli.post("/v1/runs", json={
                "input": "analyze", "completion_mode": "financial_statement_analysis",
                "completion_source_url": "https://example.com/report.pdf"})
            run_id = (await response.json())["run_id"]
            result = await status_until(cli, run_id, "failed")
            assert "without an accepted completion receipt" in result["error"]
            assert not result.get("output")


def test_terminal_status_cannot_be_overwritten_by_late_events():
    adapter = _make_adapter()
    adapter._set_run_status("run_test", "completed", output="accepted")
    adapter._set_run_status("run_test", "running", last_event="tool.completed")
    adapter._set_run_status("run_test", "cancelled")
    assert adapter._run_statuses["run_test"]["status"] == "completed"
    assert adapter._run_statuses["run_test"]["output"] == "accepted"


@pytest.mark.asyncio
async def test_real_receipt_verifier_through_runs_api(tmp_path, monkeypatch):
    """Synthetic report, actual host subprocess verifier, real HTTP; no model or publisher."""
    from gateway.financial_delivery import FinancialDelivery
    from hermes_cli import config

    installed_skill = Path("/home/ohyes768/skills/finance-macro/financial-statement-analysis")
    # Use existing synthetic report fixtures, never a private company report.
    monkeypatch.syspath_prepend(str(installed_skill / "tests"))
    monkeypatch.syspath_prepend(str(installed_skill / "scripts"))
    import run_pipeline
    from test_render_report import prepare_render_run, revenue_inputs, write_json_file

    home = tmp_path / "home"
    skill = home / "skills" / "financial-statement-analysis"
    shutil.copytree(installed_skill / "scripts", skill / "scripts")
    python = skill / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    monkeypatch.setattr(config, "get_hermes_home", lambda: home)
    gate = threading.Event()
    created = []

    def factory(*args, **kwargs):
        instance = FinancialDelivery(*args, **kwargs)
        instance.run_dir.mkdir(parents=True)
        prepare_render_run(instance.run_dir)
        write_json_file(instance.run_dir / "report_inputs.json", revenue_inputs())
        write_json_file(instance.run_dir / "source.json",
                        {"requested_url": "https://example.com/report.pdf"})
        assert run_pipeline.cmd_report(instance.run_dir)[1] == 0
        assert run_pipeline.cmd_finish(instance.run_dir, semantic_reviewed=True)[1] == 0
        created.append(instance)
        return instance

    adapter, agent = _make_adapter(), MagicMock()
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_total_tokens = 0
    agent.run_conversation.side_effect = lambda **kwargs: (gate.wait(10) and {}) or {}
    async with TestClient(TestServer(_create_runs_app(adapter))) as cli:
        with patch.object(adapter, "_create_agent", return_value=agent), patch(
            "gateway.financial_delivery.FinancialDelivery", side_effect=factory
        ):
            try:
                response = await cli.post("/v1/runs", json={
                    "input": "synthetic test", "completion_mode": "financial_statement_analysis",
                    "completion_source_url": "https://example.com/report.pdf"})
                assert response.status == 202
                run_id = (await response.json())["run_id"]
                result = await status_until(cli, run_id, "completed")
                assert result["output"] == (created[0].run_dir / "analysis.md").read_text(
                    encoding="utf-8")
                assert run_id in adapter._active_run_tasks
            finally:
                gate.set()
            task = adapter._active_run_tasks.get(run_id)
            if task:
                await asyncio.wait_for(task, 2)
