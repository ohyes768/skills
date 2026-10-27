import sys
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
sys.path.insert(0, str(SCRIPTS))
from research_policy import classify_failure, fail_route, new_routes, select_route


class ResearchPolicyTests(unittest.TestCase):
    def test_classification_uses_error_not_page_instructions(self):
        for error, expected in (
            ({"http_status": 402}, "quota"),
            ({"http_status": 401}, "auth"),
            ({"message": "Insufficient credits; Payment Required"}, "quota"),
            ({"http_status": 429, "retry_after": 12}, "rate_limit"),
            ({"message": "Network is unreachable"}, "network"),
            ({"message": "connection timed out"}, "timeout"),
            ({"http_status": 403}, "blocked"),
            ({"http_status": 404}, "not_found"),
            ({"http_status": 503}, "network"),
            ({"message": "unknown provider error"}, "unknown"),
        ):
            self.assertEqual(classify_failure(error)["kind"], expected)
        with self.assertRaises(ValueError):
            classify_failure({"http_status": True})

    def test_quota_and_auth_disable_route_across_questions(self):
        for status in (401, 402):
            routes = new_routes(["primary", "backup"])
            fail_route(routes["primary"], {"http_status": status}, now=100)
            cause = routes["primary"]["reason"]
            fail_route(routes["primary"], {"http_status": 503}, now=101)
            self.assertEqual(routes["primary"]["reason"], cause)
            self.assertEqual(select_route(routes, [], now=100)["provider"], "backup")
            self.assertEqual(select_route(routes, [], now=1000)["provider"], "backup")
            routes["backup"]["disabled"] = True
            self.assertEqual(select_route(routes, [], now=1000)["action"], "stop")

    def test_transient_failure_switches_then_has_one_bounded_retry(self):
        routes = new_routes(["primary", "backup"])
        fail_route(routes["primary"], {"message": "timeout"}, now=100)
        attempts = [{"provider": "primary", "outcome": "failure"}]
        self.assertEqual(select_route(routes, attempts, now=100)["provider"], "backup")
        routes["backup"]["disabled"] = True
        waiting = select_route(routes, attempts, now=100)
        self.assertEqual(waiting["action"], "wait")
        retry_at = waiting["retry_at"]
        self.assertEqual(
            select_route(routes, attempts, now=retry_at)["provider"], "primary"
        )
        fail_route(routes["primary"], {"message": "timeout"}, now=retry_at)
        self.assertEqual(select_route(routes, attempts, now=retry_at)["action"], "stop")

    def test_empty_and_not_found_do_not_disable_provider_globally(self):
        routes = new_routes(["primary"])
        fail_route(routes["primary"], {"http_status": 404}, now=100)
        self.assertFalse(routes["primary"]["disabled"])
        for outcome in ("empty", "not_found"):
            self.assertEqual(
                select_route(
                    routes, [{"provider": "primary", "outcome": outcome}], now=100
                )["action"],
                "decide",
            )
        self.assertEqual(select_route(routes, [], now=100)["provider"], "primary")

    def test_retry_after_is_bounded_and_no_unbounded_routes(self):
        routes = new_routes(["primary"])
        fail_route(
            routes["primary"], {"http_status": 429, "retry_after": 10**400}, now=100
        )
        self.assertLessEqual(routes["primary"]["ready_at"], 400)
        for names in ([], ["p", "p"], ["p"] * 10, [""], "p"):
            with self.assertRaises(ValueError):
                new_routes(names)


if __name__ == "__main__":
    unittest.main()
