---
name: git-commit-push
description: >
  用于用户要求生成 Git commit message、提交代码、commit、推送、push、保存到 Git、上传 GitHub
  或 commit and push 时。仅评审 skill、讨论改动不代表授权提交；只要求 commit 不自动 push，
  只要求 push 不自动创建 commit。
allowed-tools: Shell, Read, Grep, Write
---

# Git 自动提交和推送

识别模式 → 检查状态 → 只读本次提交范围 → 简单 message 直接提交 → 按要求推送 → 精简确认结果。

必需环境仅为 Git 和当前系统已有的 shell。Windows 使用当前 PowerShell，macOS 使用当前 Bash/zsh；不要求安装或检查 `gh`、Python、Node.js，不为本流程切换 shell。GitHub PR 等操作不属于本 skill。

## 1. 识别模式

| 用户意图 | 行为 |
|----------|------|
| 「写 commit message」「拟提交说明」「先别提交」 | 可只读检查，输出 message；不 add、commit、push |
| 「提交」「commit」「帮我提交代码」 | 按范围 add（需要时）+ commit；不 push |
| 「只推送」「push 已有提交」 | 只检查推送目标并 push；不 add、commit，不分析工作区 diff |
| 「提交并推送」「commit and push」「把这些改动推到 GitHub」 | 按范围提交，再 push |

单独要求「推送」默认只推已有提交；若措辞无法确定是否包含提交工作区改动，先只读检查再澄清，不擅自扩大范围。

## 2. 检查状态

```sh
git status --porcelain=v1 --branch --untracked-files=normal
```

- 区分 `##` 分支头与文件条目；只有分支头表示工作区干净。ahead/behind 是本地跟踪信息，不保证远程实时状态。
- 工作区干净只表示无需创建 commit；用户要求 push 时仍进入第 5 步。仅 push 模式在检查目标后直接进入第 5 步，即使工作区有未提交改动。
- 发现冲突或尚未完成的 merge/rebase，先说明状态，不自行继续操作或新建普通提交。detached HEAD 不自行选择推送分支。
- 仅在需要判断提交风格且上下文尚未提供时，读取 `git --no-pager log -3 --format='%s'`；全新仓库没有历史是正常情况。

独立只读检查可合并到一轮工具调用。不要固定并行读取所有 diff；add、commit、push 有依赖，必须顺序执行并检查各自退出码。

## 3. 只读本次提交范围

- 用户指定路径或暂存区时，以该范围为准。未指定范围且已有 staged 改动，默认只提交现有暂存内容，跳过 add；尤其不要对部分暂存文件重新 add。
- 用户指定范围与现有暂存范围不一致时，先澄清；普通 `git commit` 会提交整个暂存区，不自动 reset 暂存区或用其他命令替用户改变选择。
- 没有 staged 改动时，从状态确定本次候选路径；未跟踪目录需按需展开，读取拟加入的新文件内容，普通 `git diff` 不包含它们。
- 小改动直接读取目标 diff；大改动才先看同一范围的 `--name-status` / `--stat`，再按路径阅读。避免机械地先统计再完整读取全部内容；输出被截断时按文件补读，不据此猜测。

```sh
# 已暂存：只读暂存区内容
git --no-pager diff --cached --no-ext-diff --no-textconv
# 未暂存：将下列示例路径替换为本次候选路径
git --no-pager diff --no-ext-diff --no-textconv -- 'src/main.ts' 'README.md'
```

禁用外部 diff/textconv 可避免额外程序；如本次包含需转换才能理解的二进制文件，按需单独检查。`--stat` 主要缩减输出，不保证计算更快；不默认使用隐藏新文件的 `status -uno`。脚本解析路径时用 `-z` 并正确处理 NUL，不按空格拆分文件名。

只对本次拟提交内容检查敏感信息；涉及 `.env`、`credentials.json`、`*.pem`、`secrets.*` 等文件时列出路径并暂停，除非用户已明确确认。不要在输出中展示密钥内容。

## 4. 简单 message 直接提交

使用 Conventional Commits：`type(scope): 中文简短描述`，scope 可省略，正文仅在需要解释原因时添加。常用 type：`feat`、`fix`、`docs`、`refactor`、`perf`、`test`、`chore`；参考仓库已有风格。

只在有待加入的授权路径时，一次执行 `git add -- '路径1' '路径2'`，不要逐文件启动 Git，也不要盲目 `git add .` / `git add -A`。add 成功后核对本次 staged 路径与范围；已有 diff 仍准确时不重复全文读取，有变化则补读相关 staged diff。文件名含通配符时使用 `git --literal-pathspecs add -- ...`。

简单说明直接使用 `-m`，例如以下命令可用于 PowerShell、Bash 和 zsh：

```sh
git commit -m 'docs(skill): 优化提交流程'
```

多个简单段落可重复 `-m`。含复杂引号、变量符号、反引号或多行正文时，读取 [references/commit-message-shell.md](references/commit-message-shell.md)，使用 UTF-8 无 BOM 的系统临时文件 + `git commit -F`；不写死 `.git/...`，以兼容 worktree。按当前 shell 正确转义，不把 message 当可执行脚本拼接。

仅按需读取格式参考：[type / scope / subject](references/commit-types.md)（规则不确定时）、[body 模板](references/templates.md)（需要结构化正文时）、[完整示例](references/examples.md)（需要示例时），不默认全部加载。

commit 失败立即停止后续 push，并保留原始失败状态；清理临时文件不能掩盖失败。hook 失败先检查 HEAD 是否已变化及 hook 是否修改文件；需要修复时重新审阅、暂存相关内容，再正常重试 commit，不擅自 amend 或绕过 hook。

## 5. 按要求推送

仅在用户要求 push 时执行。当前分支、目标远程与目标分支已明确且符合用户意图时，使用 `git push`；目标尚不明确时，按需读取远程和分支配置，不每次固定执行 `git remote -v`，也不先增加一次网络请求来探测远程。

新分支无 upstream 时，在已确认远程和分支符合用户意图后用 `git push -u <remote> HEAD`，不要默认远程一定叫 `origin`。缺少目标信息时询问，不自动添加远程。已有 upstream 不保证默认 push 配置只推一个分支；有自定义 push refspec 等情况时使用明确的远程和 refspec。

根据实际错误处理：认证失败检查凭据，网络失败报告连接问题；只有 non-fast-forward 时才检查远程历史并讨论合并/rebase，不对所有失败统一建议 `git pull --rebase`，不盲目循环重试。

## 6. 精简确认结果

提交后运行 `git status --porcelain=v1 --untracked-files=normal` 核对剩余改动；需要获取 hash 和摘要时运行 `git --no-pager show -s --format='%h %s' HEAD`，不读取完整作者和日期信息。push 以退出码和远程返回结果为依据，不额外 fetch / ls-remote 验证；失败就明确报告未推送。

最终只报告 commit hash、message 摘要、是否推送；有剩余改动或失败时补充实际情况。只生成 message 模式直接输出说明；只 push 模式无需重新读取提交全文。

## 安全约束

- 未明确要求不 commit、不 push；不通过创建分支、安装工具等方式扩大任务范围。
- 不修改 Git 配置，不为提速关闭 hook、签名或安全检查。
- 禁止默认使用 `--force`、`--no-verify`、`--no-gpg-sign`、`commit --amend`；仅在用户明确授权对应操作且条件适用时例外。
- 不使用交互式 Git 命令；保留用户的部分暂存选择和范围外改动。
