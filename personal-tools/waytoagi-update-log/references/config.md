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

脚本路径：`../scripts/send_dingtalk.js`

**发送 Markdown 到钉钉：**
```bash
node scripts/send_dingtalk.js "<webhook_url>" "<markdown内容>"
```

**注意事项：**
- Markdown 中的 `**文字**` 会被钉钉渲染为**粗体**
- `## 标题` 会渲染为大标题
- 链接格式：`[文字](url)` 会渲染为可点击链接
- 图片（`![](url)`）会被钉钉忽略，建议在输出时过滤图片行

## 发送示例

```bash
# 单行发送
node scripts/send_dingtalk.js "https://oapi.dingtalk.com/robot/send?access_token=xxx" "**测试** 这是一条测试消息"

# 多行内容（用引号包裹）
node scripts/send_dingtalk.js "https://oapi.dingtalk.com/robot/send?access_token=xxx" "## 标题\n- 项

目1\n- 项目2"
```
