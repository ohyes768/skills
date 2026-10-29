"""Compact evidence progress; no per-request receipts or claimed host budgets."""

import argparse
import json
import re
import sys
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import quote, urlsplit

from fetch_financial_candidates import _write
from rating_math import _read, calculate
from research_state import REQUIRED_TOPICS, _digest, _evidence, _identity, _text


def make_progress(stock):
    return {
        "progress_type": "quality_rating_progress",
        "schema_version": 2,
        "stock": _identity(stock),
        "input_sha256": _digest(stock),
        "facts": [],
        "sources": [],
        "failed_sources": [],
        "dimensions": {
            key: {"status": "open", "score": None, "reason": "尚未分析", "topics": {}, "gaps": []}
            for key in REQUIRED_TOPICS
        },
    }


def load_progress(path):
    """Validate persisted references even before decisions are terminal."""
    data = _read(path)
    try:
        version = data.get("schema_version")
        expected = {
            "progress_type",
            "schema_version",
            "stock",
            "input_sha256",
            "facts",
            "failed_sources",
            "dimensions",
        }
        if version == 2:
            expected.add("sources")
        if (
            set(data) != expected
            or data["progress_type"] != "quality_rating_progress"
            or type(data["schema_version"]) is not int
            or version not in (1, 2)
        ):
            raise ValueError("不支持的轻量进度格式；旧账本请继续用 --research-state")
        _identity(data["stock"])
        if not re.fullmatch(r"[a-f0-9]{64}", data["input_sha256"]):
            raise ValueError("进度文件输入哈希无效")
        if not isinstance(data["facts"], list) or len(data["facts"]) > 48:
            raise ValueError("facts 必须为至多48条紧凑事实数组")
        sources = {}
        if version == 2:
            if not isinstance(data["sources"], list) or len(data["sources"]) > 48:
                raise ValueError("sources 必须为至多48项数组")
            for source in data["sources"]:
                _check_source(source)
                if source["id"] in sources:
                    raise ValueError("来源 id 重复")
                if any(item["url"] == source["url"] for item in sources.values()):
                    raise ValueError("同一 URL 请复用已有来源编号，不重复登记")
                sources[source["id"]] = source
        facts = {}
        for fact in data["facts"]:
            inline_fields = {
                "id",
                "statement",
                "url",
                "locator",
                "period",
            }
            shared_fields = (inline_fields - {"url"}) | {"source_id"}
            if not isinstance(fact, dict) or set(fact) not in (inline_fields, shared_fields):
                raise ValueError("事实须含 id/statement/locator/period 与 url 或 source_id")
            resolved = dict(fact)
            if "source_id" in fact:
                if not isinstance(fact["source_id"], str) or fact["source_id"] not in sources:
                    raise ValueError("事实引用了不存在的 source_id")
                resolved["url"] = sources[fact["source_id"]]["url"]
            fact_id = _text(fact["id"], "fact.id", 64)
            if fact_id in facts:
                raise ValueError("事实 id 重复")
            # Reuse the canonical source/locator/period checks, without a receipt.
            _evidence("business", {"evidence": []}, [{**resolved, "topic": "main_business"}])
            facts[fact_id] = resolved
        if not isinstance(data["failed_sources"], list) or len(data["failed_sources"]) > 16:
            raise ValueError("failed_sources 必须为至多16项数组")
        for source in data["failed_sources"]:
            if not isinstance(source, dict) or set(source) != {"provider", "reason"}:
                raise ValueError("失败渠道须含 provider/reason")
            _text(source["provider"], "provider", 64)
            _text(source["reason"], "失败原因", 500)
        if set(data["dimensions"]) != set(REQUIRED_TOPICS):
            raise ValueError("进度文件必须恰含 A-D 四个维度；财务使用独立F10包")
        for key, topics in REQUIRED_TOPICS.items():
            dim = data["dimensions"][key]
            if set(dim) != {"status", "score", "reason", "topics", "gaps"}:
                raise ValueError(f"{key} 进度字段不完整")
            status, score = dim["status"], dim["score"]
            if status not in ("open", "complete", "gap"):
                raise ValueError(f"{key} 状态须为 open/complete/gap")
            _text(dim["reason"], f"{key}.reason", 800)
            if not isinstance(dim["gaps"], list) or len(dim["gaps"]) > 12:
                raise ValueError(f"{key}.gaps 必须为至多12项数组")
            for gap in dim["gaps"]:
                _text(gap, f"{key}.gap", 500)
            if status == "complete":
                if type(score) is not int or not 1 <= score <= 5 or dim["gaps"]:
                    raise ValueError(f"{key} complete 须有1-5整数分且无核心缺口")
            elif score is not None or (status == "gap" and not dim["gaps"]):
                raise ValueError(f"{key} open/gap 必须未评分；gap须说明具体缺口")
            if not isinstance(dim["topics"], dict) or set(dim["topics"]) - set(topics):
                raise ValueError(f"{key} 包含未知 topic")
            expanded = []
            for topic, refs in dim["topics"].items():
                if not isinstance(refs, list) or not refs or len(refs) > 12:
                    raise ValueError(f"{key}.{topic} 须引用1-12个事实id")
                for ref in refs:
                    if not isinstance(ref, str) or ref not in facts:
                        raise ValueError(f"{key}.{topic} 引用了不存在的事实")
                    expanded.append({**facts[ref], "topic": topic})
            _evidence(key, {"evidence": []}, expanded)
            if status == "complete" and set(dim["topics"]) != set(topics):
                raise ValueError(f"{key} complete 尚缺必要判别主题")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("轻量进度结构损坏；修复原文件，不重建进度掩盖缺口") from exc
    return data


