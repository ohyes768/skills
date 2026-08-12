"""飞书 Webhook CLI 入口"""

from __future__ import annotations

import argparse
import sys

from feishu_webhook import FeishuConfig, FeishuWebhook


def main() -> None:
    parser = argparse.ArgumentParser(description="飞书 Webhook 通知工具")
    parser.add_argument("--url", required=True, help="飞书 Webhook URL")
    parser.add_argument("--secret", required=True, help="签名密钥")
    parser.add_argument("--text", help="发送文本消息")
    parser.add_argument("--md", help="发送 Markdown 消息")
    args = parser.parse_args()

    config = FeishuConfig(webhook_url=args.url, secret=args.secret)
    client = FeishuWebhook(config)

    if args.text:
        result = client.send_text(args.text)
    elif args.md:
        result = client.send_markdown(args.md)
    else:
        print("请指定 --text 或 --md 参数")
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()