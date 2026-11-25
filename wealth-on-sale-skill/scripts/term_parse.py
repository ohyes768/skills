#!/usr/bin/env python3
"""期限解析公共模块 —— on_sale_cmb / on_sale_hzbank 共用。

核心原则：
- 用户实际锁定天数（持有期/封闭期）优先从**产品名**解析，因为列表接口的
  term/prodTerm 字段常指"产品存续期"（动辄 365 天以上/数万天），不是持有期。
- 日开/天天/活期/现金管理类视为零锁定。
- 封闭式产品的 term 字段才是封闭期（「181天-365天」取下界、「365天以上」取 365）。
"""
import re

# 名称中的持有期/封闭期模式，按优先级
HOLD_PAT = re.compile(
    r"(\d+)天(?=持有|最低持有|最短持有)"          # 180天持有期 / 最短持有180天
    r"|(?:最低|最短)持有(\d+)天"                  # 最低持有360天
    r"|封闭式(\d+)天"                             # 封闭式391天
    r"|(\d+)天(?:定开|周期型|周期)"               # 14天定开 / 182天周期型
)
ZERO_LOCK_PAT = re.compile(r"日开|每日开放|天天|活期|现金管理|周周开|周周盈|月月开|月月盈|单周定开|单月定开|天添益|金钱包|零钱包|新钱包|日申月赎")
RANGE_PAT = re.compile(r"(\d+)天-以上|(\d+)天[-~]（?含）?|(\d+)天")


def term_days(term):
    """term 字段 -> (最短天数, 最长天数|None)。解析失败返回 None。

    「181天-365天（含）」-> (181,365)；「365天以上」-> (365, None)；「90天」-> (90, 90)
    """
    if not term:
        return None
    t = str(term).replace("（含）", "").replace("(含)", "")
    nums = [int(x) for x in re.findall(r"(\d+)天", t)]
    if not nums:
        return None
    if "以上" in t:
        return (nums[0], None)
    if len(nums) >= 2:
        return (min(nums), max(nums))
    return (nums[0], nums[0])


def hold_days(name, term=None):
    """产品对用户的实际锁定天数。解析不出返回 None。

    优先级：名称明确持有期 -> 日开/现金类=0 -> 名称独立天数 -> term 字段下界（封闭式语义）。
    注意「天天购（180天最低持有）」含"天天"但锁 180 天，所以持有期判断必须在前。
    """
    m = HOLD_PAT.search(name or "")
    if m:
        return int(next(x for x in m.groups() if x))
    if name and ZERO_LOCK_PAT.search(name):
        return 0
    # term 字段直接写明开放方式的（「每日开放」「日开」「周周开」等）也是零锁定
    if term and re.search(r"每日开放|日开|周周|月月|随时", str(term)):
        return 0
    # 名称里的独立天数（如「丰裕固收763天26173期」「半年鑫最短持有期189天」）
    if name:
        if re.search(r"最短持有期(\d+)天", name):
            return int(re.search(r"最短持有期(\d+)天", name).group(1))
        if "半年" in name:
            return 180
        nums = [int(x) for x in re.findall(r"(\d+)天", name)]
        if nums:
            return max(nums)
    td = term_days(term)
    return td[0] if td else None
