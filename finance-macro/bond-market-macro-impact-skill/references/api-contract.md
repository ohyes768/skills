# 聚合快照 API 1.0

依据 personal-web/backend/macro/docs/ANALYSIS_SNAPSHOT_API.md（2026-09-21）及同日服务端实现核对。

`GET https://web.duomi77.cn:9443/api/macro/analysis/snapshot`，无需鉴权。

- `months`：逗号分隔 YYYY-MM，最多 12 个；默认最新可用月，不保证完整。
- `date`：YYYY-MM-DD；默认服务端 15:00 规则。脚本首次不传 date 时尊重该规则。
- 响应 `success=true, data={schema_version, generated_at, request, monthly:{periods}, daily:{as_of,cards}, quality}`。
- period：month/status/cards；card：id/title/frequency/status/indicators，月度附 score/conclusion。
- indicator：key/name/unit/value/data_date/status，月度可能有 analyzed_at/next_release_at/next_release_note，日频可能有 previous_value/change/is_asof_fallback。
- 200 可能部分缺失、过期或回退；无月度快照 period.status=unavailable。400 参数错误；500 读取异常。未知字段忽略，未知 schema 版本停止，TLS 校验保持开启。

月度标准 key：

- monetary_policy：lpr_1y/lpr_5y/mlf_net_yi。
- money_supply：m2_yoy/m1_yoy/social_yoy/m2_m1_spread/spread_change_pp。
- entity_economy：pmi_manufacturing/industrial_yoy/fai_yoy/retail_yoy。
- inflation：cpi_yoy/ppi_yoy。

日频标准 key：

- liquidity：dr001/dr007/cn_10y/cn_10y_2y。
- external_pressure：dollar_index/usd_cny/ted_spread/hibor_overnight/north_today_yi/north_7d_avg_yi/north_7d_change_pct/cn_us_10y_spread/vix。
- market_sentiment：volume/turnover/margin/south_net_yi。

实现核对：历史日频按 ≤ 请求日取最近值，支持日期请求；north_today_yi 是北向成交额，7 日指该序列交易日窗口；south_net_yi 是南向净流入。quality.stale_keys 当前为空列表，quality.status 主要由缺失决定，不能据此证明数据新鲜。每个指标都要看实际日期。

脚本保存原始响应用于追溯；月度分析时间晚于历史分析时点则排除，仍无法保证当时可见或未修订。每日 previous_value 的实际间隔在接口中没有标注，默认不参与趋势计算；使用具有明确日期的历史观察值比较。
