import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "finance-macro/basic-quality-rating/scripts"
    ),
)
from bank_financial import stock_fingerprint
from f10_financial import LIMITATION, REPORTS, normalize, score_f10
from rating_math import finalize


def sample(sector="银行"):
    stock = {"code": "600036", "name": "测试", "sw_level1": sector}
    rows = []
    for y in range(2022, 2026):
        for q, day in enumerate(("03-31", "06-30", "09-30", "12-31"), 1):
            rows.append(
                {
                    "SECUCODE": "600036.SH",
                    "SECURITY_NAME_ABBR": "测试",
                    "REPORT_DATE": f"{y}-{day}",
                    "NOTICE_DATE": f"{y + 1}-01-20"
                    if q == 4
                    else f"{y}-{int(day[:2]) + 1:02d}-20",
                    "ROEJQ": 16,
                    "KCFJCXSYJLR": q * 100 * (y - 2020),
                    "KCFJCXSYJLRTZ": 20,
                    "TOTAL_ASSETS": 1000,
                    "TOTAL_LIABILITIES": 900,
                }
            )
    packet = {
        "schema_version": 1,
        "source": "eastmoney_f10",
        "stock_sha256": stock_fingerprint(stock),
        "as_of": "2026-10-28",
        "report_date": "2025-12-31",
        "datasets": {},
    }
    for kind in REPORTS:
        body = json.dumps({"success": True, "result": {"data": rows, "pages": 1}})
        packet["datasets"][kind] = {
            "body": body,
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
        }
    return stock, packet


class F10Tests(unittest.TestCase):
    def test_financial_sector_skips_industrial_leverage(self):
        for sector in ("银行", "非银金融"):
            stock, packet = sample(sector)
            result = score_f10(stock, packet)
            self.assertEqual(result["score"], 5)
            self.assertEqual(result["limitations"], [LIMITATION])

    def test_ordinary_uses_existing_caps(self):
        stock, packet = sample("机械设备")
        self.assertEqual(score_f10(stock, packet)["score"], 2)

    def test_single_quarter_is_difference_not_cumulative(self):
        stock, packet = sample()
        data, _, _ = normalize(stock, packet)
        self.assertAlmostEqual(data["latest_quarter_yoy_pct"], 25)
        self.assertEqual(data["roe_avg_3y"], 16)

    def test_missing_target_does_not_fall_back(self):
        stock, packet = sample()
        packet["report_date"] = "2026-09-30"
        self.assertIsNone(score_f10(stock, packet)["score"])

    def test_no_rows_is_ungraded(self):
        stock, packet = sample()
        packet["report_date"] = None
        for kind in REPORTS:
            packet["datasets"][kind] = {"body": None}
        self.assertIsNone(score_f10(stock, packet)["score"])

    def test_duplicates_are_not_silently_selected(self):
        stock, packet = sample()
        d = json.loads(packet["datasets"]["main"]["body"])
        d["result"]["data"].append(d["result"]["data"][-1])
        body = json.dumps(d)
        packet["datasets"]["main"] = {
            "body": body,
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
        }
        self.assertIsNone(score_f10(stock, packet)["score"])

    def test_hash_and_identity_rejected(self):
        stock, packet = sample()
        with self.assertRaises(ValueError):
            score_f10(dict(stock, name="不同名称"), packet)
        packet["datasets"]["main"]["sha256"] = "x"
        with self.assertRaises(ValueError):
            score_f10(stock, packet)

    def test_finalizer_recomputes_and_requires_limits(self):
        stock, packet = sample()
        draft = {
            "code": stock["code"],
            "name": stock["name"],
            "dimensions": {
                "business": 3,
                "moat": 3,
                "industry": 3,
                "management": 3,
                "financial": 5,
            },
            "summary": "基础评级",
            "risks": [],
            "watch_points": [LIMITATION],
            "report_md": LIMITATION,
        }
        self.assertEqual(
            finalize(draft, stock, check_financial=True, f10_data=packet)["dimensions"][
                "financial"
            ],
            5,
        )
        draft["dimensions"]["financial"] = 4
        with self.assertRaises(ValueError):
            finalize(draft, stock, check_financial=True, f10_data=packet)
        draft["dimensions"]["financial"] = 5
        draft["watch_points"] = []
        with self.assertRaises(ValueError):
            finalize(draft, stock, check_financial=True, f10_data=packet)


if __name__ == "__main__":
    unittest.main()
