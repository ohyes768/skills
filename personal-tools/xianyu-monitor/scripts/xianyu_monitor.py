#!/usr/bin/env python3
"""闲鱼捡漏监控 CLI。

对接闲鱼智能监控机器人 (http://192.168.31.73:8010, FastAPI v2.0.0)：
  wish     新建监控任务（许愿）
  wishes   列出全部许愿与运行状态
  remove   取消许愿（买到后删除任务；--pause 仅停用保留配置）
  report   拉取结果并汇总为 Markdown（增量，按本地水位线 state）
  publish  report + 通过公共 rss-relay-publish CLI 推送 RSS

仅依赖 Python 3.10+ 标准库。RSS 投递委托 knowledge/rss-relay-publish 的
rss_publish.py（定位逻辑见 _locate_rss_cli），不自行 POST。
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEFAULT_BASE = os.environ.get("XIANYU_API_BASE", "http://192.168.31.73:8010")
# 同一服务的备选地址（Tailscale/局域网），主地址不可达时自动切换
FALLBACK_BASES = ["http://192.168.31.73:8010", "http://100.111.184.19:8010"]
CST = timezone(timedelta(hours=8))  # Asia/Shanghai
SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = SKILL_DIR / "state"


def _state_dir() -> Path:
    d = Path(os.environ.get("XIANYU_MONITOR_STATE_DIR", str(DEFAULT_STATE_DIR)))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- HTTP helpers

def _request(method: str, path: str, *, base: str = DEFAULT_BASE,
             payload: dict | None = None, timeout: int = 20) -> tuple[int, object]:
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        status = exc.code
    except urllib.error.URLError as exc:
        # 主地址不可达时按备选地址自动切换（仅 GET 等幂等请求；写操作不带 base 重试）
        if method == "GET" and base == DEFAULT_BASE:
            for fb in FALLBACK_BASES:
                if fb == base:
                    continue
                try:
                    return _request(method, path, base=fb, payload=payload, timeout=timeout)
                except SystemExit:
                    continue
        raise SystemExit(f"[xianyu-monitor] API 不可达: {url} ({exc.reason})")
    try:
        return status, (json.loads(body) if body else None)
    except ValueError:
        return status, body


def _ok(status: int, body: object, action: str) -> object:
    if status >= 400:
        raise SystemExit(f"[xianyu-monitor] {action} 失败 HTTP {status}: {json.dumps(body, ensure_ascii=False)[:500]}")
    return body


# ---------------------------------------------------------------- wish / wishes / remove

def cmd_wish(args: argparse.Namespace) -> None:
    # 服务端硬约束：AI 模式 description 不能为空（422），提前校验给出可操作的报错
    if args.mode == "ai" and not (args.description or "").strip():
        raise SystemExit("[xianyu-monitor] mode=ai 必须提供 --description（给 AI 的推荐标准），"
                         "例如：'只推荐低于150元、功能正常、成色较好的，排除进水/坏轴'")
    task = {
        "task_name": args.name,
        "keyword": args.keyword,
        "description": args.description or "",
        "enabled": not args.paused,
        "analyze_images": not args.no_images,
        "max_pages": args.pages,
        "personal_only": not args.all_sellers,
        "min_price": args.min_price or "",
        "max_price": args.max_price or "",
        "free_shipping": args.free_shipping,
        "region": args.region or "",
        "cron": args.cron,
        "decision_mode": args.mode,
        "keyword_rules": [k.strip() for k in args.rules.split(",")] if args.rules else [],
        "account_strategy": args.account_strategy,
    }
    if not task["cron"]:
        task["cron"] = None
    # AI 模式必须挂 ai_prompt_criteria_file，否则分析器报「任务未配置AI prompt，跳过分析」。
    # 服务端没有创建提示词文件的 API（PUT 只能更新已有文件），直接写 NAS 本地 prompts 卷。
    criteria_rel = ""
    if args.mode == "ai":
        fname = f"{args.name}_criteria.txt"
        prompts = []
        for src in (os.environ.get("XIANYU_PROMPTS_DIR", ""),
                    os.path.expanduser("~/ai-goofish-monitor/prompts")):
            if src and os.path.isdir(src):
                prompts.append(Path(src))
        if not prompts:
            raise SystemExit("[xianyu-monitor] mode=ai 需要写判定标准文件，但找不到监控服务 prompts 目录"
                             "（默认 ~/ai-goofish-monitor/prompts，可用 XIANYU_PROMPTS_DIR 指定）")
        criteria_text = (
            "### **判定标准（用户许愿池需求）**\n\n"
            "用户想捡漏「" + args.keyword + "」，请按以下标准评估：\n- "
            + (args.description or "").strip().replace("\n", "\n- ") + "\n"
        )
        target = prompts[0] / fname
        target.write_text(criteria_text, "utf-8")
        criteria_rel = f"prompts/{fname}"
        task["ai_prompt_criteria_file"] = criteria_rel
        print(f"[xianyu-monitor] 已写判定标准 → {target}", file=sys.stderr)
    status, body = _request("POST", "/api/tasks/", payload=task)
    _ok(status, body, f"创建任务 {args.name!r}")
    print(json.dumps(body, ensure_ascii=False, indent=1))
    print(f"[xianyu-monitor] 已创建许愿「{args.name}」 keyword={args.keyword}", file=sys.stderr)
    if task["cron"]:
        print("[xianyu-monitor] cron 已设置，定时抓取由监控服务自行执行。", file=sys.stderr)
    else:
        print("[xianyu-monitor] 未设置 cron，需要手动 POST /api/tasks/start/{task_id} 触发抓取。", file=sys.stderr)


def cmd_wishes(args: argparse.Namespace) -> None:
    tasks = _ok(*_request("GET", "/api/tasks"), action="获取任务列表")
    if args.json:
        print(json.dumps(tasks, ensure_ascii=False, indent=1))
        return
    # 合并 dashboard 统计：商品数、最近抓取时间（接口失败不阻塞列表展示）
    dash = {}
    try:
        summary = _ok(*_request("GET", "/api/dashboard/summary", timeout=10),
                      action="获取看板统计").get("task_summaries", [])
        dash = {s.get("task_id"): s for s in summary}
    except SystemExit as exc:
        print(f"[xianyu-monitor] 看板统计不可用，仅列任务配置：{exc}", file=sys.stderr)
    header = (f"{'id':>3}  {'运行':^4}  {'启用':^4}  {'模式':^7}  {'价格':^9}  {'商品':>5}  "
              f"{'最近抓取':^16}  名称 / 关键词 / 地区 / cron")
    print(header)
    for t in tasks:
        price = "-".join([t.get("min_price") or "", t.get("max_price") or ""]).strip("-") or "-"
        s = dash.get(t["id"], {})
        total = s.get("total_items", "-")
        last = str(s.get("latest_crawl_time") or "-")
        last_fmt = last[:16].replace("T", " ") if last != "-" else "-"
        print(f"{t['id']:>3}  {'▶' if t.get('is_running') else '·':^4}  {'✓' if t.get('enabled') else '✗':^4}"
              f"  {t.get('decision_mode', ''):^7}  {price:^9}  {str(total):>5}  {last_fmt:^16}"
              f"  {t['task_name']} / {t['keyword']} / {t.get('region') or '-'} / {t.get('cron') or '-'}")


def _find_task(task_id: int | None, name: str | None) -> dict:
    tasks = _ok(*_request("GET", "/api/tasks"), action="获取任务列表")
    if task_id is not None:
        for t in tasks:
            if t["id"] == task_id:
                return t
        raise SystemExit(f"[xianyu-monitor] 找不到 task_id={task_id}")
    if name:
        hits = [t for t in tasks if t["task_name"] == name]
        if not hits:
            raise SystemExit(f"[xianyu-monitor] 找不到任务名 {name!r}；现有: {[t['task_name'] for t in tasks]}")
        if len(hits) > 1:
            raise SystemExit(f"[xianyu-monitor] 任务名 {name!r} 有 {len(hits)} 个同名，请用 --task-id")
        return hits[0]
    raise SystemExit("[xianyu-monitor] 需要 --task-id 或 --task-name")


def cmd_remove(args: argparse.Namespace) -> None:
    task = _find_task(args.task_id, args.task_name)
    tid, tname = task["id"], task["task_name"]
    if args.pause:
        status, body = _request("PATCH", f"/api/tasks/{tid}", payload={"enabled": False})
        _ok(status, body, f"停用任务 {tid}")
        print(f"[xianyu-monitor] 已停用「{tname}」(task_id={tid})，配置保留。", file=sys.stderr)
    else:
        if not args.yes:
            raise SystemExit(f"[xianyu-monitor] 将删除「{tname}」(task_id={tid})。确认请加 --yes")
        status, body = _request("DELETE", f"/api/tasks/{tid}")
        _ok(status, body, f"删除任务 {tid}")
        print(f"[xianyu-monitor] 已删除许愿「{tname}」(task_id={tid})。", file=sys.stderr)
        if args.keep_results:
            print("[xianyu-monitor] --keep-results：结果文件保留。", file=sys.stderr)
        else:
            _cleanup_results(tname, task.get("keyword") or tname)


def _cleanup_results(task_name: str, keyword: str) -> None:
    """删除任务后清理其结果文件与水位线；跳过仍被其他任务引用的共享文件。"""
    remaining = _ok(*_request("GET", "/api/tasks"), action="获取剩余任务")
    used = set()
    for t in remaining:
        used.update({t["task_name"], t.get("keyword") or ""})
    for cand in dict.fromkeys([task_name, keyword]):
        fname = f"{cand}_full_data.jsonl"
        if fname in {f"{u}_full_data.jsonl" for u in used if u}:
            print(f"[xianyu-monitor] 结果文件 {fname} 仍被其他心愿使用，保留。", file=sys.stderr)
            continue
        status, _ = _request("GET", f"/api/results/{urllib.parse.quote(fname)}?page=1&limit=1", timeout=10)
        if status >= 400:
            continue  # 文件本来就不存在
        status, body = _request("DELETE", f"/api/results/{urllib.parse.quote(fname)}")
        if status < 400:
            print(f"[xianyu-monitor] 已删除结果文件 {fname}。", file=sys.stderr)
        else:
            print(f"[xianyu-monitor] 结果文件 {fname} 删除失败 HTTP {status}（可稍后手动清理）。", file=sys.stderr)
    # 清水位线
    f = _state_dir() / "watermarks.json"
    try:
        marks = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        marks = {}
    for key in [task_name, keyword]:
        marks.pop(key, None)
    f.write_text(json.dumps(marks, ensure_ascii=False, indent=1), "utf-8")


# ---------------------------------------------------------------- report / publish

def _load_watermark(task_name: str) -> str:
    f = _state_dir() / "watermarks.json"
    try:
        return json.loads(f.read_text("utf-8")).get(task_name, "")
    except (OSError, ValueError):
        return ""


def _save_watermark(task_name: str, crawl_time: str) -> None:
    f = _state_dir() / "watermarks.json"
    try:
        data = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    data[task_name] = crawl_time
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def _fetch_all_items(filename: str, *, recommended_only: bool = False) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({"page": page, "limit": 100,
                                     "recommended_only": str(recommended_only).lower()})
        status, body = _request("GET", f"/api/results/{urllib.parse.quote(filename)}?{qs}")
        _ok(status, body, f"读取结果 {filename} 第 {page} 页")
        batch = body.get("items", [])
        items.extend(batch)
        total, got = body.get("total_items", 0), page * 100
        if not batch or got >= total:
            break
        page += 1
    return items


def _fmt_price(info: dict) -> str:
    return str(info.get("当前售价") or "").replace("¥", "").strip() or "?"


def _item_row(it: dict) -> dict:
    info = it.get("商品信息", {})
    ai = it.get("ai_analysis") or {}
    ref = ((it.get("价格参考") or {}).get("本商品价格位置") or {})
    return {
        "crawl": it.get("爬取时间", ""),
        "task": it.get("任务名称", ""),
        "id": str(info.get("商品ID") or ""),
        "title": info.get("商品标题", ""),
        "price": _fmt_price(info),
        "region": info.get("发货地区", ""),
        "published": info.get("发布时间", ""),
        "url": info.get("商品链接", ""),
        "app_url": f"fleamarket://item?id={info.get('商品ID')}" if info.get("商品ID") else "",
        "image": info.get("商品主图链接", ""),
        "seller": (it.get("卖家信息") or {}).get("卖家昵称", ""),
        "credit": (it.get("卖家信息") or {}).get("卖家信用等级", ""),
        "deal_score": ref.get("deal_score"),
        "deal_label": ref.get("deal_label"),
        "reason": ai.get("reason", ""),
        "matched": ai.get("matched_keywords") or [],
        "source": ai.get("analysis_source", ""),
    }


def _render_md(rows: list[dict], *, since: str, total_seen: int) -> str:
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    lines = [f"# 闲鱼捡漏速报 {now}", ""]
    if since:
        lines.append(f"> 增量范围：爬取时间晚于 `{since}`；本次新增 {len(rows)} 条（推荐池共 {total_seen} 条）。")
    else:
        lines.append(f"> 全量首报：推荐池共 {total_seen} 条，本次展示 {len(rows)} 条。")
    lines.append("")
    for r in rows:
        score = f" {r['deal_score']}分" if r["deal_score"] is not None else ""
        label = f"（{r['deal_label']}）" if r["deal_label"] else ""
        lines.append(f"## [{r['title']}]({r['url']})")
        lines.append("")
        lines.append(f"- **价格**：¥{r['price']}{score}{label}｜地区：{r['region'] or '-'}｜发布：{r['published'] or '-'}")
        seller_bits = [r["seller"] or "-"]
        if r["credit"]:
            seller_bits.append(r["credit"])
        lines.append(f"- **卖家**：{'，'.join(seller_bits)}")
        if r["reason"]:
            src = "AI" if r["source"] == "ai" else "关键词"
            lines.append(f"- **判定**：{src}推荐 —— {r['reason']}")
        if r["image"]:
            lines.append(f"- ![商品图]({r['image']})")
        lines.append("")
    return "\n".join(lines) + "\n"


def _collect(args: argparse.Namespace) -> tuple[str, list[dict], int]:
    tasks = _ok(*_request("GET", "/api/tasks"), action="获取任务列表")
    targets = []
    if args.task_name:
        targets = [t for t in tasks if t["task_name"] == args.task_name]
        if not targets:
            raise SystemExit(f"[xianyu-monitor] 找不到任务 {args.task_name!r}")
    else:
        targets = [t for t in tasks if t.get("enabled")]
    if not targets:
        raise SystemExit("[xianyu-monitor] 没有可汇总的启用任务")

    all_rows: list[dict] = []
    newest_seen = ""
    for t in targets:
        tname, fname = t["task_name"], _result_filename(t)
        since = "" if args.full else _load_watermark(tname)
        items = _fetch_all_items(fname)
        kept = []
        for it in items:
            crawl = it.get("爬取时间", "")
            if since and crawl <= since:
                continue
            if it.get("_effective_hidden"):
                continue
            kept.append(_item_row(it))
        if items:
            newest_seen = max(newest_seen, max(i.get("爬取时间", "") for i in items))
        all_rows.extend(kept)
    all_rows.sort(key=lambda r: (r["deal_score"] if r["deal_score"] is not None else -1), reverse=True)
    rows = all_rows if args.full else all_rows[: args.top]
    return _render_md(rows, since="".join(sorted({r["crawl"] for r in rows})[-1:] if rows else []) or "",
                      total_seen=len(all_rows)), all_rows, ("" if args.full else newest_seen)


def cmd_report(args: argparse.Namespace) -> None:
    md, all_rows, newest = _collect(args)
    out = Path(args.output) if args.output else _state_dir() / f"report-{datetime.now(CST):%Y%m%d-%H%M%S}.md"
    out.write_text(md, "utf-8")
    print(f"[xianyu-monitor] 汇总 {len(all_rows)} 条增量，展示前 {min(len(all_rows), args.top) if not args.full else len(all_rows)} 条 → {out}",
          file=sys.stderr)
    if args.update_watermark and newest and not args.full:
        for tname in {r["task"] for r in all_rows}:
            _save_watermark(tname, newest)
        print(f"[xianyu-monitor] 水位线已更新 → {newest}", file=sys.stderr)
    if args.print:
        sys.stdout.write(md)
    else:
        print(str(out))


def _locate_rss_cli() -> Path:
    env = os.environ.get("RSS_RELAY_SKILL_DIR")
    candidates = ([Path(env) / "scripts/rss_publish.py"] if env else []) + [
        Path("/home/ohyes768/skills/knowledge/rss-relay-publish/scripts/rss_publish.py"),
        Path(__file__).resolve().parents[2] / "knowledge/rss-relay-publish/scripts/rss_publish.py",
        Path.home() / ".hermes/skills/rss-relay-publish/scripts/rss_publish.py",
        Path.home() / ".codex/skills/rss-relay-publish/scripts/rss_publish.py",
        Path.home() / ".agents/skills/rss-relay-publish/scripts/rss_publish.py",
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    raise SystemExit("[xianyu-monitor] 找不到 rss-relay-publish 公共 CLI；安装后设置 RSS_RELAY_SKILL_DIR")


def _ensure_channel(channel: str, *, insecure: bool = False) -> None:
    """频道未登记时先创建（POST /channels），避免正式发布 404。"""
    base = os.environ.get("RSS_RELAY_BASE_URL", "https://web.duomi77.cn:9443/rss/api/rss-relay")
    try:
        req = urllib.request.Request(f"{base}/channels", method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            channels = json.loads(resp.read().decode("utf-8")).get("channels", [])
        if any(c.get("id") == channel for c in channels):
            return
        payload = json.dumps({"id": channel, "title": channel, "description": "闲鱼监控捡漏速报"},
                             ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{base}/channels", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        ctx = None
        if insecure:
            ctx = ssl._create_unverified_context()  # noqa: SLF001 显式 --insecure 才走
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            created = json.loads(resp.read().decode("utf-8"))
        print(f"[xianyu-monitor] RSS 频道 {channel!r} 不存在，已自动创建: {json.dumps(created, ensure_ascii=False)}",
              file=sys.stderr)
    except Exception as exc:  # 频道预检失败不阻塞发布，交给公共 CLI 报错
        print(f"[xianyu-monitor] 频道 {channel!r} 预检失败（将直接尝试发布）: {exc}", file=sys.stderr)


def cmd_publish(args: argparse.Namespace) -> None:
    _ensure_channel(args.channel, insecure=args.insecure)
    md, all_rows, newest = _collect(args)
    if not all_rows and not args.full:
        print("[xianyu-monitor] 无新增推荐，跳过发布。", file=sys.stderr)
        return
    out = _state_dir() / f"report-{datetime.now(CST):%Y%m%d-%H%M%S}.md"
    out.write_text(md, "utf-8")
    cli = _locate_rss_cli()
    key = args.dedupe_key or f"xianyu:{datetime.now(CST):%Y-%m-%d}"
    cmd_args = [sys.executable, str(cli), "publish", "--file", str(out),
                "--title", args.title, "--channel", args.channel, "--source", "xianyu-monitor",
                "--dedupe-key", key, "--timeout", "30"]
    if args.insecure:
        cmd_args.append("--insecure")
    if args.dry_run:
        cmd_args.append("--dry-run")
    proc = subprocess.run(cmd_args, capture_output=True)
    stdout = proc.stdout.decode("utf-8", "replace")
    try:
        result = json.loads(stdout)
    except ValueError:
        raise SystemExit(f"[xianyu-monitor] RSS CLI 未返回 JSON（exit={proc.returncode}）\n{stdout[:800]}\n{proc.stderr.decode('utf-8', 'replace')[:800]}")
    if args.update_watermark and newest and result.get("status") in ("published", "duplicate"):
        for tname in {r["task"] for r in all_rows}:
            _save_watermark(tname, newest)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"[xianyu-monitor] Markdown: {out}", file=sys.stderr)


def _result_filename(task: dict) -> str:
    """AI 模式任务的结果文件按关键词命名（划船机_full_data.jsonl），关键词模式按任务名。
    两者探测：先按任务名，404/不存在则回退关键词。"""
    for cand in dict.fromkeys([task["task_name"], task.get("keyword") or task["task_name"]]):
        fname = f"{cand}_full_data.jsonl"
        status, _ = _request("GET", f"/api/results/{urllib.parse.quote(fname)}?page=1&limit=1",
                             timeout=10)
        if status < 400:
            return fname
    return f"{task['task_name']}_full_data.jsonl"


def cmd_show(args: argparse.Namespace) -> None:
    """逛全池：与水位线无关，列出推荐商品（含停用任务），买到/隐藏的默认排除。"""
    tasks = _ok(*_request("GET", "/api/tasks"), action="获取任务列表")
    targets = ([t for t in tasks if t["task_name"] == args.task_name] if args.task_name else tasks)
    if args.task_name and not targets:
        raise SystemExit(f"[xianyu-monitor] 找不到任务 {args.task_name!r}")
    rows: list[dict] = []
    for t in targets:
        fname = _result_filename(t)
        for it in _fetch_all_items(fname):
            if it.get("_effective_hidden"):
                continue
            ai = it.get("ai_analysis") or {}
            if args.include_rejected or ai.get("is_recommended"):
                rows.append(_item_row(it))
    if args.keyword:
        rows = [r for r in rows if args.keyword.lower() in r["title"].lower()]
    if args.region:
        rows = [r for r in rows if args.region in (r["region"] or "")]
    if args.max_price:
        rows = [r for r in rows if r["price"].replace(".", "").isdigit() and float(r["price"]) <= args.max_price]
    seen_ids = set()
    deduped = []
    for r in rows:
        if r["id"] and r["id"] in seen_ids:
            continue
        seen_ids.add(r["id"])
        deduped.append(r)
    deduped.sort(key=lambda r: (r["deal_score"] if r["deal_score"] is not None else -1), reverse=True)
    rows = deduped[: args.top]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    print(f"共 {len(rows)} 件（按捡漏分排序，排除已买到/隐藏；当前水位线不参与本视图）")
    for r in rows:
        score = f"{r['deal_score']}分" if r["deal_score"] is not None else "-"
        print(f"[{score:^4}] ¥{r['price']:>7}  {r['region'] or '-':<6}  {r['title'][:36]}")
        short = r["url"].split("&referPageArgs")[0] or r["url"]
        print(f"        web: {short[:100]}")
        if r["app_url"]:
            print(f"        app: {r['app_url']}   （手机装了闲鱼时可直接唤起 App）")
        if r["reason"]:
            print(f"        判定: {r['reason'][:80]}")
    if not rows:
        print("（空）")


def cmd_bought(args: argparse.Namespace) -> None:
    """买到/不要了：把商品标记为 hidden，浏览与增量自动排除，但历史保留。"""
    tasks = _ok(*_request("GET", "/api/tasks"), action="获取任务列表")
    for t in tasks:
        fname = _result_filename(t)
        items = _fetch_all_items(fname)
        hits = [i for i in items if str((i.get("商品信息") or {}).get("商品ID")) == args.item_id]
        if hits:
            info = hits[0].get("商品信息") or {}
            status, body = _request("PATCH",
                f"/api/results/{urllib.parse.quote(fname)}/items/{args.item_id}/status",
                payload={"status": "hidden"})
            _ok(status, body, f"标记商品 {args.item_id}")
            print(f"[xianyu-monitor] 已标记「{info.get('商品标题', '')[:30]}」为 hidden"
                  f"（任务「{t['task_name']}」），浏览与增量不再展示。", file=sys.stderr)
            return
    raise SystemExit(f"[xianyu-monitor] 在所有任务结果里都没找到商品ID {args.item_id}")


def _collect_wishlist_rows(args_top: int) -> list[dict]:
    """所有许愿（含停用）的推荐池，按商品ID去重。"""
    tasks = _ok(*_request("GET", "/api/tasks"), action="获取任务列表")
    rows: list[dict] = []
    for t in tasks:
        fname = _result_filename(t)
        for it in _fetch_all_items(fname):
            if it.get("_effective_hidden"):
                continue
            ai = it.get("ai_analysis") or {}
            if ai.get("is_recommended"):
                r = _item_row(it)
                # 归属到当前遍历的心愿：老心愿删除后，其结果文件由现存同关键词心愿继承
                r["task"] = t["task_name"]
                rows.append(r)
    seen = set()
    deduped = []
    for r in rows:
        if r["id"] and r["id"] in seen:
            continue
        seen.add(r["id"])
        deduped.append(r)
    deduped.sort(key=lambda r: (r["deal_score"] if r["deal_score"] is not None else -1), reverse=True)
    enabled_map = {t["task_name"]: t.get("enabled") for t in tasks}
    for r in deduped:
        r["task_enabled"] = enabled_map.get(r["task"])
    return deduped


def _render_digest(tasks: list[dict], rows: list[dict], top: int) -> str:
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    lines = [f"# 许愿池现状 {now}", ""]
    lines.append(f"> 共 {len(tasks)} 个心愿，推荐池展示每个心愿前 {top} 条，按捡漏分排序。")
    for t in tasks:
        state = "✅ 启用" if t.get("enabled") else "⏸ 停用"
        mode = "AI 判定" if t.get("decision_mode") == "ai" else "关键词"
        req = (t.get("description") or "").strip()
        if t.get("decision_mode") == "keyword" and t.get("keyword_rules"):
            req = "关键词命中：" + "、".join(t["keyword_rules"])
        lines.append("")
        lines.append(f"## {t['task_name']}（{state} · {mode} · 每{({'0 21 * * *': '晚 21:00'}.get(t.get('cron') or '', (t.get('cron') or '手动触发')))}）")
        lines.append("")
        lines.append(f"- **要求**：{req or '（未填写）'}")
        price = "~".join([t.get("min_price") or "0", t.get("max_price") or "不限"])
        lines.append(f"- **条件**：价格 {price}｜地区 {t.get('region') or '不限'}")
        wish_rows = [r for r in rows if r["task"] == t["task_name"]]
        if not wish_rows:
            lines.append("- （暂无推荐）")
        for i, r in enumerate(wish_rows[:top], 1):
            score = f"{r['deal_score']}分" if r["deal_score"] is not None else "-"
            mark = "✅" if r.get("task_enabled") else "⏸"
            short = r["url"].split("&referPageArgs")[0] or r["url"]
            lines.append(f"{i}. [{score}] ¥{r['price']} {r['region'] or '-'}｜[{r['title'][:32]}…]({short}) {mark}")
            if r["app_url"]:
                lines.append(f"   - App 打开：{r['app_url']}")
            if r["reason"] and "关键词" not in r["reason"]:
                lines.append(f"   - 判定：{r['reason'][:90]}")
    return "\n".join(lines) + "\n"


def cmd_digest(args: argparse.Namespace) -> None:
    """把许愿池现状（心愿+要求+每个心愿前 N 条推荐）推到 RSS。"""
    tasks = _ok(*_request("GET", "/api/tasks"), action="获取任务列表")
    rows = _collect_wishlist_rows(args.top)
    md = _render_digest(tasks, rows, args.top)
    out = _state_dir() / f"digest-{datetime.now(CST):%Y%m%d-%H%M%S}.md"
    out.write_text(md, "utf-8")
    if args.print:
        sys.stdout.write(md)
        return
    _ensure_channel(args.channel, insecure=args.insecure)
    cli = _locate_rss_cli()
    key = args.dedupe_key or f"xianyu-digest:{datetime.now(CST):%Y-%m-%d}"
    cmd_args = [sys.executable, str(cli), "publish", "--file", str(out),
                "--title", args.title, "--channel", args.channel, "--source", "xianyu-monitor",
                "--dedupe-key", key, "--timeout", "30"]
    if args.insecure:
        cmd_args.append("--insecure")
    if args.dry_run:
        cmd_args.append("--dry-run")
    proc = subprocess.run(cmd_args, capture_output=True)
    try:
        result = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        raise SystemExit(f"[xianyu-monitor] RSS CLI 未返回 JSON: {proc.stdout.decode('utf-8', 'replace')[:400]}")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"[xianyu-monitor] Markdown: {out}", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description="闲鱼捡漏监控（许愿池）")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("wish", help="新建监控任务")
    w.add_argument("--name", required=True, help="任务名（唯一）")
    w.add_argument("--keyword", required=True)
    w.add_argument("--min-price", default="", help="最低价")
    w.add_argument("--max-price", default="", help="最高价")
    w.add_argument("--region", default="", help='如 "浙江/杭州/全杭州"')
    w.add_argument("--description", default="", help="AI 模式必填：给 AI 的推荐标准描述")
    w.add_argument("--cron", default=None, help="5 段 cron；不填则需手动触发 start")
    w.add_argument("--pages", type=int, default=3)
    w.add_argument("--mode", choices=["ai", "keyword"], default="ai")
    w.add_argument("--rules", default="", help="逗号分隔关键词规则（mode=keyword 时）")
    w.add_argument("--all-sellers", action="store_true", help="不限个人卖家")
    w.add_argument("--no-images", action="store_true", help="不做图片 AI 分析")
    w.add_argument("--free-shipping", action="store_true")
    w.add_argument("--account-strategy", default="auto", choices=["auto", "fixed", "rotate"])
    w.add_argument("--paused", action="store_true", help="创建但停用")
    w.set_defaults(func=cmd_wish)

    l = sub.add_parser("wishes", help="列出全部许愿")
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_wishes)

    r = sub.add_parser("remove", help="取消许愿（买到后）")
    r.add_argument("--task-id", type=int)
    r.add_argument("--task-name")
    r.add_argument("--pause", action="store_true", help="只停用不删除")
    r.add_argument("--keep-results", action="store_true", help="删除任务但保留结果文件")
    r.add_argument("--yes", action="store_true")
    r.set_defaults(func=cmd_remove)

    s = sub.add_parser("show", help="逛全池：列出推荐商品（与水位线无关）")
    s.add_argument("--task-name", help="只看该任务")
    s.add_argument("--keyword", help="标题包含")
    s.add_argument("--region", help="地区包含，如 滨江/萧山")
    s.add_argument("--max-price", type=float)
    s.add_argument("--top", type=int, default=7)
    s.add_argument("--include-rejected", action="store_true", help="连 AI/关键词否决的也列出")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    b = sub.add_parser("bought", help="买到/不要了：按商品ID标记 hidden")
    b.add_argument("item_id", help="商品ID（show --json 或结果链接里取）")
    b.set_defaults(func=cmd_bought)

    d = sub.add_parser("digest", help="许愿池现状（心愿+要求+每个心愿Top7）推 RSS")
    d.add_argument("--title", default=None, help="默认「许愿池现状 <日期>」")
    d.add_argument("--channel", default="xianyu")
    d.add_argument("--top", type=int, default=7, help="每个心愿展示前 N 条（默认 7）")
    d.add_argument("--dedupe-key", default=None)
    d.add_argument("--print", action="store_true", help="只生成不推送，stdout 输出 Markdown")
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--insecure", action="store_true")
    d.set_defaults(func=cmd_digest)

    for name, fn in (("report", cmd_report), ("publish", cmd_publish)):
        c = sub.add_parser(name, help=f"汇总增量结果{'并推 RSS' if name == 'publish' else ''}")
        c.add_argument("--task-name", help="只汇总该任务；默认全部启用任务")
        c.add_argument("--full", action="store_true", help="忽略水位线全量汇总")
        c.add_argument("--top", type=int, default=7, help="按捡漏分展示前 N 条(默认 7)")
        c.add_argument("--output", help="Markdown 输出路径")
        if name == "report":
            c.add_argument("--print", action="store_true", help="输出 Markdown 到 stdout")
            c.add_argument("--update-watermark", action="store_true")
        else:
            c.add_argument("--title", required=True)
            c.add_argument("--channel", default="xianyu")
            c.add_argument("--dedupe-key", default=None)
            c.add_argument("--dry-run", action="store_true")
            c.add_argument("--insecure", action="store_true")
            c.add_argument("--update-watermark", action="store_true", help="发布确认后推进水位线")
        c.set_defaults(func=fn)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
