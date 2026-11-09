# 杭州 PM2.5 实况与五天趋势脚本及 Skill

## Goal

提供可重复运行的脚本及配套 Skill，回答：杭州现在 PM2.5 怎么样，未来五天大致会变好还是变差，为什么。报告使用通俗中文，便于日常阅读。

## Confirmed Facts

- 用户已将最初的七天预期调整为五天，并授权创建 Trellis 开发任务。
- 2026-10-24 已实测 Open-Meteo 空气质量接口：杭州坐标 30.2741,120.1551，指定 cams_global、Asia/Shanghai、forecast_days=5，返回 10 月 24—28 日；前四天各有 24 个有效小时，第五天只有 21 个有效小时。
- CAMS 全球模型提供约五天预报；模型浓度不能称作站点实测。接口按日期返回五天，不代表从查询时刻起完整 120 小时。
- 当前实测来源尚需验证；WAQI 的 iaqi.pm25 是分指数，不能作为浓度直接展示。
- 中国空气质量标准及 AQI 技术规定在 2026 年更新，等级换算需核验现行版本。

## Requirements

- R1：提供可独立调用的脚本和配套 Skill，默认查询杭州，输出结构化 JSON 和中文 Markdown。
- R2：报告展示当前可获取的 PM2.5 浓度、单位、数据时间、来源和代表位置；明确是实测还是模型估计。实测不可用时明确说明。
- R3：提供未来五天大致趋势、每天有效时段的预测均值及小时峰值；标明日期范围、小时覆盖和不完整日期，不将缺失值视作零。
- R4：结合风速、风向、降水、湿度、温度解释趋势；边界层条件及上风向污染数据可用时纳入，不可用时不得编造。
- R5：用大白话解释变好或变差的依据，避免固定套用“北风就好”“降温就差”等规则；不编造预测概率和置信区间。
- R6：PM2.5 浓度、PM2.5 分指数和综合 AQI 分开处理；若提供等级，注明标准、版本和平均时间口径。
- R7：支持数据过期、网络失败、部分缺失的明确提示，保留来源署名；不把旧缓存或模型估计冒充实时观测。
- R8：预报准确度尚未经过杭州本地回测，报告须表达为大致预期，不宣称已验证精度。
- R9（2026-10-27用户反馈）：默认报告供普通人一眼看懂，可见正文最多300字（不含来源URL、Markdown标记和空白）；只问今天时聊天回复尽量100字以内。默认不展开站点明细和技术参数，详细信息保留在 JSON；今天的简表只展示剩余时段预估，少于18小时的日均预估不展示为完整日均。

## Acceptance Criteria

- [ ] A1（R1）：一条命令生成可解析 JSON 和可阅读的中文报告，Skill 能调用该脚本。
- [ ] A2（R2、R7）：实测成功、不可用及数据过期三种情况下，报告都能正确标注来源、时间与数据类型。
- [ ] A3（R3）：核验五天覆盖；尾日缺失、不完整当天和零浓度均能正确区分，报告不虚称完整 120 小时。
- [ ] A4（R4、R5、R8）：趋势解释可追溯到实际输入，缺失气象因子不会产生虚构结论。
- [ ] A5（R6）：不会将 WAQI 分指数直接当浓度，也不会仅凭 PM2.5 宣称完整综合 AQI；等级换算口径有可核验来源。
- [ ] A6（R7）：接口失败及缺失数据有明确结果，输出包含供应方要求的来源署名。
- [ ] A7（R9）：正常、缺失、模型代替实测、旧批次及不完整日场景的短报均不超过300字；保留必要数据类型、时间、单位和缺项说明，JSON明细不变。

## Out of Scope

- 第一版不自行训练空气质量预测模型，不承诺街道或家庭尺度精度。
- 不自动配置定时推送、商业订阅或账户申请。
- 不提供个人医疗判断。

## Open Decisions

- 无阻塞问题。用户已授权开始实现；默认杭州主城区参考点，含今天五个自然日。
- 已验证总站公开站点查询接口正常 TLS 可用且无需密钥；使用参考点周边 25 km 站点自算均值，明确不是官方全市均值。
- 第一版不换算 AQI 或污染等级，直接展示浓度、趋势及气象解释，避免混用标准口径。

## Research References

- Open-Meteo air quality API: https://open-meteo.com/en/docs/air-quality-api
- CAMS forecast basis: https://www.ecmwf.int/en/forecasts/datasets/cams-global-atmospheric-composition-forecasts
- CNEMC observations entry: https://www.cnemc.cn/
- WAQI API and index semantics: https://aqicn.org/api/
- QWeather daily forecast (currently documents three days): https://dev.qweather.com/docs/api/air-quality/air-daily-forecast/
- Hangzhou meteorology and secondary aerosol study: https://acp.copernicus.org/articles/22/10623/2022/index.html
- Regional transport study: https://acp.copernicus.org/articles/20/7217/2020/index.html
- 2026 Chinese standards update: https://www.mee.gov.cn/ywdt/zbft/202602/t20260225_1144479.shtml

## Planning Status

User approved implementation. Source verification completed; design.md and implement.md record the implementation boundaries and checks.
