# Python 虚拟环境自动初始化

这是一个 Claude Code 自定义 skill，用于在 Python 项目中自动创建 `.venv` 虚拟环境并配置所有依赖。

## 功能特性

- ✅ **自动检测** - 检测 Python 项目特征（requirements.txt、*.py 文件）
- ✅ **跨平台** - 支持 Windows、Linux、Mac
- ✅ **脚本生成** - 自动创建初始化和运行脚本
- ✅ **依赖管理** - 自动安装 pip 和项目依赖
- ✅ **Playwright 支持** - 自动检测并安装浏览器
- ✅ **完整文档** - 生成 README 和 .gitignore 配置

## 为什么需要这个 skill？

**Python 项目中的常见问题**：
- 依赖管理混乱，直接使用系统 Python
- 团队成员环境不一致，"在我机器上能跑"
- 虚拟环境配置繁琐，每次都要手动创建
- 跨平台路径问题（Windows vs Linux/Mac）

这个 skill 通过**自动化虚拟环境初始化**，确保：
- ✅ 所有 Python 项目使用 `.venv` 隔离依赖
- ✅ 自动生成便捷的初始化脚本
- ✅ 统一的依赖管理方式
- ✅ 跨平台兼容

## 使用方法

### 自动触发

当检测到以下情况时，Claude 会自动启用这个 skill：
- 项目包含 `requirements.txt` 或 `pyproject.toml` 文件
- 项目包含 `*.py` Python 文件
- 用户明确表示这是 Python 项目

### 显式调用

在对话中说：
- "初始化 Python 虚拟环境"
- "创建 .venv"
- "配置 Python 项目环境"

## 示例对话

```
用户: 创建一个 Python 爬虫项目

Claude: [自动触发 python-venv skill]
1. 创建项目结构
2. 生成 requirements.txt
3. 创建 .venv 虚拟环境
4. 生成 scripts/setup.bat 和 scripts/setup.sh
5. 安装依赖（包括 playwright）
6. 更新 .gitignore
7. 创建 README 说明

✓ 虚拟环境初始化完成！
使用方法: .venv\Scripts\python.exe your_script.py
```

## 生成的文件结构

```
your-project/
├── .venv/                    # 虚拟环境（自动创建）
│   ├── Scripts/             # Windows 可执行文件
│   │   ├── python.exe
│   │   └── pip.exe
│   └── bin/                 # Linux/Mac 可执行文件
│       ├── python
│       └── pip
├── scripts/                  # 便捷脚本（自动生成）
│   ├── setup.bat            # Windows 初始化脚本
│   ├── setup.sh             # Linux/Mac 初始化脚本
│   ├── run.bat              # Windows 运行脚本
│   └── run.sh               # Linux/Mac 运行脚本
├── requirements.txt          # 依赖列表
├── .gitignore               # Git 忽略规则（自动更新）
└── README.md                # 使用说明（自动更新）
```

## 核心原则

### 1. 虚拟环境优先
所有 Python 项目都使用 `.venv` 虚拟环境隔离依赖

### 2. 自动安装
自动创建虚拟环境并安装依赖，无需手动操作

### 3. 脚本工具
创建便捷的初始化和运行脚本，简化日常使用

### 4. 跨平台兼容
支持 Windows、Linux、Mac，自动适配路径差异

## 使用方式

### 初始化项目

**Windows**:
```batch
scripts\setup.bat
```

**Linux/Mac**:
```bash
bash scripts/setup.sh
```

### 运行 Python 脚本

**Windows**:
```batch
.venv\Scripts\python.exe your_script.py
```

**Linux/Mac**:
```bash
.venv/bin/python your_script.py
```

### 安装新依赖

**Windows**:
```batch
.venv\Scripts\python.exe -m pip install package_name
```

**Linux/Mac**:
```bash
.venv/bin/python -m pip install package_name
```

## 技术细节

### 虚拟环境创建

**优先级**：
1. **uv** (如果可用) - 快速的 Python 包管理器
2. **python -m venv** - 标准库内置方式

### 依赖安装

**命令格式**：
```bash
# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Linux/Mac
.venv/bin/python -m pip install -r requirements.txt
```

**为什么使用 `python -m pip` 而不是直接 `pip`**：
- ✅ 明确指定使用虚拟环境中的 pip
- ✅ 避免激活虚拟环境（更可靠）
- ✅ 跨平台兼容性更好

### Playwright 浏览器安装

**自动检测条件**：
- `requirements.txt` 包含 `playwright`
- 项目是 web 自动化/爬虫项目

**安装命令**：
```bash
# Windows
.venv\Scripts\python.exe -m playwright install chromium

# Linux/Mac
.venv/bin/python -m playwright install chromium
```

## 错误处理

### Windows 脚本 (setup.bat)
- ✅ Python 可用性检查
- ✅ 虚拟环境创建验证
- ✅ 依赖安装错误处理
- ✅ 友好的错误提示

### Linux/Mac 脚本 (setup.sh)
- ✅ `set -e` 错误时立即退出
- ✅ Python3 可用性检查
- ✅ requirements.txt 存在性检查
- ✅ 清晰的成功/失败提示

## 常见问题

**Q: 为什么使用 .venv 而不是 venv？**
A: 遵循 Python 社区惯例，`.` 开头表示隐藏目录，`venv` 明确含义

**Q: 可以不使用虚拟环境吗？**
A: 强烈不推荐。虚拟环境可以隔离依赖，避免版本冲突

**Q: 如何清理虚拟环境？**
A:
```bash
# Windows
rmdir /s /q .venv

# Linux/Mac
rm -rf .venv
```

**Q: 网络问题导致依赖安装失败怎么办？**
A: 使用国内镜像：
```bash
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

## 文件结构

```
python-venv/
├── SKILL.md       # Skill 定义文件（Claude 读取并执行）
└── README.md      # 说明文档（你正在阅读）
```

## 自定义

你可以编辑 `SKILL.md` 文件来自定义：
- 虚拟环境目录名（默认 `.venv`）
- 初始化脚本模板
- 依赖安装方式
- 错误处理逻辑

## 与其他 skill 的配合

- **ask-me**: 先用 ask-me 了解需求，再用 python-venv 初始化环境
- **git-commit-push**: 初始化完成后，提交代码到 Git 仓库

## 验收标准

虚拟环境初始化成功的标志：
1. ✅ `.venv/` 目录存在
2. ✅ 可以运行 `.venv/Scripts/python.exe --version`
3. ✅ `requirements.txt` 中的依赖都已安装
4. ✅ 如果需要 playwright，浏览器已安装
5. ✅ `scripts/setup.bat` 和 `scripts/setup.sh` 已创建
6. ✅ `.gitignore` 已更新
7. ✅ README.md 中添加了使用说明

## 注意事项

1. **始终使用虚拟环境运行 Python 脚本**
   ```bash
   # 正确 ✓
   .venv\Scripts\python.exe script.py

   # 错误 ✗
   python script.py
   ```

2. **不要提交 .venv 到 Git**
   - 已在 .gitignore 中配置
   - 团队成员运行初始化脚本即可

3. **定期更新依赖**
   ```bash
   .venv\Scripts\python.exe -m pip list --outdated
   .venv\Scripts\python.exe -m pip install --upgrade package_name
   ```

## 反馈与改进

如果这个 skill 对你有帮助，或者有改进建议，欢迎反馈！
