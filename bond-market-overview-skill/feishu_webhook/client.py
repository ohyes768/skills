"""飞书 Webhook 通知模块"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class FeishuConfig:
    """飞书配置"""

    webhook_url: str
    secret: str


class FeishuWebhook:
    """飞书 Webhook 发送器"""

    def __init__(self, config: FeishuConfig) -> None:
        self._config = config

    def send_text(self, text: str, at_mobiles: list[str] | None = None) -> dict[str, Any]:
        """
        发送文本消息

        Args:
            text: 消息内容
            at_mobiles: 需要 @ 的手机号列表

        Returns:
            API 响应结果
        """
        payload = {"msg_type": "text", "text": {"content": text}}
        if at_mobiles:
            payload["text"]["at_mobiles"] = at_mobiles
        return self._send(payload)

    def send_markdown(
        self,
        content: str,
        at_mobiles: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        发送 Markdown 消息

        Args:
            content: Markdown 格式的内容
            at_mobiles: 需要 @ 的手机号列表

        Returns:
            API 响应结果
        """
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "📢 通知"},
                    "template": "red",
                },
                "elements": [{"tag": "div", "content": content}],
            },
        }
        if at_mobiles:
            at_section = {
                "tag": "at",
                "at_mobiles": at_mobiles,
                "is_whole": False,
            }
            payload["card"]["elements"].append(at_section)
        return self._send(payload)

    def _sign(self, timestamp: int, secret: str) -> str:
        """生成签名"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """发送请求到飞书"""
        timestamp = str(int(time.time()))
        sign = self._sign(int(timestamp), self._config.secret)

        # timestamp 和 sign 放在请求体中，不是 URL 参数
        payload["timestamp"] = timestamp
        payload["sign"] = sign

        response = requests.post(self._config.webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()