# 实施计划与完成记录

## 顺序

- [x] 用户已确认本期迁移全部现有来源，并更新 PRD。
- [x] 用户要求实施后，读取 trellis-before-dev/skill-creator，review 后才 task.py start；分别检查外部仓库规范、工作区与调用契约。
- [x] 验证 skill-manager 对新目录发现/整包发布、Windows 安装根解析和目标 Python 版本；沿用既有分发。
- [x] 固化 CLI/JSON/退出码；先建立临时目录及本地假 HTTP 服务的行为测试。
- [x] 实现标准库公共脚本：输入/配置、SQLite 原子占用、五字段 POST、回执、按 id 读回、unknown 恢复。
- [x] 编写薄 SKILL.md、integration.md：两类接入模板、Windows/Linux 示例、配置、unknown 查证、去重限制。
- [x] 迁移 B 站字幕，验证旧回执接管、输出兼容及显式发布授权。
- [x] 迁移 A 股和利率债宏观两类入口，保留 validator/strict，验证 RSS duplicate 后仍可补发看板。
- [x] 迁移港股研究和回测共享发布入口，分别验证日期/code/报告类型身份及原参数兼容。
- [x] 迁移 WaytoAGI 的 skill 投递说明及相关调用入口，保留 mention-doc 和多渠道回执语义。
- [x] 迁移 daily-review 与新闻联播外部仓库入口，保留调度参数、dry-run、环境配置及返回码。
- [x] 全量扫描旧 POST 实现和 skill 中手写请求示例，确保 8 类实际投递都复用公共入口；更新仓库索引及部署配置说明。
- [x] 完成自动测试、Windows/Linux 烟测和技能校验；把有依据的公共契约补充至 spec。发布独立验收。

## 验证命令（已执行）

```text
python -m unittest discover -s knowledge/rss-relay-publish/tests -v
python -m py_compile knowledge/rss-relay-publish/scripts/rss_publish.py
python knowledge/rss-relay-publish/scripts/rss_publish.py --help
python <skill-creator-dir>/scripts/quick_validate.py knowledge/rss-relay-publish
git diff --check
```

运行全部迁移入口的原有测试：B 站字幕、宏观发布与 hkipo 载荷测试，以及 daily-review 和 stock-info-dingding 的相关测试。具体命令由实施前检查各仓库后记录，不猜测现有测试结构。对 WaytoAGI 补充假服务驱动的投递与回执验证。Linux 烟测须实际执行；无环境则标为未验证，不能用 Windows 结果代替。

必须覆盖：201+完整核对、元数据/正文不符、无 id、HTTP 拒绝、列表失败、TLS 配置一致、POST 后断连但已写入、超时无结果、多个匹配、跨来源/频道同名、重复、键冲突、并发、崩溃 pending、回执不可写、dry-run 零发布副作用、升级保留回执、中文与带空格路径。自动验证不接触真实发布端点。

## 风险与回滚

- 无服务端幂等，unknown 不重发；需要跨环境一次投递时另开服务端任务。
- 回执丢失/文章过期不自动重推历史稿件，说明可核查范围。
- 业务迁移前保留旧契约测试；回滚恢复入口，不删除公共回执。
- 工作区已有未提交 finance-macro/csi300-brief/，属于其他工作，不覆盖。

## 规划检查

- [x] 创建 planning 任务，填写需求、设计和实施步骤。
- [x] 对照 API 明确幂等、频道、列表上限和保留期限制。
- [x] PRD 已按需求与验收结构收敛，未保留重复讨论段落。
- [x] 用户确定本期迁移全部现有来源。
- [x] 用户已要求实施，全部 8 类来源源码迁移及跨平台验证完成。生产部署不在本期范围；未提交或归档。

## 最终验收

详见 verification.md。Windows 共 140 项测试通过；WSL Ubuntu 的公共核心 22 项及客户端 3 项通过；Ruff F/E9、技能结构校验及 diff 空白检查通过。只使用本地假服务，没有真实投递或部署。
