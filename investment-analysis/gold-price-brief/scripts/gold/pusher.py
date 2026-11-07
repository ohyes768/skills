"""
钉钉推送模块
"""

import os
import hmac
import hashlib
import base64
import urllib.parse
import time
import requests
from typing import Optional


class DingTalkPusher:
    """钉钉机器人推送器"""

    def __init__(
        self,
        webhook: Optional[str] = None,
        secret: Optional[str] = None,
    ):
        """
        初始化推送器

        Args:
            webhook: 钉钉 webhook URL，默认为环境变量 DINGTALK_WEBHOOK
            secret:  加签密钥，默认为环境变量 DINGTALK_SECRET
        """
        self.webhook = webhook or os.environ.get("DINGTALK_WEBHOOK")
        if not self.webhook:
            raise ValueError("钉钉 webhook 未设置，请设置 DINGTALK_WEBHOOK 环境变量")
        self.secret = secret or os.environ.get("DINGTALK_SECRET", "")

    def _get_sign(self) -> tuple:
        """
        生成钉钉加签

        Returns:
            (timestamp, sign) 元组
        """
        if not self.secret:
            return "", ""

        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.secret}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(
            secret_enc, string_to_sign_enc, digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def _build_url(self) -> str:
        """构建完整的 webhook URL（包含签名）"""
        if not self.secret:
            return self.webhook

        timestamp, sign = self._get_sign()
        return f"{self.webhook}&timestamp={timestamp}&sign={sign}"

    def push_markdown(
        self,
        title: str,
        content: str,
    ) -> bool:
        """
        推送 Markdown 消息到钉钉

        Args:
            title: 消息标题
            content: Markdown 格式的消息内容

        Returns:
            推送是否成功
        """
        url = self._build_url()

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content,
            },
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            return result.get("errcode", 1) == 0
        except Exception as e:
            print(f"钉钉推送失败: {e}")
            return False
