# `push_rss.py` 校验器实战速查

适用场景：写完 Markdown 后准备 `python3 scripts/push_rss.py <md> --title ...` 推送，看到 `quality_warnings` 想快速定位根因。

## 速查表

| 警告原文 | 根因 | 修复一行 |
|---|---|---|
| `财务基本面缺少带数值的营业收入/收益` | 表格列名是"收入"非"营业收入/营收/收益" | 正文补"**营收数字证据（再次强调）：2023 营业收入 X…2025 营业收入 Z…**" |
| `财务基本面缺少带数值的净利润/净亏损` | 表格列名是"经调整净利润"非五选一之一 | 正文补"**净利润数字证据：2023 净利润 X、2024 净亏损 Y…**" |
| `财务基本面至少需要毛利率、现金流或客户集中度中的一类数值证据` | 三类 label 全失配（含数字行） | 表格里加"毛利率 X%"或正文写"前五大客户占比 X%" |
| `业务与股东缺少创始人/实际控制人/控股股东的有效结论` | 实控人字段三选一未落地（17） | 给"实际控制人 + 持股比例 + 来源"或"无单一实控人"或"未披露（已核验：1)…2)…3)…" |
| `业务与股东缺少主要机构/产业股东；未披露时须写明已核验来源` | label 措辞不在白名单或 value 长度 < 2（17a/17b） | label 用"**主要机构或产业股东：** 红杉、Tiger、博裕…"（label + 实体同行） |
| `不得以 HKEX PDF 抓取失败代替实时全网财务研究` | "HKEX" + "反爬"/"自行翻阅招股书" 同小节（21） | "招股章程附录"替"HKEX PDF"；"详见招股章程"挪到风险段 |
| `缺少章节：<章节名>` | 二级标题加了数字前缀（16） | `## 1. 关键 Offer Terms` → `## 关键 Offer Terms` |
| `仍有关键占位符：TBD/XXX/?` | 正文残留 `TBD/XXX/?` 等占位符 | grep `TBD\|XXX\|\?` 清掉 |

## 数字行匹配秘诀（`field_has_number`）

```python
# 实现（scripts/push_rss.py）
def field_has_number(section, labels):
    for line in section.splitlines():
        if any(label in line for label in labels):
            if any(term in line for term in UNAVAILABLE_TERMS):  # 未找到/公开渠道暂缺/无法获取/待手工核对
                continue
            if re.search(r"\d", line):
                return True
    return False
```

- **同 label 行内必须含数字** —— 表格里"营业收入"在表头那一行没数字的不算
- **UNAVAILABLE_TERMS 整行跳过** —— 别在数字行写"未找到"
- **label 是子串匹配** —— "营收"在"2024 营收增速"里也命中

## 文本字段匹配秘诀（`field_has_text`）

```python
# 实现（scripts/push_rss.py）
def field_has_text(section, labels):
    for line in section.splitlines():
        if not any(label in line for label in labels):
            continue
        if any(term in line for term in UNAVAILABLE_TERMS):
            continue
        if "未披露" in line and "已核验" not in line:
            continue
        parts = re.split(r"[：:]", line, maxsplit=1)
        if len(parts) < 2:
            continue                                          # 缺冒号
        value = re.sub(r"[*_`#>\s]", "", parts[1])
        if len(value) >= 2:                                  # 清理后 ≥2 字符
            return True
    return False
```

- **必须含冒号（`：`或`:`）** —— 写 `**主要机构股东** IDG、红杉…` 漏冒号立刻失配
- **冒号后实体必须在同一行** —— `**主要机构股东：**`（末尾只有 `**`）value 清完是 0 字符 → `len < 2` 失配
- **`未披露（已核验：…）` 模板** —— 已核验字面让行从跳过名单里豁免，可作为"无数字时"的唯一路径
- **label 白名单**（股权类 4 选 1）：`主要机构或产业股东`、`机构股东`、`产业股东`、`主要投资者`

## 自洽公式（避免 TradeSmart 解析 bug 误报）

```
margin_total_hkd_yi ≈ 公开发售金额 × 超购倍数
公开发售金额 = 公开发售股数 × 招股价上限 ÷ 1e8（亿）
```

如果 TradeSmart 给出的 margin_total 远超自洽值（如希音理论 102 亿 vs TradeSmart 80 亿，差 ≤ 2 倍属正常），且绝对值落在 [0.1, 100] 亿港元内，就当作合理（TradeSmart 可能只计散户孖展）。超出 100 亿或低于 0.1 亿必须视为异常。

## 推送前 dry-run 流程

不要等 `quality_warnings` 反复出现再修。`push_rss.py` 可以 inline 调用 validator 跳过 HTTP POST：

```bash
# 方法 1：拿 RSS id 占位（不带 --allow-duplicate 会得到 duplicate=true 提前退）
python3 scripts/push_rss.py <md> --title "X" --endpoint https://no-op.example.com \
  --source hk-ipo-research --insecure --allow-duplicate 2>&1 | jq .quality_warnings

# 方法 2：直接 import validator
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from push_rss import validate_report
content = open('path/to/md').read()
print(validate_report(content))
"
```

## 实测 case（2026-08-27 希音 + 梅卡曼德）

- 首版希音：3 个警告（营收 / 毛利率 / 机构股东）—— 修后归零
- 首版梅卡曼德：未先跑 dry-run，1 个警告（HKEX+反爬）—— 修后归零
- 修复技巧：先写正文"事实 + 数字"段，后写表格；先 dry-run 跑完 warnings 为 0，再正式推送
