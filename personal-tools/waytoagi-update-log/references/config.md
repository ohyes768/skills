# WaytoAGI 更新日志追踪 - 配置参考

## 钉钉群机器人配置

**Webhook 通过 `.env` 注入**，不要硬编码：

```bash
cp .env.example .env
# 编辑 .env，把 DINGTALK_WEBHOOK 替换为真实值
```

`.env` 已被 `.gitignore` 排除，不会进入 git 历史。

**安全设置：** 暂无（可自行在钉钉机器人设置中加签或 IP 白名单）

## 发送脚本

实际发送由公共 skill `dingtalk-push`（canonical：`personal-tools/dingtalk-push/scripts/dingtalk_send.py`）执行；`../scripts/send_dingtalk.js` 只是兼容 shim：定位公共 CLI、固定 title/关键词、正文经 stdin 传入，自带 HTTP 已移除。

**发送 Markdown 到钉钉**（webhook 参数可省略，省略时 shim 经 `--env-file` 让公共 CLI 读本 skill 的 `.env`）：
```bash
node scripts/send_dingtalk.js "<webhook_url可选>" "<markdown内容>"
```

**结果判定：** stdout 是单个 JSON。`sent`（退出码 0）= 已送达；`duplicate` = 同内容已发过，不再重发；`failed`（2）= 显式拒绝（如 310000 关键词不匹配、连接失败），修正后重试；`unknown`（3）= 超时/响应异常，**不要自动重发**，先人工核对群消息；`conflict`（4）= 同键不同内容。webhook/token 不会出现在任何输出里。

**注意事项：**
- Markdown 中的 `**文字**` 会被钉钉渲染为**粗体**
- `## 标题` 会渲染为大标题
- 链接格式：`[文字](url)` 会渲染为可点击链接
- 图片（`![](url)`）会被钉钉忽略，建议在输出时过滤图片行

## 发送示例

```bash
# 单行发送（省略 webhook，走 .env）
node scripts/send_dingtalk.js "" "**测试** 这是一条测试消息"

# 显式传 webhook（旧用法，继续兼容）
node scripts/send_dingtalk.js "https://oapi.dingtalk.com/robot/send?access_token=xxx" "**测试** 这是一条测试消息"
```
