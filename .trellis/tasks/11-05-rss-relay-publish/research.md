# 本地证据（2026-11-05）

仅本地只读检查，未验证线上状态或生产发布。下列路径以 F:/personal-projects 为根。

| 位置 | 发现 |
|---|---|
| skills/README.md，登记与发布 | skill 源码在本仓库，Hermes/OpenClaw 发布由 skill-manager 管理 |
| personal-web/backend/rss-relay/src/endpoints.py，PostRequest/create_post | 五字段，没有幂等键；每次新建 id；未知频道 422、停用频道 409；返回 detail_url |
| personal-web/backend/rss-relay/src/endpoints.py，list_posts_json/get_post | 最多 200 篇、无分页，完整正文可读回 |
| personal-web/backend/rss-relay/config/app.yaml | retention_days=15 |
| skills/finance-macro/a-share-macro-impact-skill/scripts/push_rss.py | 标准库 HTTP、同标题查重，还包含业务 validator 和看板同步 |
| skills/bilibili-subtitle-rss/scripts/subtitle_rss.py，publish_post/request_json | 已有本地回执、远端查重及 HTTP 实现，可作试点；实际函数名以源码为准 |
| skills/waytoagi-update-log/SKILL.md | mention-doc token 与多渠道回执逻辑 |
| skills/hk-ipo-research/SKILL.md；skills/hk-ipo-backtest/SKILL.md | 每日招股窗口研究与首日成熟案例回测，发布时机属业务层 |
| daily-review/daily_review.py，rss_push | workreport 频道；调度和 --push 留在业务层 |
| stock-info-dingding/xwlb_to_rss.py | 昨日新闻摘要、默认 dry-run、xinwen 频道 |
| skills/finance-macro/csi300-brief/SKILL.md | 只读生成简况，定时和投递由调用方负责 |

设计中的 CLI、状态码、新目录均未实现。后续实施前重读最新源码，不能把规划当既有能力。
