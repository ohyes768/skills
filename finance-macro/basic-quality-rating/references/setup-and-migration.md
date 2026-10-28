# 安装与旧手册迁移

本页用于部署/同步维护，不是每次公司分析的前置研究步骤。

## 环境准备

全部脚本只依赖 Python 3 标准库，使用现有 Python ≥3.12 直接运行即可。
不需要 uv sync、pip install、PDF 解析库或兄弟 skill 的目录布局。
v3.5 已移除 PDF 下载、解析、缓存和银行/保险候选定位命令；旧调用应改用
已有结构化数据或宿主读取的官方网页/公告正文，按来源与口径填入行业证据包。
v3.7.0 禁止 PDF 取证（含宿主工具、其他 skill 和 PDF 缓存），仅使用结构化候选与可读网页正文。
每维允许初查加四轮网页补查，仍缺核心证据时明确未评级；全局预算及交付预留继续有效。
评分合同、模板、财务评分与统一校验命令保持兼容。升级安装副本时应清理旧版本残留工具，
不能将新旧目录叠加后继续执行旧 PDF 命令。

## 废止远程旧执行手册

已知旧 `quality-rating-pipeline-runbook` 含过时的 PDF 优先、整数占位、逐项反算和第二套校验规则。
主 skill 禁止 PDF 取证，不恢复旧手册流程；升级部署时一并迁移旧手册，避免两套规则并存。
新主 skill 不再加载它。为保留旧命令调用兼容，可在获得同步/部署授权后执行一次迁移：

```text
python3 <主skill目录>/scripts/retire_legacy_runbook.py --runbook-dir <旧runbook目录> --skill-dir <主skill目录>
```

默认只预览待改路径，不修改文件。确认路径后加 `--apply`：

```text
python3 <主skill目录>/scripts/retire_legacy_runbook.py --runbook-dir <旧runbook目录> --skill-dir <主skill目录> --apply
```

工具核对旧 skill 名称及新校验器存在，将 SKILL.md 和旧校验脚本备份为同目录的 `.pre-unification.bak`，
把旧手册改成退役入口，把旧校验命令转发到主 skill，复用同一规则。
不会删除文件、修改调用端或重启服务；已有不同版本备份时停止，避免覆盖历史。
重复运行同一迁移无变化。主 skill 移动后，需重装转发入口，或设置 `BASIC_QUALITY_RATING_DIR` 为新目录。
旧命令的输出将统一为主校验器的 JSON，错误退出码为 2；依赖旧文字输出/退出码 1 的脚本须相应适配。

迁移前先检查 nullable 调用端兼容性；本仓库开发完成不代表安装、NAS 同步或 Web 消费端已完成升级。
