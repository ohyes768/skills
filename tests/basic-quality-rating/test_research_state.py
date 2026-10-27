import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
sys.path.insert(0, str(SCRIPTS))
from research_state import REQUIRED_TOPICS, ResearchRun, check_research


def facts(dimension):
    return [
        {
            "topic": topic,
            "statement": f"已核实 {topic} 的测试事实",
            "url": "https://example.test/annual.pdf",
            "locator": "PDF p12",
            "period": "2025年度",
        }
        for topic in REQUIRED_TOPICS[dimension]
    ]


class ResearchStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "research.json"
        self.run = ResearchRun(self.path)
        self.stock = {"code": "000001", "name": "虚构测试公司", "roe_year": 2025}
        self.run.init(self.stock, ["primary", "backup"])

    def start(self, dimension="business", request_id="round-1", now=100):
        return self.run.start(
            dimension,
            "定价方式是否支持本维分档",
            "可能改变业务模式 3/4 分",
            request_id,
            now=now,
        )

    def test_init_and_request_replay_do_not_reset_budget(self):
        first = self.start()
        again = ResearchRun(self.path).start(
            "business",
            "定价方式是否支持本维分档",
            "可能改变业务模式 3/4 分",
            "round-1",
            now=100,
        )
        self.assertEqual(first["attempt"], again["attempt"])
        self.assertEqual(self.run.status()["dimensions"]["business"]["rounds_used"], 1)
        self.run.init(self.stock, ["primary", "backup"])
        self.assertEqual(self.run.status()["dimensions"]["business"]["rounds_used"], 1)
        with self.assertRaises(ValueError):
            self.run.init(dict(self.stock, code="000002"), ["primary", "backup"])
        with self.assertRaises(ValueError):
            self.run.init(self.stock, ["new-route"])
        with self.assertRaises(ValueError):
            self.run.start("business", "换词试图复用同一请求ID", "影响3/4分", "round-1")

    def test_failure_fallback_and_duplicate_result_are_bounded(self):
        self.start()
        result = self.run.result(
            "business", "round-1", 1, "failure", error={"http_status": 402}, now=100
        )
        self.assertEqual(result["provider"], "backup")
        self.assertEqual(result["attempt"], 2)
        self.run.result(
            "business", "round-1", 1, "failure", error={"http_status": 402}, now=100
        )
        with self.assertRaises(ValueError):
            self.run.result("business", "round-1", 1, "success", now=100)
        with self.assertRaises(ValueError):
            self.run.close(
                "business", "complete", "不能在备用调用待返回时结案", facts("business")
            )
        self.run.result(
            "business", "round-1", 2, "success", evidence=facts("business"), now=100
        )
        self.run.close("business", "complete", "所需证据已覆盖")
        self.assertEqual(self.run.status("business")["status"], "complete")
        next_dim = self.start("industry", "industry-1")
        self.assertEqual(next_dim["provider"], "backup")
        self.assertEqual(self.run.status()["providers"]["primary"]["reason"], "quota")

    def test_initial_plus_two_followups_exhaust_without_fabricating_facts(self):
        for n in range(1, 4):
            request = f"q-{n}"
            self.start(request_id=request)
            self.run.result("business", request, 1, "empty", now=100)
            end = self.run.result("business", request, 2, "empty", now=100)
            self.assertEqual(end["action"], "decide")
        with self.assertRaises(ValueError):
            self.start(request_id="q-4")
        self.assertEqual(self.run.status("business")["evidence"], [])
        self.run.close("business", "gap", "初查及两轮补查后仍缺关键事实")
        self.assertEqual(self.run.status("business")["status"], "gap")

    def test_last_success_can_complete_after_budget_is_spent(self):
        for n in range(1, 4):
            request = f"q-{n}"
            self.start(request_id=request)
            self.run.result(
                "business",
                request,
                1,
                "success",
                evidence=facts("business") if n == 3 else [],
                now=100,
            )
        self.run.close("business", "complete", "第三轮已获得最后缺口")
        self.assertEqual(self.run.status("business")["rounds_used"], 3)

    def test_complete_requires_topics_and_real_reference_shape(self):
        with self.assertRaises(ValueError):
            self.run.close("moat", "complete", "仅一句笼统结论不够")
        bad = facts("moat")
        bad[0]["url"] = "not-a-url"
        with self.assertRaises(ValueError):
            self.run.close("moat", "complete", "错误来源", bad)
        self.run.close("moat", "complete", "已有缓存证据覆盖问题", facts("moat"))
        with self.assertRaises(ValueError):
            self.start("moat", "extra-search")
        self.assertEqual(self.run.status("moat")["rounds_used"], 0)

    def test_reopen_requires_concrete_conflict_and_only_once(self):
        self.run.close("business", "complete", "已有事实", facts("business"))
        with self.assertRaises(ValueError):
            self.run.reopen("business", "", "再确认一下")
        self.run.reopen(
            "business", "新公告与原主营构成矛盾", "可能改变主导业务和2/3分裁决"
        )
        self.start(request_id="conflict-1")
        self.run.result("business", "conflict-1", 1, "success", now=100)
        self.run.close("business", "complete", "冲突已解释，原事实仍成立")
        with self.assertRaises(ValueError):
            self.run.reopen("business", "又想换关键词", "仍是同一个分档疑问")

    def test_all_routes_unavailable_stops_with_gap_and_preserves_facts(self):
        self.start()
        self.run.result(
            "business", "round-1", 1, "failure", error={"http_status": 402}, now=100
        )
        result = self.run.result(
            "business", "round-1", 2, "failure", error={"http_status": 401}, now=100
        )
        self.assertEqual(result["action"], "stop")
        self.assertEqual(self.run.status("business")["status"], "gap")
        self.assertTrue(self.run.status("business")["missing_topics"])
        self.assertEqual(self.start("industry", "i-1")["action"], "stop")

    def test_retry_wait_does_not_consume_extra_round_and_cannot_add_new_request(self):
        other = ResearchRun(Path(self.temp.name) / "one-route.json")
        other.init(self.stock, ["primary"])
        other.start("industry", "需求驱动", "影响行业分档", "i-1", now=100)
        wait = other.result(
            "industry", "i-1", 1, "failure", error={"kind": "timeout"}, now=100
        )
        self.assertEqual(wait["action"], "wait")
        with self.assertRaises(ValueError):
            other.start("industry", "换个关键词", "不应开启并行轮次", "i-2", now=100)
        ready = other.start(
            "industry", "需求驱动", "影响行业分档", "i-1", now=wait["retry_at"]
        )
        self.assertEqual(ready["attempt"], 2)
        end = other.result(
            "industry",
            "i-1",
            2,
            "failure",
            error={"kind": "timeout"},
            now=wait["retry_at"],
        )
        self.assertEqual(end["action"], "stop")
        self.assertEqual(other.status("industry")["rounds_used"], 1)

    def test_corrupt_state_lock_and_wrong_receipt_fail_without_reset(self):
        self.start()
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.run.result("business", "round-1", 99, "success")
        self.assertEqual(before, self.path.read_bytes())
        lock = self.path.with_name(self.path.name + ".lock")
        lock.write_text("another writer", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.start("industry", "i-1")
        lock.unlink()
        self.path.write_text("{bad", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run.init(self.stock, ["primary", "backup"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{bad")

    def test_submission_requires_terminal_state_identity_and_gap_nulls(self):
        draft = {
            "code": self.stock["code"],
            "name": self.stock["name"],
            "dimensions": {key: 4 for key in (*REQUIRED_TOPICS, "financial")},
        }
        with self.assertRaises(ValueError):
            check_research(self.path, draft, self.stock)
        for dimension in REQUIRED_TOPICS:
            self.run.close(dimension, "gap", "未获得评分所需事实")
        with self.assertRaises(ValueError):
            check_research(self.path, draft, self.stock)
        for dimension in REQUIRED_TOPICS:
            draft["dimensions"][dimension] = None
        check_research(self.path, draft, self.stock)
        with self.assertRaises(ValueError):
            check_research(self.path, dict(draft, code="000002"), self.stock)
        with self.assertRaises(ValueError):
            check_research(self.path, draft, dict(self.stock, roe_year=2024))

    def test_cli_returns_compact_json_and_failures_have_no_fake_result(self):
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "research_state.py"),
                "status",
                "--state",
                str(self.path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("dimensions", json.loads(run.stdout))
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "research_state.py"),
                "start",
                "--state",
                str(self.path),
                "--dimension",
                "business",
                "--question",
                "",
                "--impact",
                "",
                "--request-id",
                "x",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, "")

    def test_pending_replay_respects_new_global_provider_block(self):
        self.start("business", "business-1")
        self.start("moat", "moat-1")
        self.run.result(
            "business", "business-1", 1, "failure", error={"http_status": 402}, now=100
        )
        replay = self.start("moat", "moat-1")
        self.assertEqual(replay["provider"], "backup")
        self.assertEqual(replay["attempt"], 2)

    def test_multiple_outstanding_failures_keep_bounded_counter(self):
        for dimension in ("business", "moat", "industry"):
            self.start(dimension, dimension + "-1")
        for dimension in ("business", "moat", "industry"):
            result = self.run.result(
                dimension,
                dimension + "-1",
                1,
                "failure",
                error={"http_status": 402},
                now=100,
            )
            self.assertEqual(result["provider"], "backup")
        self.assertLessEqual(self.run.status()["providers"]["primary"]["failures"], 2)

    def test_persisted_evidence_is_validated_before_terminal_acceptance(self):
        state = json.loads(self.path.read_text(encoding="utf-8"))
        for key, dim in state["dimensions"].items():
            dim["status"], dim["reason"] = "complete", "corrupted data"
            dim["evidence"] = [{"topic": topic} for topic in REQUIRED_TOPICS[key]]
        self.path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run.status()


if __name__ == "__main__":
    unittest.main()
