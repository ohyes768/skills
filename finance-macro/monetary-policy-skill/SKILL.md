---
name: monetary-policy-skill
description: Use when analyzing the People''s Bank of China monetary-policy stance, MLF liquidity operations, or LPR financing costs.
---

# 货币政策分析 Skill

本 skill 依据 MLF 净投放和 LPR 判断中国货币政策的松紧。

## 数据与频率

| 指标 | 含义 | 发布时间 |
|---|---|---|
| MLF 净投放 | 中期流动性 | 每月 2-3 日 |
| 1 年期 LPR | 企业融资成本 | 每月 20 日 |
| 5 年期以上 LPR | 居民中长期融资成本 | 每月 20 日 |

## 使用

```powershell
uv run python scripts/run_all.py --month YYYY-MM
uv run python scripts/run_all.py --upload
```

输出原始数据至 `finance-macro/output/monetary-policy-skill/monetary_indicators_latest.json`；加 `--upload` 会构建并发送 `macro_signal.json`。

## 评分

- MLF 净投放：50%
  - 超过 5,000 亿元：85 分
  - 0 至 5,000 亿元：55 分
  - -1,000 至 0 亿元：40 分
  - 低于 -1,000 亿元：15 分
- LPR：50%
  - 较上月下调：90 分
  - 持平：55 分
  - 上调：15 分

当一个维度缺失时，按剩余可用权重归一化。总分映射为：80+ 明显宽松、60-79 适度宽松、40-59 中性、20-39 适度紧缩、20 以下明显紧缩。

## 推送结构

```json
{
  "conclusion": "适度宽松",
  "data_date": "2026-09-15",
  "total_score": 70.0,
  "details": {
    "mlf_net_yi": 6000,
    "lpr_1y": 3.0,
    "lpr_5y": 3.5
  }
}
```

使用 `MACRO_SIGNAL_UPLOAD_TOKEN`、`MACRO_SIGNAL_UPLOAD_URL` 和可选的 `MACRO_UPLOAD_SSL_VERIFY` 配置上传。上传前脚本会校验结构；后端按顶层 `data_date` 归档月份。