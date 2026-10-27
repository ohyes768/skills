# 数据来源与输出口径

## 数据源

1. **站点实测：中国环境监测总站**。空请求体的只读查询：`POST https://air.cnemc.cn:18007/HourChangesPublish/GetAllAQIPublishLive`。保留 TLS 验证，使用该站 Referer；只保留 `CityCode=330100` 的杭州数据。2026-10-24 已验证可用，无需密钥。同一接口每站点还返回 `PM2_5_24h`（24小时滑动平均，实测口径），用于近24小时均值，无需额外请求。这是公开网站使用的未版本化接口，未来可能变化，不承诺可用率。[总站入口](https://www.cnemc.cn/)
2. **空气质量：Open-Meteo / CAMS Global**。`https://air-quality-api.open-meteo.com/v1/air-quality`，参数为杭州经纬度、`hourly=pm2_5`、`domains=cams_global`、`forecast_days=5`、`timezone=Asia/Shanghai`。[接口文档](https://open-meteo.com/en/docs/air-quality-api)、[CAMS 五天模型说明](https://www.ecmwf.int/en/forecasts/datasets/cams-global-atmospheric-composition-forecasts)
3. **天气：Open-Meteo**。`https://api.open-meteo.com/v1/forecast`，同一坐标、时区和日期；小时字段为 `temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,boundary_layer_height`，指定 `wind_speed_unit=ms`。[天气文档](https://open-meteo.com/en/docs)

Open-Meteo 免费接口用于非商业场景；商业用途需按供应方条款选择服务。报告保留 CAMS / ECMWF、Open-Meteo 署名。[使用条件](https://open-meteo.com/en/pricing)

## 实测与时间

- 实测浓度使用 `PM2_5`，不是 `PM2_5_24h`，也不是 PM2.5 的 AQI 分指数。`TimePointStr` 按北京时间解析为观测小时。小时发布数值描述该小时对应的监测时段，不是传感器的瞬时读数。
- 主城区参考点周边 25 km 范围内，取最新有效且不晚于报告时间的观测小时，按站点去重后计算均值；不混入旧小时站点。报告包含站点数、各站浓度及距离。这个样本可能包含主城区周边区域，不代表官方市级统计。
- 超过 3 小时的观测标为 `stale`，不再当作当前情况；如果当前附近两小时内有 CAMS 值，则明确以模型估计代替。不可用时没有静默旧缓存。
- `PM2_5_24h` 是总站发布的站点级 24 小时滑动平均（实测），覆盖以最新有效观测小时为终点往前约一天。近24小时均值只对最新有效小时站点集合中有该值的站点取算术均值，旧小时站点不混入；站点值全缺时为 null，`NA`、负值拒绝，0 是有效值。接口不提供逐小时历史，因此**不计算自然日实测日均**，也不把当天已过时段的平均当作全天日均。
- 固定使用 UTC+08:00，无需操作系统安装 IANA tzdata。接口返回时区必须为 Asia/Shanghai。输入时间必须可解析、整点且不重复；数组长度及单位不符时拒绝该供应方数据。
- 报告生成时间、快照获取时间、实测时间是不同字段。接口没有提供可核验的起报时刻，因此 `sources.model_initialization_time=null`，不能用抓取时间冒充起报时刻。

## JSON 主要字段

默认 Markdown 是面向普通人的短报：可见正文最多300字（不含来源URL及Markdown标记），仅含当前浓度、近24小时均值与WHO对照、时间、两列预测表、一句天气原因和必要缺失提示。默认不展开站点、峰值、技术参数或错误堆栈。JSON 结构和精度不变，保留全部证据。聊天中只问今天时，Skill 最终回复尽量100字以内。

| 字段 | 含义 |
|---|---|
| `status` | `ok` 数据完整；`partial` 有数据但有缺项/过期提示；`unavailable` 当前和所有日期均无可用 PM2.5 |
| `current` | 浓度、数据时间、`kind=observation/model_estimate`；无值时为 null |
| `observations` | 实测状态、选中小时、站点列表、半径和自算均值 |
| `observations.mean_pm25_24h` | 近24小时实测均值：最新有效小时站点的 24h 滑动平均自算均值；站点值全缺时为 null |
| `health_reference` | WHO 2021 PM2.5 24小时指导值 15 μg/m³；注明是参考线，不是安全线 |
| `daily[].valid_hours` | 当天有效 PM2.5 小时数，0 是没有数据，不是浓度为零 |
| `daily[].mean_pm25` | 有效小时模型均值；只有24小时完整时才是完整模型日均 |
| `daily[].peak_pm25/peak_times` | 有效小时中的峰值和对应时间 |
| `daily[].remaining_mean_pm25` | 生成时间之后的有效整点均值；不包含已经开始的当前小时 |
| `daily[].weather.counts` | 各天气字段独立的有效小时数，可能与PM2.5覆盖不同 |
| `daily[].factors` | 有数值依据的条件性天气解释；无触发信号不代表空气一定好 |
| `warnings/limitations/attribution` | 数据缺口、模型局限和来源署名 |

`trend` 仅比较有效小时数不少于18的日期，不完整日排序仍可能偏移。今天的全天模型数值包括已过时段；表格和天气统计都不是整段“尚未发生的未来”。天气统计使用当天各自有效小时，可能与PM2.5覆盖不同。

## 三种均值口径与健康参考

| 口径 | 窗口 | 性质 | 报告位置 |
|---|---|---|---|
| 近24小时均值 | 以最新有效观测小时为终点往前约一天 | 实测（总站 24h 滑动平均自算） | `observations.mean_pm25_24h`，短报单独一行 |
| 自然日实测日均 | 当天 0—24 时 | 实测，但一天结束后才完整；数据源不提供 | 不输出，不得用部分时段平均冒充 |
| 未来日均 | 未来自然日 | 模型预估 | `daily[].mean_pm25`，短报标“约” |

WHO 2021《全球空气质量指南》PM2.5 24小时指导值为 15 μg/m³（年均值为 5）。它是参考线，不是安全线：高于说明近期暴露偏高，低于也不代表零风险；本 skill 不据此贴“安全/不安全”标签，也不换算 AQI 或等级。[指南原文](https://www.ncbi.nlm.nih.gov/books/NBK574591/)

## 气象解释阈值

这些是可解释的工程规则，**不是健康阈值、官方分级或经过拟合的预测公式**，不会据此乘系数修改 CAMS 浓度：

- 风速 <2 m/s 的小时数至少6：提示风小，可能积累。
- 湿度 ≥80% 且风速 <2 m/s 的同一小时数至少4：提示高湿静风，可能有利于颗粒物增长。
- 边界层 <300 m 且风速 <2 m/s 的同一小时数至少4：提示垂直扩散空间较小，不能直接诊断逆温。
- 有效天气小时累计降水 ≥2 mm 且至少3小时降水 ≥0.1 mm：提示湿清除可能有利。
- 有效天气小时平均风速 ≥3 m/s：提示扩散条件，但同时保留上风向输入污染的可能。

风向使用风速加权圆平均，避免359°与1°算成180°；方向过于分散或静风时不强行给主导风向。温度显示范围，不能单独决定PM2.5变化方向。

杭州相关机制可参考[本地环流、温湿度与二次气溶胶研究](https://acp.copernicus.org/articles/22/10623/2022/index.html)；区域输送可参考[长江流域输送研究](https://acp.copernicus.org/articles/20/7217/2020/index.html)。这些研究支持考虑因素，不验证本脚本规则的预测准确率。

第一版不计算 AQI 或“优良”等级。需要扩展时，先核验现行 HJ 633—2026、平均时间与标准过渡期，不能直接套用旧阈值，也不能用单一PM2.5代替综合AQI。[2026 标准修订说明](https://www.mee.gov.cn/ywdt/zbft/202602/t20260225_1144479.shtml)

## 故障排查与回放

每个接口最多尝试2次，单次超时20秒；三个源并行获取。某个源失败时保留其他结果。网络出错不代表浓度为零。HTTP 请求保留证书检查，不因连不上而关闭 TLS 验证。

```bash
python "<skill-dir>/scripts/hangzhou_pm25.py" --save-input "<output-dir>/input.json" --output-dir "<output-dir>"
python "<skill-dir>/scripts/hangzhou_pm25.py" --input "<output-dir>/input.json" --now "2026-10-24T17:00:00+08:00" --format json
```

第二条命令完全离线；`--now` 只能与 `--input` 配合。复现时填入快照对应时间；不传 `--now` 则按真实当前时间检查新鲜度和筛选日期。`--save-input` 仅保存杭州站点原始行，不保留全国站点数组。

退出码：0 为存在可用 PM2.5（可能 partial）；1 为全部 PM2.5 不可用但仍输出报告；2 为输入、参数或文件错误。JSON 标准输出不夹杂运行日志。

开发验证：`python -m unittest discover -s environment/hangzhou-pm25/tests -v`。
