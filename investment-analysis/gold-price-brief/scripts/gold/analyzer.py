"""
DeepSeek AI 分析模块
"""

import os
import json
import requests
from typing import Optional


class GoldAnalyzer:
    """DeepSeek 黄金分析器"""

    API_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化分析器

        Args:
            api_key: DeepSeek API密钥，默认为环境变量 DEEPSEEK_API_KEY
        """
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeek API密钥未设置，请设置 DEEPSEEK_API_KEY 环境变量")

    def analyze(self, gold_data: dict) -> str:
        """
        调用DeepSeek分析黄金走势

        Args:
            gold_data: 包含以下字段的字典:
                - time: 当前时间
                - gold_price: 当前金价（元/克）
                - gold_rsi_14: RSI指标
                - series: 历史数据列表

        Returns:
            AI分析文本
        """
        # 构建提示词
        prompt = self._build_prompt(gold_data)

        # 调用API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.2,
            "max_tokens": 1400,
        }

        response = requests.post(
            self.API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _build_prompt(self, gold_data: dict) -> str:
        """只提供可核查的输入事实，利率方向由程序计算。"""
        series_json = json.dumps(gold_data.get("series", []), ensure_ascii=False, indent=2)
        fed_json = json.dumps(gold_data.get("fed_expectations", {"status": "unavailable"}), ensure_ascii=False)
        price_json = json.dumps(gold_data.get("price_summary", {"status": "unavailable"}), ensure_ascii=False)
        holdings_json = json.dumps(gold_data.get("holdings_summary", {"status": "unavailable"}), ensure_ascii=False)
        prompt = f"""北京时间：{gold_data['time']}。上海Au9999：{gold_data['gold_price']} 元/克。
国际现货XAUUSD：{gold_data.get('xau_usd')} 美元/盎司（None表示暂缺）。
日线RSI(14)：Wilder={gold_data.get('gold_rsi_14')}，Simple={gold_data.get('simple_rsi_14')}，第三方={gold_data.get('ali_rsi_14')}。
历史数据：{series_json}
国内价格技术摘要（程序计算，单位元/克，None表示暂缺）：{price_json}
SPDR最新有效持仓比较（独立记录日期）：{holdings_json}
gold_price为人民币/克；High_VIX/Close_VIX为VIX日高/收盘；gold_tonnes为SPDR官方实物持仓吨数；gold_tonnes_change为记录间吨数变化。各项按自身记录日期使用，缺失不估算，不把持仓变化等同于精确申赎流量。
美联储预期（程序已计算）：{fed_json}

请只根据以上事实，用中文写350—500字的黄金走势分析。重点回答黄金现在如何走、价格依据是什么、后续观察什么。规则：
1. 不得编造未提供的美元指数、实际利率、汇率、新闻、央行讲话和经济数据。你没有实时联网能力。
2. change是较上一发布日期快照的变化，baseline_published_at给出准确基准；pp是概率百分点，bps是利率基点。不要自行替换成接口内置“昨日”值。
3. 下次会议的cut/hold/hike是相对当前利率的概率；后续会议是累计利率路径，不能写成该次会议单独加减息概率。预期不等于美联储承诺。
4. direction=hawkish/dovish表示预期利率上移/下移，对黄金仅为潜在压力/支撑，不能据此保证涨跌或直接给买卖指令。结合金价、RSI，说明是否有价格确认；数据不足时明确不足。
5. status为fallback、stale、unavailable或awaiting_update时，不得据旧快照判断当前利率方向。is_new_snapshot=false不代表概率变化为零，只表示本轮未取得更新快照，不可描述为刚刚发生的冲击。
6. 日线收盘、均线和历史区间只按price_summary的日期使用；不能编造完整K线形态或RSI背离。当前报价本身不是支撑阻力，不编造精确入场、止损点位。
7. Wilder RSI(14)为主要口径，Simple和第三方仅提示差异，不能用三口径占据正文；超卖不等于止跌或见底。日线status=stale时，均线、区间及本地RSI只作历史参考，不判断当前技术趋势。
8. 日涨跌是最近已完成交易日收盘相对前收盘；quote_change_pct是实时价较最近收盘。注明比较日期；国际现货只有报价，不推算国际涨跌。实时触及均线或区间边界，不等于收盘确认。
9. 先根据收盘变化、MA5/MA20及近期区间判断趋势；后续观察给出有数据依据的条件：收盘收复均线、重新跌破区间等，并解释对趋势判断的意义。仅有收盘区间时不能称日内高低点。数据不足逐项注明。
10. 持仓优先使用holdings_summary的有效记录比较，标明起止日期；陈旧持仓只供历史参考。VIX水平仅是市场波动背景，不能单独判断黄金避险需求强弱。
严格按三个小节输出：**黄金走势**（先给判断和价格依据，占正文至少一半）、**辅助因素**（SPDR与利率只解释对黄金的影响，不复述完整会议概率表）、**后续观察**（具体价格条件与确认方式）。不要以利率开篇，不重复附录报价。"""

        return prompt
