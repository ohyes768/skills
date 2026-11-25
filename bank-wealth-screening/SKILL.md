---
name: bank-wealth-screening
description: 招商银行/杭州银行 自营+代销理财产品筛选与净值分析。Use when user wants 查询招行或杭行能买的理财产品（自营/代销）、按风险等级/持有期限筛选、看历史净值/年化/最大回撤/Sharpe、推荐理财产品。数据源覆盖招银自营(cfweb SM4)、杭银自营+代销(hzbankwealth+ rwpq)、兴银/信银/光大/民生/南银/华夏/中银各理财子官网。
---

# 在售理财筛选与净值分析（招商银行 / 杭州银行）

**入口分两个：招商银行 / 杭州银行。各自再分自营/代销。**

| 银行 | 自营 | 代销第三方 |
|---|---|---|
| 招商银行 | `on_sale_cmb.py`（招银理财） | 官网页架 72 只（光大22/华夏17/民生9/中银8...） |
| 杭州银行 | `on_sale.py`（杭银理财） | rwpq 平台 326 只在售（光大74/华夏51/兴银系80/信银35/南银16/民生2...） |

所有脚本在 `scripts/` 下。依赖：`requests`、`numpy`、`gmssl`（招银 SM4）、`cryptography`（南银/招行 RSA+AES）。

---

## 第一步：筛在售产品

### 招商银行

```bash
# 招银自营（4-6位数字码，代销已默认排除）
python3 scripts/on_sale_cmb.py --retail --risk R1,R2
#   --min-days N  按持有期解析筛选（勿手工文本匹配期限）：
#     持有期优先从产品名解析（「180天持有期」「最低持有360天」）——常开产品 term 字段
#     「365天以上」指产品存续期而非持有期；名称无持有期才回退 term（封闭式 term 即封闭期，
#     「181天-365天」取下界、「365天以上」取 365）；日开/天天/活期/现金管理视为零锁定。
#     期限为「365天以上」的募集期封闭式容易被手工正则漏掉，用 --min-days 可避免。

# 代销第三方（官网公开货架 72 只精选）—— 从缓存 JSON 或重新抓取
# 数据: scripts/data/cmb_daixiao_products.json（132只含招银，剔招银=83只第三方）
```

### 杭州银行

```bash
# 杭银理财自营（窗口开放=今天能买入）
python3 scripts/on_sale.py            # 今天窗口开放的
python3 scripts/on_sale.py --all      # 全部在售状态
python3 scripts/on_sale.py --risk R2

# 代销第三方在售（rwpq 平台，326只在售，剔杭银+招银后约258只）
python3 scripts/on_sale_hzbank.py                     # 全部在售第三方
python3 scripts/on_sale_hzbank.py --risk R2           # 按风险等级
python3 scripts/on_sale_hzbank.py --manager 华夏,信银  # 按管理人关键字
python3 scripts/on_sale_hzbank.py --min-days 30       # 最短持有期≥30天
python3 scripts/on_sale_hzbank.py --json              # JSON输出
```

---

## 第二步：拉历史净值

各管理人净值接口和脚本对照（**用杭行/招行货架上的产品名去各管理人官网搜索匹配代码，再拉净值**）：

| 管理人 | 脚本 | 接口域名 | 结构化净值 | 签名/特殊 |
|---|---|---|---|---|
| 招银自营 | `fetch_nav_history.py` | cfweb.paas.cmbchina.com | ✅ | SM4 签名（gmssl） |
| 杭银自营 | `fetch_nav_history.py` | hzbankwealth.cn JSON | ✅ | 无 |
| 兴银理财 | `xy_fetch.py` | cibwm.com.cn `/api/public/pc/productVal/performanceTrend/<code>/SINCE` | ✅ | 无 |
| 信银理财 | `citic_fetch.py` | wechat.citic-wealth.com `getTAProductNav` | ✅ | TLS legacy renegotiation（`ctx.options\|=0x4`） |
| 光大理财 | `ceb_fetch.py` | 95595.com.cn `getLsjz.portlet` | ✅ | 无；⚠️仅覆盖母行100只，专款不在内 |
| 民生理财 | `ms_nav_fetch.py` | cmbcwm.com.cn `BTADailyQry`（form-urlencoded） | ✅ | 无；先 `BTAProductQry` 按名称搜 REAL_PRD_CODE |
| 南银理财 | `ny_nav_fetch.py` | nanyinwealth.com `queryNetValueList.portlet` | ✅ | AES-128-ECB + RSA PKCS1v1.5；⚠️偶发失败需重试；⚠️timeStamp 也是AES加密的 |
| 华夏理财 | `hx_fetch.py` | hxwm.com.cn `gmjzbgData.js` + 静态报告 js | ✅ | 无；10153份报告，6092只产品 |
| 中银理财 | `boc_fetch.py` | bankofchina.com 静态 JSON→详情页 | ✅ | 无 |

