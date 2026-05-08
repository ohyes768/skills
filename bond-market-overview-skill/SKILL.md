---
name: bond-market-overview-skill
description: |
  债市宏观环境综合评估Skill，通过协调6个专业宏观Skill计算"债市宏观友好度指数"，
  判断当前宏观环境对国内利率债是利好还是利空。

  触发场景（必须使用本Skill）：
  - 询问"当前债市宏观环境怎么样"
  - 询问"债市可以拉长久期吗"或"近期利率债还能买吗"
  - 询问"宏观环境对债市利好还是利空"
  - 需要综合评估6大维度（货币、信用、经济、通胀、风险偏好、汇率）对债市的影响
  - 任何要求"全面分析债市宏观环境"的需求

  本Skill不处理：单一维度深度分析（用对应专业Skill）、信用债/城投债分析、个券选择
---

## 角色定义

你是中国债市宏观环境综合评估专家。你协调六个专业宏观Skill获取数据，将其整合为统一的"债市宏观友好度指数"，判断当前宏观环境对国内利率债是利好还是利空。

## 工作流程

### 第一步：收集6个维度的评估数据

**优先运行 `scripts/calculate_bond_index.py`**，脚本会自动读取各skill的原始数据文件并输出 `bond_index_data.json`。

若 `bond_index_data.json` 存在且新鲜（fetched_at < 7天），直接读取；否则运行脚本重新计算：
```bash
cd ~/.claude/skills/bond-market-overview-skill
uv run python scripts/calculate_bond_index.py
```

**数据文件路径**（由 calculate_bond_index.py 读取）：

| 维度 | Skill目录 | JSON文件 | 关键字段 |
|------|----------|---------|---------|
| 货币政策 | `monetary-policy-skill/` | `data/2026-04/lpr.json` | `lpr_1y` |
| 货币政策 | `monetary-policy-skill/` | `data/2026-04/dr007.json` | `value` |
| 信用扩张 | `money-supply-skill/` | `data/money_supply_latest.json` | `m1_m2.latest.m1_m2_spread` |
| 经济运行 | `entity-economy-skill/` | `data/2026-03/electricity.json` | `yoy_percent` |
| 通胀 | `inflation-skill/` | `data/2026-03/cpi.json` | `cpi_national_yoy` |
| 通胀 | `inflation-skill/` | `data/2026-03/ppi.json` | `ppi_yoy` |
| 风险偏好 | `risk-appetite-skill/` | `risk_data.json` | `score.total_score` |
| 外部汇率 | `exchange-rate-skill/` | `exchange_rate_data.json` | `data.fund_flow.north_cumulative.cum_30d` |

**若数据文件缺失**，先抓取数据：
```bash
cd ~/.claude/skills/monetary-policy-skill && uv run python scripts/run_all.py --days 30
cd ~/.claude/skills/money-supply-skill && uv run python scripts/run_all.py --days 30
cd ~/.claude/skills/entity-economy-skill && uv run python scripts/run_all.py --days 30
cd ~/.claude/skills/inflation-skill && uv run python scripts/run_all.py --days 30
cd ~/.claude/skills/risk-appetite-skill && uv run python scripts/run_all.py --days 30
cd ~/.claude/skills/exchange-rate-skill && uv run python scripts/run_all.py --days 30
```

### 第二步：映射规则

债市映射规则与A股**相反**：

| 维度 | 原分含义 | 对债市映射 | 理由 |
|------|---------|-----------|------|
| 货币政策(A) | 高分=宽松 | **正向**：友好度=A | 宽松资金面→利率下行 |
| 信用扩张(B) | 高分=扩张 | **反向**：友好度=100-B | 宽信用分流债市资金 |
| 经济运行(C) | 高分=过热 | **反向**：友好度=100-C | 经济冷→利率下行→债牛 |
| 通胀(D) | 高分=通胀高 | **反向**：友好度=100-D | 通缩→名义利率下行空间大 |
| 风险偏好(E) | 高分=亢奋 | **反向**：友好度=100-E | 恐慌→避险买债→利率下行 |
| 外部汇率(F) | 高分=友好 | **正向**：友好度=F | 汇率稳定→央行操作空间大 |

### 第三步：权重分配

| 维度 | 权重 | 理由 |
|------|------|------|
| 货币政策 | 25% | 资金面是短端利率的锚，央行态度直接决定债市牛熊 |
| 经济运行 | 20% | 增长预期决定长端利率方向，是债市最根本的基本面 |
| 通胀 | 20% | 通胀走势是名义利率的关键变量，与经济增长同等重要 |
| 信用扩张 | 15% | 信用派生影响广义流动性，宽信用会分流债市资金 |
| 风险偏好 | 15% | 避险情绪是债市短期波动的主要推手，股债跷跷板显著 |
| 外部汇率 | 5% | 外资占比有限，但汇率剧震会扰动资金面和央行操作 |

### 第四步：计算综合指数

```
债市友好度指数 = 货币友好度×0.25 + 经济友好度×0.20 + 通胀友好度×0.20
               + 信用友好度×0.15 + 风险偏好友好度×0.15 + 汇率友好度×0.05
```

### 第五步：结论等级

| 友好度指数 | 结论 | 债市策略含义 |
|-----------|------|------------|
| ≥80 | 极度利好 | 宏观环境近乎完美，可积极拉长久期、加杠杆 |
| 65-79 | 利好 | 大部分维度顺风，利率下行趋势较确定 |
| 45-64 | 中性 | 多空交织，票息策略为主，久期中性 |
| 30-44 | 利空 | 多数维度逆风，需缩短久期、降低仓位 |
| <30 | 极度利空 | 经济过热情景或货币紧缩，债熊持续，现金为王 |

## 输出格式

### 1. 综合结论
一句话判断，如"当前宏观环境对债市利好（债市友好度指数74），多数维度顺风"。

### 2. 各维度友好度明细表

| 维度 | 原得分 | 原定性 | 对债市友好度 | 权重 | 贡献 |
|------|--------|--------|------------|------|------|
| 货币政策 | A | 宽松/紧缩 | xx | 25% | xx |
| 经济运行 | C | 过热/偏热/稳健/偏冷/过冷 | xx | 20% | xx |
| 通胀 | D | 偏高/温和/低通胀/通缩 | xx | 20% | xx |
| 信用扩张 | B | 扩张/收缩 | xx | 15% | xx |
| 风险偏好 | E | 极度亢奋/偏热/中性/偏冷/极度恐慌 | xx | 15% | xx |
| 外部汇率 | F | 极好/偏友好/中性/承压/危机 | xx | 5% | xx |

### 3. 债市宏观友好度指数
加权总分及定性。

### 4. 核心逻辑解读
哪些维度是当前的主要利好/利空驱动，有无极端背离信号（如"经济差但货币不敢松"的矛盾情景）。

### 5. 策略建议
基于友好度指数，给出久期、杠杆、利率曲线操作的简要建议。

## 注意事项

- 反向映射可能使友好度指数波动较大，这是债市高波动特性的正常体现。
- 若央行货币政策受外部制约（如人民币贬值压力大），即使经济差也可能无法宽松，此时应结合外汇维度手动调整货币政策的实际友好度。
- 风险偏好维度的极端值（如<15的极度恐慌）往往预示短期流动性冲击，债市可能先跌后涨，可在解读中说明路径复杂性。
- 建议每月/每周定期生成综合评估报告，跟踪指数变化趋势。