def _check_source(source):
    if not isinstance(source, dict) or set(source) != {
        "id",
        "title",
        "url",
        "source_type",
        "published_at",
        "accessed_at",
    }:
        raise ValueError("来源须含 id/title/url/source_type/published_at/accessed_at")
    if not isinstance(source["id"], str) or not re.fullmatch(r"S[1-9][0-9]*", source["id"]):
        raise ValueError("来源 id 须为 S1、S2 等稳定引用编号")
    _text(source["title"], "source.title", 240)
    url = _text(source["url"], "source.url", 512)
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc:
        raise ValueError("来源须为实际 http(s) 地址")
    if source["source_type"] not in ("official", "research", "data_platform", "media"):
        raise ValueError("source_type 须为 official/research/data_platform/media")
    for key in ("published_at", "accessed_at"):
        value = source[key]
        if value is None and key == "published_at":
            continue
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError(f"{key} 须为 YYYY-MM-DD；未知发布日期用 null")
    if source["published_at"] and source["published_at"] > source["accessed_at"]:
        raise ValueError("披露日期不能晚于访问日期")


def _cell(value):
    return (
        escape(str(value), quote=False)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def render_sources(data, *, stock=None, f10_data=None):
    """Render only cited facts; preserve IDs and never infer missing metadata."""
    sources = {s["id"]: s for s in data.get("sources", [])}
    facts = {f["id"]: f for f in data["facts"]}
    used = {}
    for dim in data["dimensions"].values():
        for refs in dim["topics"].values():
            for ref in refs:
                used[ref] = facts[ref]
    next_id = max((int(s[1:]) for s in sources), default=0) + 1
    groups, inline_ids = {}, {}
    for fact in used.values():
        sid = fact.get("source_id")
        if sid is None:
            url = fact["url"]
            if url not in inline_ids:
                sid = f"S{next_id}"
                next_id += 1
                inline_ids[url] = sid
                sources[sid] = {
                    "title": "标题未记录",
                    "url": url,
                    "source_type": None,
                    "published_at": None,
                    "accessed_at": None,
                }
            sid = inline_ids[url]
        groups.setdefault(sid, []).append(fact)
    if f10_data is not None:
        if stock is None:
            raise ValueError("合并 F10 来源须提供原始 --stock")
        if _digest(stock) != data["input_sha256"]:
            raise ValueError("F10 来源与进度输入不一致")
        from f10_financial import score_f10

        financial = score_f10(stock, f10_data)
        for source in financial["coverage"]["sources"]:
            sid = next(
                (key for key, value in sources.items() if value["url"] == source["url"]), None
            )
            if sid is None:
                sid = f"S{next_id}"
                next_id += 1
                sources[sid] = {**source, "source_type": "data_platform"}
            groups.setdefault(sid, []).append(
                {
                    "period": source["period"],
                    "locator": source["locator"],
                    "statement": source["support"],
                }
            )
    rows = ["| 编号 | 来源 | 披露日期 / 事实期间 | 定位与支持内容 |", "|---|---|---|---|"]
    labels = {
        "official": "公司/交易所/监管披露",
        "research": "研报",
        "data_platform": "第三方数据平台",
        "media": "媒体来源",
    }
    for sid, source_facts in groups.items():
        source = sources[sid]
        title = _cell(source["title"]).replace("[", "\\[").replace("]", "\\]")
        url = quote(source["url"], safe="/:?&=%#@+;$,~-_.!")
        label = labels.get(source["source_type"], "来源类型未记录")
        pub = source["published_at"]
        dates = (
            (f"目标期披露：{pub}" if source.get("target_publication") else pub)
            if pub
            else (
                f"未标注；访问于 {source['accessed_at']}" if source["accessed_at"] else "日期未记录"
            )
        )
        periods = "；".join(dict.fromkeys(f["period"] for f in source_facts))
        support = "；".join(
            dict.fromkeys(
                f"{f['locator']}：{f['statement'][:120]}{'…' if len(f['statement']) > 120 else ''}"
                for f in source_facts
            )
        )
        rows.append(
            f"| {sid} | [{title}](<{url}>)（{label}） | {_cell(dates)} / {_cell(periods)} | {_cell(support)} |"
        )
    return "\n".join(rows)


def check_progress(path, dimensions, stock=None, *, identity=None):
    data = load_progress(path)
    calculate(dimensions)
    if stock is not None and (
        _identity(stock) != data["stock"] or _digest(stock) != data["input_sha256"]
    ):
        raise ValueError("进度文件与原始 stock 不一致")
    if identity is not None and _identity(identity) != data["stock"]:
        raise ValueError("进度文件与本次评级股票身份不一致")
    for key, dim in data["dimensions"].items():
        if dim["status"] == "open":
            raise ValueError(f"{key} 尚未完成；先裁决或明确 gap")
        if dimensions[key] != dim["score"]:
            raise ValueError(f"{key} 与进度文件分数不一致；gap 必须为 null")
    return data


def summary(data):
    return {
        "stock": data["stock"],
        "fact_count": len(data["facts"]),
        "failed_sources": data["failed_sources"],
        "dimensions": {
            key: {k: dim[k] for k in ("status", "score", "gaps")}
            for key, dim in data["dimensions"].items()
        },
        "scope": "证据进度与分数一致性；不统计或强制工具调用预算，不证明事实真实",
    }


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status", "sources"))
    parser.add_argument("--stock", help="Original stock JSON; required for init")
    parser.add_argument("--output", required=True, help="Progress JSON path")
    parser.add_argument("--f10-data", help="Optional verified F10 packet for sources table")
    args = parser.parse_args(argv)
    try:
        if args.f10_data and args.command != "sources":
            raise ValueError("--f10-data 仅用于 sources")
        path = Path(args.output)
        if args.stock and path.resolve() == Path(args.stock).resolve():
            raise ValueError("进度文件不能覆盖原始 stock")
        if args.command == "init":
            if not args.stock:
                raise ValueError("init 必须提供 --stock")
            stock = _read(args.stock)
            if path.exists():
                data = load_progress(path)
                if data["stock"] != _identity(stock) or data["input_sha256"] != _digest(stock):
                    raise ValueError("现有进度绑定其他输入；不覆盖")
            else:
                data = make_progress(stock)
                _write(path, data)
        else:
            data = load_progress(path)
            if args.stock and data["input_sha256"] != _digest(_read(args.stock)):
                raise ValueError("进度文件与原始 stock 不一致")
        if args.command == "sources":
            print(
                render_sources(
                    data,
                    stock=_read(args.stock) if args.stock else None,
                    f10_data=_read(args.f10_data) if args.f10_data else None,
                )
            )
        else:
            print(json.dumps(summary(data), ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        print(f"research_progress: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