### 使用示例

```bash
cd scripts/

# 兴银：先按杭行产品名搜官网代码，再拉净值
python3 -c "
from xy_fetch import *
import json,urllib.request
UA='Mozilla/5.0'
payload={'page':{'pageNumber':1,'pageSize':5,'orders':[]},
 'pageFilterCriteria':{'preferredTypeKey':[],'riskLevel':[],'productPeriod':[],'productType1':[],'productStatus':[],'productForm':[],'orgType':[],'saleCurrency':[],'distributionChannel':[],'selectionLabel':[],'fuzzyStr':'添利天天利76号'}}
req=urllib.request.Request('https://www.cibwm.com.cn/api/public/pc/productInfo/getProdInfoByPage',data=json.dumps(payload).encode(),method='POST')
req.add_header('User-Agent',UA); req.add_header('Content-Type','application/json')
print(json.load(urllib.request.urlopen(req,timeout=30))['data'])
"

# 信银：名称映射→净值
python3 -c "
import json,urllib.request,ssl,urllib.parse
ctx=ssl.create_default_context(); ctx.options|=0x4
op=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
q=urllib.parse.urlencode({'key':'日盈象天天利321号'})
req=urllib.request.Request(f'https://wechat.citic-wealth.com/cms.product/api/custom/productInfo/search?{q}')
req.add_header('User-Agent','Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)')
print(json.load(op.open(req,timeout=30)))
"

# 民生：结构化历史净值
python3 ms_nav_fetch.py FBAF19240F     # 按 real_prd_code
python3 ms_nav_fetch.py --name "天天增利"  # 按名称搜索再拉

# 南银：结构化历史净值（偶发失败重试即可）
python3 ny_nav_fetch.py Z70021 Z99002

# 华夏：净值报告（全量跑批 8499 只，已抓约3400）
python3 hx_fetch.py                    # 全量（较慢）
# 或者只跑杭行货架优先的
```

### 招行 SM4 签名细节（cfweb，招银自营+光大/兴银/信银代销共用）

```
appId = "LB50.22_CFWebUI"
timespan = 毫秒时间戳
signature = base64( SM4-ECB( key="9qwBGju73JAXid48", data="LB50.22_CFWebUI|<timespan>" ) )
headers: appId, timespan, signature, X-B3-BusinessId: LB502215022970
```

### 民生 kType 对照（QryFinSamInfoByCode.do）

1=发行公告 2=净值公告 3=(空) 4/5=其他 6=到期

### 信银 TLS 注意

wechat.citic-wealth.com 要求 UnsafeLegacyRenegotiation：Python 里 `ctx.options |= 0x4`，curl 加 `--ciphers DEFAULT@SECLEVEL=1`。

---

## 第三步：业绩指标

```bash
python3 nav_stats.py <code> [<code>...]
# 输出: 成立时长、近6月年化、成立年化、最大回撤、成立Sharpe、近1年Sharpe
# 净值缓存写 data/nav_history/<CODE>.csv
```

**T 份额查不到 ≠ 无业绩**：cfweb 对渠道专属 T 份额返回"查无此代码"，但同一产品的 A/B/C/D 份额查得到（例：招睿增利指南针180天持有期1号，108998T 失败、108998A/C 一次命中 142 点）。报"无参照"前先把代码尾缀换成 A/C/D 各试一次。封闭系列新发期（如增鼎封闭11号仅成立 7 天）才算真无参照——用官网详情页/同花顺搜索结果交叉确认最老份额的成立日期再下结论。

