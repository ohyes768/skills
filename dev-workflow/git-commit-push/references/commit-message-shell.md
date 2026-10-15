# 复杂提交说明的跨平台写入

仅在 `-m` 难以可靠表达 message 时读取。选择当前 shell 的示例，将说明替换为已审阅的内容；不需要安装其他运行时。

临时文件使用系统临时目录，与 `.git` 的目录/文件形态无关。将提交作为独立工具调用，检查返回码后再决定是否 push；以下示例清理后仍返回原 commit 退出码。

## PowerShell 5.1 / 7（Windows）

单引号 here-string 保留 `$变量` 和反引号原文。使用 .NET 显式写入 UTF-8 无 BOM，避免 PowerShell 5.1 不支持 `-Encoding utf8NoBOM`。如保存为含中文的 `.ps1` 文件并用 5.1 执行，脚本本身应使用 UTF-8 BOM；message 临时文件仍无 BOM。

```powershell
$msg = @'
docs(skill): 优化提交流程

保留 $HOME 与 `反引号` 原文，兼容 worktree。
'@
$msgPath = [System.IO.Path]::GetTempFileName()
$commitExit = 1
try {
    [System.IO.File]::WriteAllText($msgPath, $msg, [System.Text.UTF8Encoding]::new($false))
    git commit -F $msgPath
    $commitExit = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $msgPath -ErrorAction SilentlyContinue
}
exit $commitExit
```

here-string 结束标记 `'@` 必须独占一行且从行首开始。若 message 本身含这样的行，使用文件写入工具生成原始 UTF-8 内容，避免直接插入模板。

## Bash / zsh（macOS、Git Bash）

引号包裹的 heredoc 分隔符禁止变量与命令替换；括号将 `exit` 和清理 trap 限制在本次提交的子 shell 内。

```sh
(
    msg_path=$(mktemp) || exit 1
    trap 'rm -f -- "$msg_path"' EXIT
    cat > "$msg_path" <<'COMMIT_MESSAGE_EOF'
docs(skill): 优化提交流程

保留 $HOME 与 `反引号` 原文，兼容 worktree。
COMMIT_MESSAGE_EOF
    if [ "$?" -ne 0 ]; then exit 1; fi
    git commit -F "$msg_path"
    exit "$?"
)
```

选择一个不会作为 message 独立行出现的分隔符。不要将此示例和后续 push 无条件串接；父 shell 或工具调用方必须检查该子 shell 的退出码。
