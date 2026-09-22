# 宏观 Skill 下线设计

## 目标

从本仓库移除已由 Web 服务承担的四个宏观 Skill，并保留 A 股与债市综合判断模型，供后续重建或调整使用。

## 范围

删除以下目录及其测试、抓取、上传实现：

- `finance-macro/exchange-rate-skill`
- `finance-macro/risk-appetite-skill`
- `finance-macro/a-share-macro-skill`
- `finance-macro/bond-market-overview-skill`

同步从技能注册表、仓库 README、技能矩阵和剩余宏观 skill 的过时交叉引用中清理上述名称。

## 保留的模型文档

在 `finance-macro/ARCHIVED_MACRO_DECISION_LOGIC.md` 中归档两套综合模型：A 股宏观友好度与债市宏观友好度。文档保留维度、权重、评分方向、数据时效规则、缺失数据行为、输出字段和市场情绪的独立处理方式；不会保留任何可执行抓取或推送代码。

## 兼容性

清理后，仓库仅保留四个推送至 Web 服务的核心宏观 Skill：`monetary-policy-skill`、`money-supply-skill`、`entity-economy-skill` 与 `inflation-skill`。移除的综合索引命令不再可用；其原始逻辑只在归档文档中保留。

## 验证

使用全文搜索确认无活动配置、代码、测试或文档引用被删除的四个 skill；对仍保留的四个 skill 的 Python 源码做编译检查，并确认注册表只包含这四个独立宏观数据 skill。