`nav_stats.py` 内置统一 loader：招银/杭银 CSV 之外，自动识别 `~/study/nav/` 下 citic/ny/hx/xy 四家的 JSON 格式（深度限制见「已知限制」对照表）；ms/ceb/boc 无结构化历史。

**同系列老份额参照（新份额必做）**：

```bash
python3 series_ref.py <系列关键字> [--top 5] [--min-days 180] [--online-cmb]
# 例: python3 series_ref.py 悦嘉最短持有180天
```

在信银/华夏/南银本地索引 + 招行目录（`--online-cmb`）里搜同系列份额，输出成立最老、有净值数据的参照业绩表。老份额不在任何索引里时（如招行目录只收 770 支自营），用 web 搜索产品全名找老份额代码再喂给 `nav_stats.py`。整个系列查不到 ≥min-days 的份额就明确告知"该系列无业绩可参照"。

---

## 数据缓存位置

```
scripts/data/nav_history/     招银+杭银自营净值 CSV
~/study/nav/xy/               兴银净值 JSON（7786 只）
~/study/nav/citic/            信银净值 JSON（8102 只）
~/study/nav/ceb/              光大净值 JSON（100 只）
~/study/nav/ms/               民生净值公告清单 JSON（1399 只）
~/study/nav/boc/              中银净值 JSON
~/study/nav/hx/               华夏净值报告 JSON
~/study/nav/ny/               南银净值 JSON
~/study/cmb_daixiao_products.json   招行官网货架 132 只
~/study/hzbank_daixiao_thirdparty.json  杭行代销第三方 1469 只
```

---

## 推荐输出规范

当用户要"推荐/选哪个"时，固定输出三段：

1. **推荐至多 3 个放最前面**：逐个给理由（参照业绩 + 流动性 + 落选者原因），方便用户先看结论
2. **候选必须全部列出**：满足用户条件的候选一个不落（代码、管理人、风险、期限、名称、起购；招行侧带上发售/开放起始日期 `beginDate`），用户要自己对比
3. **业绩只用可信数据**：成立 <6 个月不输出指标，用同系列老份额参照
4. **参照业绩跟候选放在一起输出，不许分两段**：每个候选一张卡片，格式如下（参照系没有数据的写明"无业绩可参照"及原因，绝不留空白）：

```
华夏理财悦嘉最短持有180天4号C
`25315036C · R2 · 持有180天 · 起购1元`
📎 参照:同系2号C/D/E(317天)
近6月年化 +2.87%~+2.89%｜成立年化 +3.08%~+3.09%
最大回撤 -0.06%｜Sharpe(成立) +1.97｜数据截至 2026-10-12
✅/⚠️/❌ 一句话结论（是否推荐、为什么）
```

5. **负面信号要当场验证并写进卡片**：不推荐的原因必须给数据（如权益增强型近3月实测年化为负、typeinfo b5 固收+、老份额历史风险等级更高），不许只说"波动大"
6. 附"仅供参考，不构成投资建议"

---

## 业绩指标门槛

| 指标 | 最低门槛 | 勉强可信 |
|---|---|---|
| 成立年化 | 3个月 | 6个月+ |
| 最大回撤 | 6个月 | 1年 |
| Sharpe | 1年 | 2年+ |

## 同系列老份额参照（推荐前必做）

新份额（成立 <6 个月）指标是建仓期虚高，**不输出给用户**；推荐理由建立在同系列成立 1 年+ 老份额上：

