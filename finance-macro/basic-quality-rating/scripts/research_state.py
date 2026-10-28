"""Persistent research receipts, source failover and per-dimension stop budgets.

Host tools perform the actual search. Reserve with start, then record each tool
outcome with result. This is a workflow gate, not a host/network interceptor.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from rating_math import _read, calculate
from research_policy import fail_route, new_routes, select_route

REQUIRED_TOPICS = {
    "business": ("main_business", "customers_repeat", "pricing_cycle"),
    "moat": ("advantages", "durability_trend", "counterevidence"),
    "industry": ("demand_driver", "substitution_risk"),
    "management": ("decisions", "allocation_alignment", "governance_succession"),
}
BANK_TOPICS = {"financial": ("profitability", "asset_quality", "capital", "liquidity")}
INSURANCE_TOPICS = ("profitability", "solvency", "insurance_business", "asset_liability")
ALL_TOPICS = {**REQUIRED_TOPICS, **BANK_TOPICS}
MAX_ROUNDS = 5  # Initial web research plus four follow-ups, shared by each dimension.
DELIVERY_RESERVE = 8


def _text(value, name, limit=1200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} 必须为非空文本，长度不超过 {limit}")
    return value


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _identity(stock):
    if not isinstance(stock, dict):
        raise TypeError("stock 必须为原始股票 JSON 对象")
    return {key: _text(stock.get(key), key, 100) for key in ("code", "name")}


def _check_shape(state):
    try:
        if type(state["version"]) is not int or state["version"] != 1:
            raise ValueError("不支持的取证状态版本")
        _identity(state["stock"])
        if len(state["input_sha256"]) != 64 or set(state["dimensions"]) not in (
            set(REQUIRED_TOPICS),
            set(ALL_TOPICS),
        ):
            raise ValueError("状态身份或维度结构损坏")
        execution = state.get("execution")
        if execution is not None:
            if (
                type(execution["research_limit"]) is not int
                or execution["research_limit"] < 1
                or execution["phase"] not in ("research", "report")
                or execution["delivery_reserve"] != DELIVERY_RESERVE
                or _calls_used(state) > execution["research_limit"]
            ):
                raise ValueError("执行预算或阶段损坏")
            if execution["phase"] == "report":
                snapshot = execution["snapshot"]
                if snapshot["derived"] != calculate(snapshot["dimensions"]):
                    raise ValueError("成稿评分快照损坏")
        new_routes(list(state["providers"]))
        for route in state["providers"].values():
            if (
                type(route["disabled"]) is not bool
                or type(route["failures"]) is not int
                or not 0 <= route["failures"] <= 2
            ):
                raise ValueError("渠道状态损坏")
        ids = []
        for key, dim in state["dimensions"].items():
            if key == "financial" and dim.get("mode", "bank") not in ("bank", "insurance"):
                raise ValueError("financial 取证模式损坏")
            if (
                dim["status"] not in ("open", "complete", "gap")
                or type(dim["reopen_used"]) is not bool
            ):
                raise ValueError("维度状态损坏")
            if not isinstance(dim["rounds"], list) or len(dim["rounds"]) > MAX_ROUNDS + int(
                dim["reopen_used"]
            ):
                raise ValueError("维度轮次超出预算")
            validated = {"evidence": [], "mode": dim.get("mode", "bank")}
            _evidence(key, validated, dim["evidence"])
            if dim["status"] == "complete" and _missing(key, dim):
                raise ValueError("complete 状态缺少必要主题")
            if dim["status"] != "open":
                _text(dim["reason"], "结案原因")
            for round_ in dim["rounds"]:
                ids.append(round_["request_id"])
                if len(round_["attempts"]) > len(state["providers"]) * 2:
                    raise ValueError("渠道调用次数超出本轮预算")
                if any(a["provider"] not in state["providers"] for a in round_["attempts"]):
                    raise ValueError("未知渠道调用记录")
        if len(set(ids)) != len(ids):
            raise ValueError("请求 ID 重复")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("取证状态损坏；不得用 init 重置预算") from exc


def _load(path):
    state = _read(path)
    if not isinstance(state, dict):
        raise TypeError("取证状态必须为对象")
    _check_shape(state)
    return state


def _dimension(state, dimension):
    if dimension not in state["dimensions"]:
        raise ValueError("未知 dimension；金融 financial 取证须先用 init 的对应行业模式启用")
    return state["dimensions"][dimension]


def _missing(dimension, dim):
    covered = {fact["topic"] for fact in dim["evidence"]}
    return [topic for topic in _topics(dimension, dim) if topic not in covered]


def _topics(dimension, dim):
    if dimension == "financial" and dim.get("mode", "bank") == "insurance":
        return INSURANCE_TOPICS
    return ALL_TOPICS[dimension]


def _evidence(dimension, dim, facts):
    if not isinstance(facts, list) or len(facts) > 12:
        raise ValueError("evidence 必须为至多 12 条事实的数组")
    for raw in facts:
        if not isinstance(raw, dict) or raw.get("topic") not in _topics(dimension, dim):
            raise ValueError("事实必须指向本维度的 required topic")
        fact = {
            key: _text(raw.get(key), key, limit)
            for key, limit in (
                ("topic", 64),
                ("statement", 800),
                ("url", 512),
                ("locator", 160),
                ("period", 80),
            )
        }
        if (
            urlsplit(fact["url"]).scheme not in ("https", "http")
            or not urlsplit(fact["url"]).netloc
        ):
            raise ValueError("事实 url 必须为可核对的 http(s) 来源；此检查不证明内容真实")
        if fact not in dim["evidence"]:
            dim["evidence"].append(fact)
    if len(dim["evidence"]) > 12:
        raise ValueError("本维度最多保留 12 条紧凑事实；复用已读取的网页原文，不重复抓取")


def _calls_used(state):
    return sum(len(r["attempts"]) for d in state["dimensions"].values() for r in d["rounds"])


def _summary(state, dimension=None):
    def brief(key, dim):
        return {
            "status": dim["status"],
            **({"mode": dim.get("mode", "bank")} if key == "financial" else {}),
            "rounds_used": len(dim["rounds"]),
            "rounds_remaining": 0
            if dim["status"] != "open"
            else max(
                0,
                (1 if dim["reopen_used"] else MAX_ROUNDS)
                - sum(r["conflict"] == dim["reopen_used"] for r in dim["rounds"]),
            ),
            "reopen_used": dim["reopen_used"],
            "missing_topics": _missing(key, dim),
            "reason": dim["reason"],
            "evidence_count": len(dim["evidence"]),
        }

    if dimension:
        dim = _dimension(state, dimension)
        return {**brief(dimension, dim), "evidence": dim["evidence"]}
    return {
        "stock": state["stock"],
        "terminal": all(dim["status"] != "open" for dim in state["dimensions"].values()),
        **(
            {
                "execution": {
                    "phase": state["execution"]["phase"],
                    "research_remaining": state["execution"]["research_limit"] - _calls_used(state),
                    "delivery_reserve": state["execution"]["delivery_reserve"],
                }
            }
            if "execution" in state
            else {}
        ),
        "providers": state["providers"],
        "dimensions": {key: brief(key, dim) for key, dim in state["dimensions"].items()},
    }


def _dispatch(state, dimension, round_, now):
    dim = _dimension(state, dimension)
    if dim["status"] != "open":
        return {"action": "done", "dimension": dimension, "status": dim["status"]}
    if round_["closed"]:
        return {
            "action": "decide",
            "dimension": dimension,
            "missing_topics": _missing(dimension, dim),
        }
    pending = [a for a in round_["attempts"] if a["outcome"] == "pending"]
    for record in pending:
        if state["providers"][record["provider"]]["disabled"]:
            record["outcome"] = "skipped"
    pending = [a for a in pending if a["outcome"] == "pending"]
    if pending:
        decision = {"action": "search", "provider": pending[-1]["provider"]}
        attempt = round_["attempts"].index(pending[-1]) + 1
    else:
        decision = select_route(state["providers"], round_["attempts"], now=now)
        attempt = len(round_["attempts"]) + 1
        if decision["action"] == "search":
            execution = state.get("execution")
            if execution and _calls_used(state) >= execution["research_limit"]:
                round_["closed"] = True
                return {
                    "action": "stop",
                    "dimension": dimension,
                    "reason": "全局取证预算已用尽；用已得事实 complete 或 gap，保留交付调用",
                }
            round_["attempts"].append(
                {
                    "provider": decision["provider"],
                    "outcome": "pending",
                    "result_sha256": None,
                    "reserved_at": now,
                }
            )
        elif decision["action"] in ("stop", "decide"):
            round_["closed"] = True
            if decision["action"] == "stop":
                dim["status"], dim["reason"] = "gap", decision["reason"]
    return {
        **decision,
        "dimension": dimension,
        "request_id": round_["request_id"],
        "attempt": attempt,
        "question": round_["question"],
        "impact": round_["impact"],
        "missing_topics": _missing(dimension, dim),
    }


class ResearchRun:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + ".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("取证状态正被其他进程写入；稍后重试，不重置状态或删除锁") from exc
        try:
            os.close(descriptor)
            yield
        finally:
            lock.unlink(missing_ok=True)

    def _save(self, state):
        _check_shape(state)
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _update(self, change):
        with self._lock():
            state = _load(self.path)
            before = _digest(state)
            response = change(state)
            if _digest(state) != before:
                self._save(state)
            return response

    def init(
        self,
        stock,
        providers,
        *,
        bank_research=False,
        insurance_research=False,
        research_limit=None,
    ):
        if research_limit is not None and (type(research_limit) is not int or research_limit < 1):
            raise ValueError("research_limit 必须为正整数")
        identity, input_sha = _identity(stock), _digest(stock)
        routes = new_routes(providers)
        if bank_research and insurance_research:
            raise ValueError("银行与保险取证模式不能同时启用")
        financial_mode = "insurance" if insurance_research else "bank" if bank_research else None
        if financial_mode:
            from financial_score import _sector

            if _sector(stock, []) != financial_mode:
                raise ValueError("金融取证模式与原始输入行业不一致")

        def empty_dimension(key):
            result = {
                "status": "open",
                "reopen_used": False,
                "rounds": [],
                "evidence": [],
                "reason": None,
            }
            if key == "financial":
                result["mode"] = financial_mode
            return result

        with self._lock():
            if self.path.exists():
                state = _load(self.path)
                if state["input_sha256"] != input_sha or list(state["providers"]) != providers:
                    raise ValueError("状态已绑定其他输入或渠道配置；不能重新 init 重置预算")
                if research_limit is not None and (
                    "execution" not in state
                    or state["execution"]["research_limit"] != research_limit
                ):
                    raise ValueError("不能补建或变更执行预算；旧账本按原模式续跑，不事后补账")
                if (
                    financial_mode
                    and "financial" in state["dimensions"]
                    and state["dimensions"]["financial"].get("mode", "bank") != financial_mode
                ):
                    raise ValueError("financial 已绑定其他行业模式，不能重置取证预算")
                if financial_mode and "financial" not in state["dimensions"]:
                    if state.get("execution", {}).get("phase") == "report":
                        raise ValueError("成稿后不能追加行业取证模式")
                    state["dimensions"]["financial"] = empty_dimension("financial")
                    self._save(state)
            else:
                state = {
                    "version": 1,
                    "stock": identity,
                    "input_sha256": input_sha,
                    "providers": routes,
                    "dimensions": {
                        key: empty_dimension(key)
                        for key in (ALL_TOPICS if financial_mode else REQUIRED_TOPICS)
                    },
                }
                if research_limit is not None:
                    state["execution"] = {
                        "research_limit": research_limit,
                        "delivery_reserve": DELIVERY_RESERVE,
                        "phase": "research",
                        "snapshot": None,
                        "created_at": time.time(),
                    }
                self._save(state)
            return _summary(state)

    def status(self, dimension=None):
        return _summary(_load(self.path), dimension)

    def start(self, dimension, question, impact, request_id, *, now=None):
        _text(question, "question")
        _text(impact, "impact")
        _text(request_id, "request_id", 100)
        now = time.time() if now is None else now

        def change(state):
            if state.get("execution", {}).get("phase") == "report":
                raise ValueError("已进入成稿阶段；具体分档冲突须先 reopen，不再取证")
            dim = _dimension(state, dimension)
            for key, other in state["dimensions"].items():
                for round_ in other["rounds"]:
                    if round_["request_id"] == request_id:
                        if (
                            key != dimension
                            or round_["question"] != question
                            or round_["impact"] != impact
                        ):
                            raise ValueError("同一 request_id 只能重放原维度、问题与影响说明")
                        return _dispatch(state, dimension, round_, now)
            if dim["status"] != "open":
                raise ValueError("该维度已结案；复用证据，具体冲突须先 reopen")
            if any(not r["closed"] for r in dim["rounds"]):
                raise ValueError("该维度仍有在途轮次；先记录结果或显式结案")
            same_phase = [r for r in dim["rounds"] if r["conflict"] == dim["reopen_used"]]
            if len(same_phase) >= (1 if dim["reopen_used"] else MAX_ROUNDS):
                raise ValueError("本维度取证预算已用尽；用已有证据 complete 或 gap，不再换关键词")
            round_ = {
                "request_id": request_id,
                "question": question,
                "impact": impact,
                "conflict": dim["reopen_used"],
                "attempts": [],
                "closed": False,
            }
            dim["rounds"].append(round_)
            return _dispatch(state, dimension, round_, now)

        return self._update(change)

    def result(
        self, dimension, request_id, attempt, outcome, *, error=None, evidence=None, now=None
    ):
        if (
            type(attempt) is not int
            or attempt < 1
            or outcome not in ("success", "empty", "failure")
        ):
            raise ValueError("需要有效 attempt 及 success/empty/failure outcome")
        evidence = [] if evidence is None else evidence
        if outcome != "success" and evidence:
            raise ValueError("失败或无命中不能携带已核实事实")
        if outcome != "failure" and error is not None:
            raise ValueError("只有 failure 可以提供 error")
        signature = _digest([outcome, error, evidence])
        now = time.time() if now is None else now

        def change(state):
            dim = _dimension(state, dimension)
            rounds = [r for r in dim["rounds"] if r["request_id"] == request_id]
            if not rounds or attempt > len(rounds[0]["attempts"]):
                raise ValueError("未找到 start 发放的调用回执")
            round_, record = rounds[0], rounds[0]["attempts"][attempt - 1]
            if record["result_sha256"] is not None:
                if record["result_sha256"] != signature:
                    raise ValueError("已登记回执不能改写为不同结果")
                return _dispatch(state, dimension, round_, now)
            if record["outcome"] != "pending" or round_["closed"]:
                raise ValueError("该回执已结案或取消，不接受迟到结果")
            record["recorded_at"] = now
            record["result_sha256"] = signature
            record["outcome"] = outcome
            if outcome == "failure":
                failure = fail_route(state["providers"][record["provider"]], error, now=now)
                record["failure_kind"] = failure["kind"]
                if failure["kind"] == "not_found":
                    record["outcome"] = "not_found"
            elif outcome == "success":
                _evidence(dimension, dim, evidence)
                state["providers"][record["provider"]]["failures"] = 0
                round_["closed"] = True
            return _dispatch(state, dimension, round_, now)

        return self._update(change)

    def close(self, dimension, status, reason, evidence=None):
        if status not in ("complete", "gap"):
            raise ValueError("结案状态仅支持 complete/gap")
        _text(reason, "reason")

        def change(state):
            dim = _dimension(state, dimension)
            if dim["status"] != "open":
                if dim["status"] == status and dim["reason"] == reason and not evidence:
                    return _summary(state, dimension)
                raise ValueError("已结案维度不能改写；具体冲突须先 reopen")
            if status == "complete" and any(not r["closed"] for r in dim["rounds"]):
                raise ValueError("在途调用尚未登记，不能 complete")
            _evidence(dimension, dim, evidence or [])
            if status == "complete" and _missing(dimension, dim):
                raise ValueError(f"缺少必要问题的证据：{_missing(dimension, dim)}")
            for round_ in dim["rounds"]:
                round_["closed"] = True
                for record in round_["attempts"]:
                    if record["outcome"] == "pending":
                        record["outcome"] = "abandoned"
            dim["status"], dim["reason"] = status, reason
            return _summary(state, dimension)

        return self._update(change)

    def reopen(self, dimension, conflict, impact):
        _text(conflict, "conflict")
        _text(impact, "impact")

        def change(state):
            dim = _dimension(state, dimension)
            if dim["status"] == "open" or dim["reopen_used"]:
                raise ValueError("仅已结案维度可因具体冲突重开一次")
            if "execution" in state:
                state["execution"]["phase"] = "research"
                state["execution"]["snapshot"] = None
            dim["reopen_used"] = True
            dim["status"] = "open"
            dim["reason"] = f"冲突：{conflict}；影响：{impact}"
            return _summary(state, dimension)

        return self._update(change)

    def seal(self, dimensions):
        derived = calculate(dimensions)

        def change(state):
            check_research(
                self.path, {**state["stock"], "dimensions": dimensions}, require_snapshot=False
            )
            if "execution" in state:
                state["execution"]["phase"] = "report"
                state["execution"]["snapshot"] = {
                    "dimensions": dimensions,
                    "derived": derived,
                    "calculated_at": time.time(),
                }
            return derived

        return self._update(change)


def check_research(
    path, draft, stock=None, *, require_bank=False, require_insurance=False, require_snapshot=True
):
    state = _load(Path(path))
    if _identity(draft) != state["stock"]:
        raise ValueError("取证状态与本次评级股票身份不一致")
    if stock is not None and _digest(stock) != state["input_sha256"]:
        raise ValueError("取证状态与原始 stock 输入不一致")
    if require_bank and require_insurance:
        raise ValueError("只能使用一种金融取证模式")
    required_mode = "bank" if require_bank else "insurance" if require_insurance else None
    if required_mode and (
        "financial" not in state["dimensions"]
        or state["dimensions"]["financial"].get("mode", "bank") != required_mode
    ):
        raise ValueError("金融补数须先 init 对应行业模式，并结案 financial 取证")
    for key, dim in state["dimensions"].items():
        if dim["status"] == "open":
            raise ValueError(f"{key} 尚未结案，先 complete 或 gap")
        if dim["status"] == "gap" and draft["dimensions"][key] is not None:
            raise ValueError(f"{key} 存在证据缺口，评分必须为 null")
        if dim["status"] == "complete" and (draft["dimensions"][key] is None or _missing(key, dim)):
            raise ValueError(f"{key} complete 状态与证据/分数不一致")

    if require_snapshot and "execution" in state:
        execution = state["execution"]
        if (
            execution["phase"] != "report"
            or execution["snapshot"]["dimensions"] != draft["dimensions"]
        ):
            raise ValueError(
                "未计算最终版维度或改分后快照失效；先 calculate --research-state，再成稿/finalize"
            )


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status", "start", "result", "close", "reopen"))
    parser.add_argument("--state", required=True)
    parser.add_argument("--stock")
    parser.add_argument(
        "--research-limit", type=int, help="Immutable global research-call budget (init only)"
    )
    parser.add_argument("--providers", nargs="+")
    parser.add_argument(
        "--bank-research", action="store_true", help="Enable bank E evidence budget (init only)"
    )
    parser.add_argument(
        "--insurance-research",
        action="store_true",
        help="Enable insurance E evidence budget (init only)",
    )
    parser.add_argument("--dimension")
    parser.add_argument("--question")
    parser.add_argument("--impact")
    parser.add_argument("--request-id")
    parser.add_argument("--input", help="Result object or close evidence array JSON")
    parser.add_argument("--status", choices=("complete", "gap"))
    parser.add_argument("--reason")
    parser.add_argument("--conflict")
    args = parser.parse_args(argv)
    run = ResearchRun(args.state)
    try:
        if args.research_limit is not None and args.command != "init":
            raise ValueError("--research-limit 仅用于 init")
        if (args.bank_research or args.insurance_research) and args.command != "init":
            raise ValueError("金融取证模式参数仅用于 init")
        if args.command == "init":
            if not args.stock:
                raise ValueError("init 需要 --stock 和 --providers")
            result = run.init(
                _read(args.stock),
                args.providers,
                bank_research=args.bank_research,
                insurance_research=args.insurance_research,
                research_limit=args.research_limit,
            )
        elif args.command == "status":
            result = run.status(args.dimension)
        elif args.command == "start":
            result = run.start(args.dimension, args.question, args.impact, args.request_id)
        elif args.command == "result":
            if not args.input:
                raise ValueError("result 需要 --input 结果文件")
            payload = _read(args.input)
            result = run.result(**payload)
        elif args.command == "close":
            result = run.close(
                args.dimension, args.status, args.reason, _read(args.input) if args.input else None
            )
        else:
            result = run.reopen(args.dimension, args.conflict, args.impact)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"research_state: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
