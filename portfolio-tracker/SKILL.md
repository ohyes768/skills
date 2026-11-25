---
name: portfolio-tracker
description: 个人理财产品持仓管理。Use when user wants 查看当前持仓收益、买入新理财记账、赎回到期理财、到期提醒、持仓产品净值更新。数据源为各管理人官网接口（兴银/信银/光大/杭银/招银），自动拉最新净值计算收益率/年化/回撤/Sharpe。
---

# 个人理财产品持仓管理

**一句话：买入记账 → 日常看收益 → 到期赎回销账，完整生命周期。**

持仓配置在 `scripts/data/holdings.json`，净值缓存在 `scripts/data/`（CSV per code）。

依赖：`numpy`、`cryptography`（信银 legacy SSL + 中国理财网签名）。

---

## 快速上手

```bash
cd scripts/

# 查看当前持仓速览（自动拉最新净值，按近3月年化排序）
python3 portfolio.py

# 用本地缓存（不刷新净值）
python3 portfolio.py --no-refresh
```

输出每只持仓的：持有信息（总收益率、持有年化、近1月/近3月年化）+ 产品指标（风险等级、成立时长、近6月年化、成立年化、最大回撤、成立/近1年Sharpe）。不显示本金、市值与收益金额。

---

## 买入记账

```bash
python3 portfolio.py --buy <代码> --shares <份额> --principal <本金> --date <买入日期>
# 示例：
python3 portfolio.py --buy 120084A --shares 50000 --principal 50000 --date 2026-12-01
python3 portfolio.py --buy AF268304S --shares 30000 --principal 30000 --date 2026-12-15
```

自动写入 `data/holdings.json` 并拉取该产品历史净值缓存。

## 赎回/到期销账

```bash
python3 portfolio.py --redeem <代码> --date <赎回日期>
# 示例：
python3 portfolio.py --redeem TYG3M1906 --date 2026-12-23
```

标记为已赎回（移入 `data/redeemed.json` 保留历史），从当前持仓列表移除。

## 到期提醒

```bash
python3 portfolio.py --expiring 30    # 未来30天内到期/开放的产品
python3 portfolio.py --expiring 7     # 未来7天内
```

按持仓产品的 endDate/开放日期筛选，列出即将到期/可赎回的产品及当前收益率。

---

## 数据文件

| 文件 | 用途 |
|---|---|
| `data/holdings.json` | 当前持仓 {代码: {shares, principal, buy_date}} |
| `data/redeemed.json` | 已赎回历史 {代码: {shares, principal, buy_date, redeem_date, redeem_nav}} |
| `data/<CODE>.csv` | 净值缓存 (date,nav)，portfolio.py 自动维护 |

## 净值拉取

`fetch_nav_history.py` 自动识别代码类型：
- 招银自营（4-6位数字，如 120084A）→ cfweb SM4 签名
- 杭银自营（TYG/JQB/HYG）→ hzbankwealth.cn JSON
- 信银理财（AF/BF）→ wechat.citic-wealth.com（需 legacy SSL）
- 光大理财（GD）→ 招行 cfweb
- 兴银理财（XY）→ 招行 cfweb

其他管理人（南银/民生/华夏）需手动从 `bank-wealth-screening` skill 的脚本拉取后放入 `data/` 目录。

---

## 与 bank-wealth-screening skill 的关系

| | bank-wealth-screening | portfolio-tracker |
|---|---|---|
| 定位 | **发现**：筛在售→推荐→拉净值 | **管理**：持仓速览→买卖记账→到期提醒 |
| 输入 | 筛选条件（风险/期限/管理人） | 持仓配置（holdings.json） |
| 输出 | 候选清单 + 推荐理由 | 持仓收益 + 到期提醒 |

典型的组合使用：先在 bank-wealth-screening 里筛+推荐，买入后用 portfolio-tracker 记账跟踪。

---

## 业绩指标门槛

| 指标 | 最低门槛 | 勉强可信 |
|---|---|---|
| 成立年化 | 3个月 | 6个月+ |
| 最大回撤 | 6个月 | 1年 |
| Sharpe | 1年 | 2年+ |