1. 先在渠道产品目录按系列名关键字搜老份额（按 `beginDate` 排序取最老）；老份额已不在渠道发行的，用 web 搜产品全名找老代码（例：665593=招睿安悦370天1号、130052A=招睿明裕180天持有2号）。
   **⚠️ `series_ref.py` 只覆盖信银/华夏/南银/招行目录，不含杭银自营**。杭银自营系列的参照必须手动查杭银全量目录（`https://www.hzbankwealth.cn/eportal/hzbw/product_data.json`，5568 只含存续）：按系列名关键字过滤 `contenttitle`，取 `chanpinzhuangtai=存续` 且 `chengliriqi` ≥180 天的份额，用 `leijijingzhi` 和成立日算年化。**杭银自营系列报"无参照"之前必须先走这一步**，否则一律视为漏查（2026-11-25 实例：添益180天持有、安享优选182天周期型、半年添益全都有多年老份额，series_ref 却报 0）。
   同理，**南银系列 series_ref 报 0 时也要检查 `~/study/nav/ny/*_nav.json` 本地缓存并直接用 `ny_nav_fetch.py` 按代码拉**（增瑞财富牛 Z70021 当时缓存里就有 58 点净值，series_ref 却报 0）。华夏系同判断：先查 `hx/_index.json`（10153 份报告按产品 id 索引），候选代码在 priority 列表里就可用单代码抓取流程拉净值——固收增强周期180天（2119187001，5年老份额）就是这样找回的。
2. **"同系列"必须同登记编号（杭银看 `dengjino`、招银系列名逐字匹配），不能拿同家族不同产品线充数**：同一策略前缀下常有并行产品线（如杭银"丰鸿固收371天XXXX期"与"丰鸿固收（灵动目标盈）XXXX期"是两条独立线，登记编号不同）。拿错参照=虚假业绩背书。
3. 注意**风险等级的历史变化**：老份额当年可能风险等级更高（如丰鸿系 2026-06 前份额是 R3，之后才降标 R2），要向用户说明参照与本期不完全对应。
4. **typeinfo 等内部字段可作策略指纹**：杭银 typeinfo `b5`=含转债/弹性敞口（固收+），同带 b5 的产品线即使标 R2 波动也明显高于纯固收（b2/b3）线；稳健型用户优先纯固收线。
5. 整个系列无 1 年以上老份额的，明确标注"无业绩可参照、盲买管理人"。

## 已知限制

**净值缓存深度对照（决定哪个系列能用历史业绩验证，2026-11-25 实测）**：

| 通道（`~/study/nav/<mgmt>/`） | 历史深度 | 说明 |
|---|---|---|
| hx（华夏） | **全历史**（数百点/支） | 净值报告 JSON，最可靠 |
| xy（兴银） | 全历史（700+ 点） | `adjustedValue` 复权净值 |
| cmb / hzbank CSV | 全历史 | 招银/杭银自营 |
| citic（信银） | **仅 ~31 点**（1 个月） | wechat 接口只回近月，深历史拿不到 |
| ny（南银） | **仅 ~58 点**（约 2 个月） | 只够算近期年化，不能验证长期 |
| ms（民生） | 无结构化历史 | 仅最新净值+公告 PDF 链接 |
| ceb（光大） | 仅母行 100 只 | 专款（杭行74只）不在内 |
| boc（中银） | rows 多为空 | 静态页无结构化数据 |

其他：

- 光大专款（杭行74只/招行20只）：光大理财官网 cebwm.com 有瑞数反爬，脚本化不可行；用同系列公开份额参照
- 民生理财历史净值：cmbcwm.com.cn BTADailyQry 结构化直连（508只零售），但本地缓存只存了最新净值
- 南银理财偶发失败：重试即可（失败率~30%）；缓存深度仅 2 个月（见上表）
- **中国理财网（chinawealth.com.cn）：已退役，勿再使用**。2026-11-24 实测 `prod/search` 返回 `code:-1 "二次校验参数不能为空"`——服务端加了新的二次校验参数，RSA+AES 签名流程整体失效，**不是限频，重试无意义**（曾有记录误写为"限流 3-4 请求即 429"，以本条为准）。历史逆向代码**不在本仓库 git 历史中**（该文件从未提交过），副本在 `~/study/wealth-distribution-channel/cw_chinawealth.py` 和 `~/study/hzbank_yield/cw_chinawealth.py`。管理人直连接口已覆盖其原有用途
- 无直连数据源的管理人（建信/中邮/工银/浦银/交银/平安/宁银/北银等）：业绩不可验证，推荐时明确标注"无业绩可参照、盲买管理人"，不要凭列表信息推荐
- 华夏银行自营 164 只（杭行货架）：全部"到期"状态，2026底清理，无需关注
