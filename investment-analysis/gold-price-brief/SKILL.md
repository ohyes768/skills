---
name: gold-price-brief
description: 黄金走势每日研判播报 skill。每日取国内金价/伦敦金/SPDR 持仓/美联储利率预期/RSI 实时数据，生成走势研判并推送钉钉。由 task-web 定时触发；数据获取失败时明确失败不推送。不适用于实盘下单或杠杆交易建议。
---

# 黄金走势研判播报

数据一律来自取数脚本实时返回，禁止凭模型记忆回答价格类事实；缺失字段保留"资料不足"，不估算、不切换数据源。默认中文输出，注明数据时间（Asia/Shanghai）。结论仅供研究参考。

Canonical source：本包。迁移自 `stock-info-dingding/gold_price_push.py`（2026-11-07）；旧入口在调度切换完成前保留兼容，两处不得各自独立演进。

## 流程

1. **取数**（失败即中止，不推送、不做分析）：

```bash
python3 <skill-dir>/scripts/gold_price_push.py fetch > /tmp/gold-data-$(date +%Y%m%d-%H%M).json
```

检查退出码为 0 且 JSON 非空；非 0 时直接以失败结束并说明 stderr 内容。

2. **研判**：读取该 JSON，基于以下事实生成研判（事实部分照抄 JSON 数值，带单位与日期）：
   - 当前金价（元/克）、五日/区间涨跌、MA5/MA20 位置关系
   - RSI(14) 三个口径（gold_rsi_14 / simple_rsi_14 / ali_rsi_14）
   - SPDR 持仓及近一日变动（吨）
   - 美联储利率预期（各会议 hold/hike 分布与方向变化）
   - 结论段：偏多/偏空/震荡 判断 + 一句话理由；风险提示一句。不编造 JSON 之外的事实。

3. **落盘**：研判 Markdown 写入 `/tmp/gold-analysis-<同批次时间戳>.md`。

4. **推送**（真实外发，PUSH_MODE=1 才发送）：

```bash
PUSH_MODE=1 python3 <skill-dir>/scripts/gold_price_push.py push <数据JSON路径> <研判md路径>
```

检查退出码与 stdout（"推送成功!"）；失败时如实报告 stderr，不得重试超过一次，不得声称已送达。不带 `PUSH_MODE=1` 时为测试模式：只打印将发送的 Markdown，不发起任何网络发送。

## 配置

webhook 是群机器人唯一凭据，只放 `.env`（已被 gitignore 排除）或调度环境变量，不进代码与日志。参见 [.env.example](.env.example)：

| 变量 | 说明 |
|---|---|
| `GOLD_DINGTALK_WEBHOOK` | 群机器人 Webhook 完整地址（含 access_token），缺失时推送失败 |
| `GOLD_DINGTALK_SECRET` | 加签密钥；机器人开启「加签」时必填，脚本自行 HMAC 加签 |
| `GOLD_FED_CACHE_PATH` | 金十利率预期缓存位置，默认 `<skill>/data/gold_fed_expectations.json` |
| `DEEPSEEK_API_KEY` | 仅旧版一条龙模式使用；现行两段式无需 |

发送实现保留在本包 `scripts/gold/pusher.py`（含加签）。公共 `dingtalk-push` CLI 目前不支持加签，故暂不接入；待公共 CLI 支持加签后再统一切换。

## 边界

- 不得修改本 SKILL.md，不得改动调用方调度配置；研判正文由模型生成，脚本不改写。
- 输出摘要：最终回复只写研判要点两三句 + 推送结果，不要粘贴全文。
- 金十利率预期的口径、缓存与降级规则见 [references/gold-fed-expectations.md](references/gold-fed-expectations.md)；离线排版样例见 [references/preview-sample.md](references/preview-sample.md)。
- 调度：由 task-web（hermes_trigger → Runs API）统一触发；本 skill 不自带 cron。
