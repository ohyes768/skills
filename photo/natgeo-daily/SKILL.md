# natgeo-daily 国家地理每日一图

每日抓取 National Geographic Photo of the Day，翻译描述并推送钉钉。

## 工作流程

1. 运行脚本（自动：抓页面 → 提取 OG 数据 → LLM 翻译描述 → 推钉钉 → 落 JSON）：

```bash
python3 /home/ohyes768/skills/photo/natgeo-daily/scripts/natgeo_daily.py
```

2. 向调用方汇报：标题 / 摄影师 / 中文摘要一句 / 是否推送成功。
3. 脚本退出码：0=成功；2=当日照片提取失败；3=钉钉推送被拒；5=投递结果未知；4=其他异常。非 0 时原样转述 stderr。

## 说明

- 翻译：优先脚本内置 DeepSeek（env `DEEPSEEK_API_KEY`）；Hermes 会话内运行时若无 key，直接由你翻译描述后写入即可——但**不要**为翻译重跑脚本。
- 钉钉推送走**公共 dingtalk-push CLI**（`personal-tools/dingtalk-push`），脚本自身不做 HTTP 发送。回执与去重由 CLI 负责：
  - 同内容再推 → `duplicate`（按回执跳过，**不会**出现第二条相同消息）；
  - 超时/5xx/响应不可解析 → `unknown`（**可能已送达**，不自动重发）；
  - 机器人明确拒绝（关键词不匹配等）→ `failed`。
- **退出码 5 = 投递结果未知**：消息可能已经在群里了。先核对群消息，**不要**重跑脚本、不要重发同一条。
- 群机器人安全设置必须是「自定义关键词」（关键词：`国家地理`）。公共 CLI 不做加签，脚本在检测到 `NATGEO_DINGTALK_SECRET` 时会直接失败并提示。
- 摄影师提取三处来源（优先级从高到低）：og:description 正文里的 `Photograph by X` / `photographer X` → 独立图注 `span.RichText Caption__Credit` → 主图 JSON 的 `crdt` 字段。图注里的机构名（`National Geographic Pristine Seas`）会剔除，短资质后缀（`MoCP`）保留。
- 调度：由 task-web（personal-web）统一触发；本 skill 不自带 cron。

## 测试

```bash
cd /home/ohyes768/skills/photo/natgeo-daily && python3 -m unittest discover -s tests
```

纯 stdlib unittest（无 pytest 依赖），覆盖摄影师提取（含图注/JSON 兜底）与推送状态映射（sent/duplicate/unknown/failed）两组历史缺陷。
