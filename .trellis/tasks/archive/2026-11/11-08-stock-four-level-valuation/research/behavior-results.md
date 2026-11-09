# 有 Skill 行为复测

2026-11-09；agent `79299445-7932-4b87-833d-d40b5591741a`，只读 [SKILL.md](../../../investment-analysis/stock-four-level-valuation/SKILL.md) 与三个 references，未读基线文件、未联网、未用CLI。场景与基线完全一致（[scenarios.md](scenarios.md)）。

## 结果

| 场景 | status | 四点 | 关键行为 |
|---|---|---|---|
| A | insufficient_data | 全null | 不映射评分到PE；2025 EPS≠TTM；特别分红单列；披露日缺失按实质更新缺口处理，不机械90天过期 |
| B | insufficient_data | 全null | 拒绝把未核实BVPS当普通股PB锚；银行资本/资产质量缺口阻止ready；缺失≠已恶化，未误判blocked |
| C | insufficient_data | 全null | 拒绝39.93×{0.6,0.8,1,1.2}，也拒绝折现后乘比例；条件式现值32.49只留在分析文字，指出终期除息歧义，不进计算节点 |

三场景 confidence=unavailable，理由均为无法形成有证据支持的四点，不是判断公司差。A/B 保留可算对照（payout比率等）但明确非覆盖证明。正文无暗藏参考四点。

## 与基线对比

| 场景 | 无 Skill | 有 Skill |
|---|---|---|
| A | 通过（本来就不出价） | 保持通过 |
| B | 通过 | 保持通过 |
| C | 失败：现值×{0.6,0.8,1,1.2}出四个价 | 修复：拒绝机械比例，正式状态不足 |

核心失败模式（“算得出就先给观察线+免责声明”）已被 Skill 规则阻止。

## 复测发现的合同缺口（已修复）

内联材料的 evidence.origin 无合法写法。修复：[output-contract.md](../../../investment-analysis/stock-four-level-valuation/references/output-contract.md) 与 [input-and-reuse.md](../../../investment-analysis/stock-four-level-valuation/references/input-and-reuse.md) 规定内联材料 origin=`inline:<日期>:<简短描述>`，不造URL/路径。

## 边界

本次为只读行为测试，未运行 finalize/check；工具级验证由 CLI 测试承担。行为测试证明的是本组离线场景中的约束有效，不证明真实市场估值正确。
