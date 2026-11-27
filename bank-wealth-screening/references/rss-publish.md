# 推送到 RSS（可选，用户明确要求时才发）

筛选/净值结果可推送到个人 RSS 中转服务，实际投递委托公共包 `rss-relay-publish`（subprocess 调用其 `scripts/rss_publish.py`，不自己实现 POST；查重回执由公共层 SQLite 管理）。公共包按 `RSS_RELAY_SKILL_DIR` 环境变量或本仓库 `skills/knowledge/rss-relay-publish` 自动定位，找不到时明确失败不回退。

```bash
# 直接推 Markdown 报告
python scripts/rss_push.py --file report.md --title "杭行代销在售 2026-11-25" \
    --channel wealth --source bank-wealth-screening \
    --dedupe-key "hzbank-onsale:2026-11-27"

# 从 on_sale_hzbank.py / on_sale_cmb.py 的 JSON 输出自动渲染 Markdown 表格后推送
python scripts/rss_push.py --json hzbank_onsale.json --title "..." \
    --dedupe-key "hzbank-onsale:2026-11-27"
```

- `--dry-run` 仅预览；可选 `--url`、`--base-url`、`--ca-file`、`--insecure`（仅显式要求）。
- `--dedupe-key` 必须稳定唯一：建议 `<渠道>-onsale:<日期>`；修订版加 `:v2` 并在标题体现。
- stdout 是单个 JSON：`published`/`duplicate` 为成功；`conflict`=同键不同内容；`unknown`=可能已接收，同命令重跑只核对不重发。详见公共包 SKILL.md 判定表。
- **频道**：须已在 RSS 服务登记且启用（未登记时发布被拒，报 `preflight_failed "Channel not found"`，不自动建频道）。**2026-11-27 实测：默认的 `bank-wealth` 频道在服务端不存在，实际登记的理财频道是 `wealth`，推送用 `--channel wealth`**。已登记频道可用 `GET <base>/posts?limit=50` 看返回里的 channel 集合确认。
- 只查看/生成结果时不发布，不能因为加载本 skill 就自动发送。
