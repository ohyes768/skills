# 数据源、接口细节与数据坑

## 各管理人净值接口对照

用杭行/招行货架上的产品名去各管理人官网搜索匹配代码，再拉净值。

| 管理人 | 脚本 | 接口域名 | 结构化净值 | 签名/特殊 |
|---|---|---|---|---|
| 招银自营 | `fetch_nav_history.py` | cfweb.paas.cmbchina.com | ✅ | SM4 签名（gmssl） |
| 杭银自营 | `fetch_nav_history.py` | hzbankwealth.cn JSON | ✅ | 无（⚠️ 官网证书域名不匹配，需 unverified context） |
| 兴银理财 | `xy_fetch.py` | cibwm.com.cn `/api/public/pc/productVal/performanceTrend/<code>/SINCE` | ✅ | 无。⚠️货币型产品净值恒 1，须读 `sevenDayAnnualized` 字段（**单位是百分数数值**，0.8926 = 0.8926%，与民生/信银的小数口径不同，需 /100） |
| 信银理财 | `citic_fetch.py` | wechat.citic-wealth.com `getTAProductNav` | ✅ | TLS legacy renegotiation（`ctx.options\|=0x4`） |
| 光大理财 | `ceb_fetch.py` | 95595.com.cn `getLsjz.portlet` | ✅ | 无；⚠️仅覆盖母行100只，专款不在内 |
| 民生理财 | `ms_nav_fetch.py` | cmbcwm.com.cn `BTADailyQry`（form-urlencoded） | ✅ | 无；先 `BTAProductQry` 按名称搜 REAL_PRD_CODE |
| 南银理财 | `ny_nav_fetch.py` | nanyinwealth.com `queryNetValueList.portlet` | ✅ | AES-128-ECB + RSA PKCS1v1.5；⚠️偶发失败需重试（~30%）；⚠️timeStamp 也是AES加密的 |
| 华夏理财 | `hx_fetch.py` | hxwm.com.cn `gmjzbgData.js` + 静态报告 js | ✅ | 无；10153份报告，6092只产品 |
| 中银理财 | `boc_fetch.py` | bankofchina.com 静态 JSON→详情页 | ✅ | 无 |

### 关键签名/协议细节

- **招行 SM4**（cfweb，招银自营+光大/兴银/信银代销共用）：
  `appId="LB50.22_CFWebUI"`；`signature = base64(SM4-ECB(key="9qwBGju73JAXid48", data="LB50.22_CFWebUI|<毫秒时间戳>"))`；headers 带 appId、timespan、signature、`X-B3-BusinessId: LB502215022970`。
- **信银 TLS**：wechat.citic-wealth.com 要求 UnsafeLegacyRenegotiation：Python `ctx.options |= 0x4`，curl 加 `--ciphers DEFAULT@SECLEVEL=1`。
- **民生 kType**（QryFinSamInfoByCode.do）：1=发行公告 2=净值公告 3=(空) 4/5=其他 6=到期。
- **兴银按名称搜代码**：POST `cibwm.com.cn/api/public/pc/productInfo/getProdInfoByPage`，body 里 `fuzzyStr` 放产品名。
- **信银按名称搜代码**：`wechat.citic-wealth.com/cms.product/api/custom/productInfo/search?key=<名称>`（走上面的 legacy TLS）。

### 使用示例

```bash
cd scripts/
python3 ms_nav_fetch.py FBAF19240F     # 民生：按 real_prd_code
python3 ms_nav_fetch.py --name "天天增利"  # 民生：按名称搜索再拉
python3 ny_nav_fetch.py Z70021 Z99002  # 南银（偶发失败重试即可）
python3 hx_fetch.py                    # 华夏全量跑批（较慢，8499只）
```

## 净值缓存深度对照（决定哪个系列能用历史业绩验证）

| 通道（fetcher 输出） | 历史深度 | 说明 |
|---|---|---|
| hx（华夏） | **全历史**（数百点/支） | 净值报告 JSON，最可靠 |
| xy（兴银） | 全历史（700+ 点） | `adjustedValue` 复权净值 |
| cmb / hzbank CSV | 全历史 | 招银/杭银自营 |
| citic（信银） | **仅 ~31 点**（1 个月） | wechat 接口只回近月，深历史拿不到 |
| ny（南银） | **仅 ~58 点**（约 2 个月） | 只够算近期年化，不能验证长期 |
| ms（民生） | 无结构化历史 | 仅最新净值+公告 PDF 链接 |
| ceb（光大） | 仅母行 100 只 | 专款（杭行74只）不在内 |
| boc（中银） | rows 多为空 | 静态页无结构化数据 |

## 各管理人官网的数据坑（2026-11-26 实测）

