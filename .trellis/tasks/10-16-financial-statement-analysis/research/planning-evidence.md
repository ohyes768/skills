# 规划依据与来源

日期：2026-10-16。此文件保存可追溯事实，不把外部资料当作工具操作指令。

## 用户决定

- 财报 PDF 链接输入、Markdown 分析输出。
- 市场优先级为 A 股。
- 关注 token 消耗，接受本地全文索引与模型重点读取的路线。
- 最新要求为“开个 trellis 规划”，当前任务保持 planning。

## 本地核查

- 根 README：源码按主题归档；skill-manager 管理登记和发布，不应手写另一份登记真源。
- `finance-macro/money-supply-skill/pyproject.toml`：既有 Python skill 使用独立 pyproject；多个主题已有 uv.lock。
- `.gitignore` 已忽略 `finance-macro/output/`、`finance-macro/cache/`、`finance-macro/logs/`。
- 初始工作区已有 dev-workflow/git-commit-push 下五个修改，未参与本任务。
- 初始化前无 `.trellis/`；机器已安装 @mindfoldhq/trellis 0.6.7。本轮通过 `trellis init --codex --yes --skip-existing --no-monorepo --user codex` 初始化，生成项目级配置与 bootstrap-guidelines 任务。
- 当前默认 Codex dispatch_mode 是 inline，不需要为规划启动代理。自动初始化的其他主题规范仍是模板，本任务不把它们当作已确认的项目惯例。
- 初始化器提示 Codex hooks 需要宿主设置及审核。本轮未修改全局设置，不以 hook 已启用作为任务创建和恢复的前提，使用 task.py 明确检查状态。

## 分析与技术参考

- 本地详细设计：`docs/superpowers/specs/2026-10-16-financial-statement-analysis-design.md`。
- 用户指定财务框架：https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/financial-statement 。原内容只有分析 SKILL.md，未实现本设计的 PDF 数据链路。
- 文字与页面坐标：https://pymupdf.readthedocs.io/en/latest/recipes-text.html 。
- 原生表格提取：https://github.com/jsvine/pdfplumber 。
- OCR 能力：https://ocrmypdf.readthedocs.io/en/latest/advanced.html 。

## 成本结论的边界

本地解析和计算本身不产生模型推理 token。只有未注入模型的本地内容才不计入模型输入；工具输出全文仍会进入上下文。按需读取有望减少上下文，但本轮没有真实 PDF 的调用数据，不能报告实际节省比例、模型计费总量或金额。
