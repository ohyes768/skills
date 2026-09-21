# 来源与改造说明

## 上游项目

- `Marvae/hk-ipo-research-assistant`：复制 `scripts/` 与原始参考资料，作为可执行抓取与分析底座。上游许可证保存在 `../LICENSE.marvae.txt`。
- `LI-Jialu/hk-ipo-skill`（原链接会重定向）：采用实时抓取、多源交叉验证、评分、排除项与历史复盘设计；复制并保留评分和数据源参考。上游许可证保存在 `../LICENSE.caroline.txt`。
- `stock-info-dingding/hk_stock_push.py`：借鉴新浪港股 IPO 列表的表格解析、日期范围筛选及五位股票代码发现流程；未复制钉钉推送耦合。

## 合并原则

- 以脚本输出提供事实，以 agent 工作流完成核验、解释和评分。
- 把预测、最终配售和上市后结果分开，避免时间穿越。
- 对缺失、冲突和单一来源数据显式降置信度。
- 保持 OpenClaw/Hermes 常见的 `SKILL.md + scripts + references` 自包含目录结构。
