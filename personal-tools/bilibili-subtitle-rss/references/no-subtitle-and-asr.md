# 无字幕判定与 ASR 回退

## 一、判定「视频确实没有字幕」

不要凭一次失败就下结论。按顺序排除，每步都留证据：

| 步骤 | 做法 | 判据 |
|---|---|---|
| 1 | `bili status` | `authenticated: true` — 排除登录失效 |
| 2 | `bili video <BV> --subtitle-timeline --json` | `subtitle.available` / `subtitle.items` 数量 |
| 3 | 拿一个**历史上有字幕**的 BV 号跑同一条命令 | 能出条目 = 凭证与工具正常，问题在视频本身 |
| 4 | 浏览器加载播放器，拦截 `x/player/wbi/v2` 响应 | `subtitle.subtitles: []` 且 `lan: ""` — 平台侧确实没挂字幕 |
| 5 | 查 `x/web-interface/view` 的 `rights` | `arc_pay`/`ugc_pay` = 0、`is_cooperation` = 1 — 非付费专属，排除权限原因 |
| 6 | 同 UP 主同系列其他集跑一遍 | 有字幕的集说明 UP 传了，这集是漏传 |

### 关键点

- **裸 curl 打 `x/player/wbi/v2` 不可信**：WBI 签名是页面 JS 算的，不签名会返回空 `subtitles`，看起来像"没字幕"实则是请求无效。**必须用浏览器真实加载后拦包**，或用 `bili` CLI（它内部已实现签名）。
- **`subtitle.list: []` 不代表视频没字幕**，要同时看 `lan` 字段。`lan: ""` 才是真没有。
- 同系列 3/6 集有字幕、3/6 没有，是常态——**单集漏传很常见**，不代表账号或接口问题。

## 二、ASR 回退（用户明确同意后才做）

skill 默认禁止自行触发 ASR。以下路径在用户点头后使用。

**首选且唯一：本机 FunASR 容器**（2026-11 部署，见下节）。

### 音频获取（两条路径通用）

```bash
uvx --from 'git+https://github.com/ZeroMarker/bilibili-cli.git@6962d5b' --with av \
    bili audio <BV> -o /tmp/bili_audio/
```

- **必须 `--with av`**：切分需要 PyAV，缺了报 `音频切分失败: 音频切分需要 PyAV 库`
- 产出 `seg_NNN.wav`，16kHz mono PCM，每段 25 秒
- 87 分钟视频 → 210 段，约 161MB

### 方案 A：FunASR 容器（首选）

容器：`funasr-asr`，SenseVoiceSmall + fsmn-vad + ct-punc，部署在 `/home/ohyes768/funasr-asr/`（docker compose 管理，restart: unless-stopped）。

```bash
# 健康检查；不通时 cd /home/ohyes768/funasr-asr && docker compose up -d
curl -s -m5 http://127.0.0.1:10301/health

# 逐段转写
curl -s -X POST http://127.0.0.1:10301/asr -F "file=@/tmp/bili_audio/seg_000.wav"
# 返回: {"results":[{"text":"..."}], "text":"..."}
```

要点：

- **繁简与标点容器内已处理**（SenseVoice 输出的 `<|zh|>` 类标签由服务端清理），不需要 zhconv、不需要 initial_prompt/vad_filter 参数——faster-whisper 的那批坑在这里不存在。
- **时间戳**：响应不带逐句时间戳，用段文件名 `seg_NNN` 推算：`from = NNN × 25`，`to = from + 25`（末段按剩余时长封顶）。精度是段级的，对合并分段（间隔>1.5s 规则）够用；`items` 的 `from`/`to` 用全片累计秒数。
- **失败重试**：单段 curl 超时（默认 7200s 上限太长，建议 `-m 300`）或返回非 200 时，重试该段，不要硬磨。
- **长视频直传**：小视频（<10 分钟）可把 `bili audio` 换成整文件直传 `/asr`（容器内 VAD 自动切段），一段请求搞定；更长的仍建议用 25s 分段，避免单请求内存峰值过高（容器限额 3G）。
- 段间拼 `text` 即全文；正文按 skill 的合并分段规则再处理。

### 输出 schema（两条路径通用）

必须产出 `bili` CLI 同构的 JSON，才能复用 `--input-json` 链路：

```json
{
  "ok": true,
  "schema_version": "1",
  "data": {
    "video": {"bvid": "BV...", "title": "...", "duration": "1:27:25",
              "url": "https://www.bilibili.com/video/BV...",
              "owner": {"name": "..."}, "aid": 0, "duration_seconds": 0},
    "subtitle": {"available": true, "format": "timeline",
                 "text": "...", "items": [{"from": 0.1, "to": 1.86, "content": "..."}]},
    "ai_summary": "", "comments": [], "related": [], "warnings": []
  }
}
```

`items` 的 `from`/`to` 必须是**全片累计时间戳**，不是分段内相对值（分段时加偏移量）。

## 三、诚实披露

ASR 稿与平台字幕性质不同，必须让读者知道。三个选项：

1. 标题 `B站文字稿｜<原标题>`，正文顶部加说明行 —— **推荐**，不破坏标题契约
2. 标题 `B站文字稿｜[ASR转写] <原标题>` —— 标题层面标注，但偏离 skill 固定格式
3. 什么都不标 —— **不推荐**，机器稿有错字风险，读者无从判断

正文模板里「以下为平台字幕原文」对 ASR 稿是错的，应改为「以下为语音识别生成的文字稿」。这是必要的事实修正，不属于内容编辑。

## 四、RSS 硬约束

- **RSS relay 只有 POST，没有更新/删除接口**。标题写错改不掉，**必须一次写对**。
- 服务端会**去除正文开头空行** → 正文不能以空行开头，否则读回不符返回 `unknown`。
- 读回核对只允许 CRLF/CR→LF 等价，其他正文或元数据变化都不算核对成功。
- 文章保留 15 天，列表最多 200 篇。查不到 ≠ 从未发布。

## 五、web_search 后端不可用时的替代

DeepSeek 后端欠费会返回 `HTTP 402: Insufficient Balance`，`web_search` / `web_extract` 全挂。改用：

- `curl` 直连目标站（B 站 `x/web-interface/*`、巨潮、东财）
- Playwright 加载页面并拦包（适合需要 JS 签名的接口）
- 站内搜索 API（B 站 `x/web-interface/search/type`）
