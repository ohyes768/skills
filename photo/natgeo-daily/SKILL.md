# natgeo-daily 国家地理每日一图

每日抓取 National Geographic Photo of the Day，翻译描述并推送钉钉。

## 工作流程

1. 运行脚本（自动：抓页面 → 提取 OG 数据 → LLM 翻译描述 → 推钉钉 → 落 JSON）：

```bash
python3 /home/ohyes768/skills/photo/natgeo-daily/scripts/natgeo_daily.py
```

2. 向调用方汇报：标题 / 摄影师 / 中文摘要一句 / 是否推送成功。
3. 脚本退出码：0=成功；2=当日照片提取失败；3=钉钉推送失败；4=其他异常。非 0 时原样转述 stderr。

## 说明

- 翻译：优先脚本内置 DeepSeek（env `DEEPSEEK_API_KEY`）；Hermes 会话内运行时若无 key，直接由你翻译描述后写入即可——但**不要**为翻译重跑脚本。
- 钉钉 webhook：env `NATGEO_DINGTALK_WEBHOOK` / `NATGEO_DINGTALK_SECRET`，只从环境变量读取（可写入本 skill 目录 `.env`，脚本启动时自动加载、不覆盖已有环境变量），参照 `.env.example`；未配置时推送失败（退出码 3）。
- **推送判定必须看 `errcode`，不能只看 HTTP 200**：钉钉业务失败（errcode=-1「系统繁忙」等）同样返回 HTTP 200。脚本已内建判断 + 最多 3 次重试（退避 3s/6s/9s），重试全失败才返回退出码 3。
- 摄影师提取：NatGeo 描述有「Photograph by X」和正文内嵌「photographer X says」两种写法，脚本两种都认；只认首字母大写词组，避免把普通短语当人名。带资质后缀（如 `Endia Beal, MoCP`）会保留。
- 无按日去重：同日重跑会重复推送，属于已知行为（与原 stock-info 脚本一致）。**推送失败后重试别用整脚本重跑**，直接复用 `data/natgeo_photo_YYYYMMDD.json` 重发，避免二次抓取。
- 调度：由 task-web（personal-web）统一触发；本 skill 不自带 cron。
