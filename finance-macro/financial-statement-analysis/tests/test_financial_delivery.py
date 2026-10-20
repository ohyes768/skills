"""Host delivery must finish before the agent's final model request/cleanup returns."""

import asyncio
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_delivery import rendered


def delivery(tmp_path):
    from financial_delivery import FinancialDelivery

    skill_root = tmp_path / "skill"
    shutil.copytree(Path(__file__).parents[1] / "scripts", skill_root / "scripts")
    instance = FinancialDelivery(skill_root, "run_test", "https://example.com/report.pdf",
                                 python_executable=Path(sys.executable))
    instance.run_dir.mkdir(parents=True)
    return instance


def test_host_accepts_receipt_and_interrupts_without_waiting_for_agent(tmp_path):
    import run_pipeline

    instance = delivery(tmp_path)
    rendered(instance.run_dir)
    assert run_pipeline.cmd_finish(instance.run_dir, semantic_reviewed=True)[1] == 0
    agent, publish = Mock(), Mock()
    asyncio.run(instance.check_once(agent, publish))
    assert publish.call_args.kwargs["output"] == (
        instance.run_dir / "analysis.md").read_text(encoding="utf-8")
    assert instance.terminal
    agent.interrupt.assert_called_once()


def test_host_rejects_corrupt_receipt_instead_of_delivering(tmp_path):
    instance = delivery(tmp_path)
    (instance.run_dir / "completion.json").write_text("{}", encoding="utf-8")
    publish = Mock()
    asyncio.run(instance.check_once(Mock(), publish))
    assert "error" in publish.call_args.kwargs
    assert "output" not in publish.call_args.kwargs


def test_missing_receipt_is_not_completion(tmp_path):
    instance = delivery(tmp_path)
    publish = Mock()
    asyncio.run(instance.check_once(Mock(), publish))
    publish.assert_not_called()
    assert not instance.terminal


def test_financial_budget_exhaustion_makes_no_extra_model_call(tmp_path):
    instance = delivery(tmp_path)
    agent = Mock()
    instance.configure_agent(agent)
    assert "budget" in agent._handle_max_iterations([], 90).lower()
    assert not agent.mock_calls


def test_unknown_run_path_is_rejected(tmp_path):
    from financial_delivery import FinancialDelivery

    with pytest.raises(ValueError):
        FinancialDelivery(tmp_path, "../old", "https://example.com/report.pdf")