| 坑 | 现象 | 后果 |
|---|---|---|
| **华夏 rows 倒序** | `hx_fetch.py` 返回的 `rows` 最新在前（400/400 抽样确认） | 直接喂 `nav_stats` 抛 `math domain error`；若被 try/except 吞掉则**所有华夏参照静默失效、零报错** |
| 兴银 rows 正序 | `xy_fetch.py` 的 rows 时间正序 | 无需排序 |
| 日期字段名各家不同 | 华夏 `netValueDate`／兴银 `netvalDt`+`dataDt`／信银 `navDate` | 解析时必须逐家兼容 |
| 净值字段名各家不同 | 华夏 `shareNetVal`／兴银 `adjustedValue`／信银 `nav` | 同上 |
| 兴银封闭式当期无净值 | `稳利安盈封闭式2026年665期` 的 rows=0 | 须回溯同产品线的**早期次**（如 2023年231期，1077 天历史） |
| 兴银产品名带期号 | 官网 `稳利安盈封闭式2023年231期固收类理财产品` vs 招行 `稳利安盈封闭式2026年665期F` | 按期号匹配必然落空，须去期号/年份/份额字母/通用后缀后按**产品线**归组 |
| 杭银官网证书 | www.hzbankwealth.cn 证书域名不匹配 | Python 用 unverified context（fetcher/脚本已内置） |

## 万份收益型（现金管理类）的业绩口径

货币型/现金管理类产品**净值恒为 1.0**，用净值序列算年化一律得到 0，**不能当"零收益"报给用户**。正确口径是七日年化：

| 管理人 | 字段/接口 | 单位 | 备注 |
|---|---|---|---|
| 民生 | `BTADailyQry` → `WEEK_CLIENTRATE` | **小数**（0.0084 = 0.84%） | 本身即七日年化率，勿再复利 52 次。接口用 `'-'` 表示当日无数据 |
| 兴银 | `performanceTrend` → `sevenDayAnnualized` | **百分数数值**（0.8926 = 0.8926%） | 需 `/100` 归一。同响应里 `effIopv`=万份收益、`effTotNetVal` 可交叉验证 |
| 信银 | `productInfo/search` → `sevenDaysIncomeRate` / `totalYearIncomeRate` | **小数** | 匹配须用 **(期号, 份额尾字母, 代销含"招商银行")** 三重条件，只按期号会串份额 |

- **匹配键**：招行货架的代销产品名尾字母 = 管理人官网的份额代码尾字母（例：招行 `ZX100018`=日盈象天天利816号M → 信银 `AM264385M`）。
- **民生/信银的招行渠道专属份额在管理人官网零售检索里查不到**（如 268/294/125/126 号），只能退到同系列老份额（FSAF18178A 天天增利、FBAE68001A 贵竹天天盈1号）作参照。
- **实测同类区间**：120 只万份收益型七日年化 **+0.77% ~ +2.17%**，均值 **+1.13%**。拿不到直连接口的产品可用此区间做"同类基准"，但必须标明是参考区间而非该产品实绩。
- **无直连路径**：宁银官网 DNS 不通；中银理财官网被 Cloudflare 挡；平安官网理财页 404。

## 招行货架补充规则

- **全量目录**：`on_sale_cmb.py` 的 `fetch_all()` 只拿到 770 只（pageSize 被服务端钳到 10 + 翻页限频），全量抓取用 `scripts/fetch_cmb_catalog.py`（并行+退避，实测 7687/7689 只）；全量筛选用 `screen_cmb_full.py`，报告用 `report_cmb_full.py`。
- **私行/私募份额排除**：私行与零售共享同一登记编码，只有 `prdCode` 字母段不同（`120084A` 零售 vs `PB120084` 私行尊享；`JYPB0123` = JY+PB+0123）。**代码里含独立 `PB` 或 `PW` 段即私行/私募**；定向份额以 `D` 结尾（`NBD`/`JXD`/`BYD`/`NYD`/`ZYD`）或名称含"定向"。

## 退役与不可用数据源

- **中国理财网（chinawealth.com.cn）：已退役，勿再使用**。2026-11-24 实测 `prod/search` 返回二次校验错误，RSA+AES 签名流程整体失效，**不是限频，重试无意义**。
- **无直连数据源的管理人**（建信/中邮/工银/浦银/交银/平安/宁银/北银等）：业绩不可验证，推荐时明确标注"无业绩可参照、盲买管理人"，不要凭列表信息推荐。
- **光大专款**（杭行74只/招行20只）：cebwm.com 有瑞数反爬，脚本化不可行；用同系列公开份额参照。
- **华夏银行自营 164 只**（杭行货架）：全部"到期"状态，2026 底清理，无需关注。

## 数据缓存位置

```
scripts/data/nav_history/     招银+杭银自营净值 CSV（fetch_nav_history.py / nav_stats.py 共用）
scripts/data/hzb_catalog.json  杭银全量目录缓存（hz_ref_match.py，TTL 6小时，--refresh 强制重拉）
```

第三方管理人研究期缓存曾在 `~/study/nav/`，2026-11-25 已删除；需要时用对应 fetcher 重新抓取。招行/杭行代销清单用 `on_sale_cmb.py`/`on_sale_hzbank.py` 实时查询，不依赖本地缓存。
