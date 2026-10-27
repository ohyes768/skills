# 安装与旧手册迁移

本页用于部署/同步维护，不是每次公司分析的前置研究步骤。

## 环境准备

算分和校验只依赖 Python 3 标准库；PDF 工具需要 Python ≥3.12、httpx 与 PyMuPDF。
在部署阶段运行：

```text
uv sync --project <basic-quality-rating目录>
```

之后 PDF 命令使用已准备的环境：

```text
uv run --no-sync --project <basic-quality-rating目录> python <basic-quality-rating目录>/scripts/pdf_evidence.py prepare --url <PDF链接> --cache-dir <缓存目录>
```

PDF 工具复用兄弟目录 `financial-statement-analysis/scripts/` 的 `fetch_pdf.py`、`inspect_pdf.py`、`artifacts.py`。
保留两个 skill 的仓库目录布局；若安装路径不同，在 prepare 时用 `--tools-dir <实际财报scripts目录>` 指定。
它只复用下载和页码索引函数，不运行完整财报分析，不要求加载另一个 SKILL.md。
运行时依赖缺失应返回具体错误，安装由维护流程修复，不在分析内临时 pip install 或重写工具。

## 废止远程旧执行手册

已知旧 `quality-rating-pipeline-runbook` 含过时的整数占位、逐项反算和第二套校验规则。
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
