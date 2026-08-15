---
name: a-share-macro-skill
description: A股宏观环境综合分析 skill。用于判断当前宏观环境对 A 股是偏利好、偏中性还是偏不利，并把核心宏观底色与短期市场情绪分开表达。触发场景包括：询问“A股宏观环境怎么样”“宏观是否利好A股”“本周A股大环境变好还是变差”“风险偏好是否过热”“是否适合加仓或减仓但需要宏观背景”。必须先检查数据质量；关键数据缺失、过期或没有评分时，不得给出利好/不利结论。
---

# A股宏观环境综合分析

## 核心原则

不要把缺失数据当作中性数据。只要核心宏观数据缺失、过期、读取失败或没有明确评分，就输出“本周判断不可用”，并说明原因。

不要只给一个“A股利好分”。最终表达必须分三层：

1. 数据是否可靠
2. 核心宏观底色
3. 短期市场情绪

推荐表达：

```text
宏观底色：偏利好
短期情绪：偏热
综合判断：中期环境改善，但短期追高风险上升
```

## 工作流程

### 1. 更新子模块数据

优先运行各子 skill 的数据脚本，确保数据尽量新。

```powershell
cd F:\personal-projects\macro-fin-skill\skills\exchange-rate-skill
uv run python scripts\run_all.py --days 30

cd F:\personal-projects\macro-fin-skill\skills\risk-appetite-skill
uv run python scripts\run_all.py --days 30

cd F:\personal-projects\macro-fin-skill\skills\money-supply-skill
uv run python scripts\run_all.py --days 30

cd F:\personal-projects\macro-fin-skill\skills\monetary-policy-skill
uv run python scripts\run_all.py --days 30

cd F:\personal-projects\macro-fin-skill\skills\entity-economy-skill
uv run python scripts\run_all.py --days 30

cd F:\personal-projects\macro-fin-skill\skills\inflation-skill
uv run python scripts\run_all.py --days 30
```

如果某个子模块运行失败，要把失败写入最终报告，不要用默认分数替代。

### 2. 要求统一输出格式

每个子 skill 最好输出自己的 `macro_signal.json`，放在统一输出目录 `finance-macro/output/<skill 目录名>/`。

格式：

```json
{
  "dimension": "money_supply",
  "score": 70,
  "conclusion": "信用扩张",
  "data_date": "2026-05-20",
  "errors": []
}
```

字段要求：

- `dimension`：维度名称
- `score`：0-100 分，必须是真实计算结果
- `conclusion`：简短定性结论
- `data_date`：数据日期，必须能判断是否过期
- `errors`：抓取或计算错误，没有错误时为空数组

不得输出“缺数据但 score=50”的结果。

### 3. 运行总分析

在本 skill 目录运行：

```powershell
cd F:\personal-projects\macro-fin-skill\skills\a-share-macro-skill
python scripts\generate_macro_signals.py
python scripts\calculate_macro_index.py
```

结果会写入：

```text
F:\personal-projects\skills\finance-macro\output\a-share-macro-skill\macro_index_data.json
```

运行输出必须先展示 6 个 skill 的详细数据，再展示总结：

```text
=== 宏观数据明细 ===
【货币政策】...
【信用扩张】...
【经济运行】...
【通胀环境】...
【外部压力】...
【市场情绪】...

=== 总结 ===
核心宏观指数：58.14（中性）
短期情绪：偏热
综合判断：多空交织，等待更明确的宏观方向。
```

## 三层判断规则

### 第一层：数据质量

核心宏观维度包括：

- 货币政策
- 信用扩张
- 经济运行
- 通胀环境
- 外部压力

只要上述任一维度缺失、过期、读取失败或没有明确评分，本周判断不可用。

市场情绪是短期修正项。它缺失时，可以继续判断核心宏观，但必须提示“短期情绪不可用”。

### 第二层：核心宏观底色

核心宏观指数只包含：

| 维度 | 权重 |
|---|---:|
| 货币政策 | 20% |
| 信用扩张 | 20% |
| 经济运行 | 25% |
| 通胀环境 | 15% |
| 外部压力 | 20% |

风险偏好不进入核心宏观指数。

经济运行和通胀采用平滑的倒 U 型映射，避免分数在边界附近突然大幅跳变。

宏观底色分档：

| 分数 | 结论 |
|---:|---|
| 80 以上 | 明显利好 |
| 65-79 | 偏利好 |
| 45-64 | 中性 |
| 30-44 | 偏不利 |
| 30 以下 | 明显不利 |

### 第三层：短期市场情绪

风险偏好只作为短期温度计：

| 风险偏好分数 | 情绪 |
|---:|---|
| 85 以上 | 过热 |
| 70-84 | 偏热 |
| 45-69 | 正常 |
| 25-44 | 偏冷 |
| 25 以下 | 恐慌 |

情绪过热不等于更利好，必须提示短期回撤风险。情绪偏冷或恐慌也不等于更差，如果宏观底色改善，要提示可能存在左侧机会。

## 输出要求

报告必须包含：

1. 数据质量：哪些维度可用，哪些缺失、过期或报错
2. 六个 skill 的详细数据：货币、信用、经济、通胀、外部压力、市场情绪
3. 宏观底色：核心宏观指数和定性结论
4. 短期情绪：风险偏好温度
5. 综合判断：用自然语言解释“中期环境”和“短期风险”是否一致
6. 主要拖累项和支撑项

如果数据不可用，报告不得出现“友好”“利好”“不利”等最终判断，只能说明“本周判断不可用”及原因。

## 飞书通知

如果需要发送飞书通知，只发送已经通过数据质量检查的结论。若判断不可用，通知内容应优先列出缺失和错误原因。
