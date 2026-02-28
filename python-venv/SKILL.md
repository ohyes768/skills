# Python项目虚拟环境初始化

在Python项目初始化时，自动创建`.venv`虚拟环境，配置所有Python依赖使用虚拟环境安装。

## 适用场景

检测到以下特征时启用：
- 项目包含 `requirements.txt` 或 `pyproject.toml` 文件
- 项目包含 `*.py` Python文件
- 用户明确表示这是Python项目

## 核心原则

1. **虚拟环境优先**: 所有Python项目都使用`.venv`虚拟环境隔离依赖
2. **自动安装**: 自动创建虚拟环境并安装依赖
3. **脚本工具**: 创建便捷的初始化和运行脚本
4. **跨平台**: 支持Windows、Linux、Mac

## 执行步骤

### 步骤1: 检查现有虚拟环境

```bash
# 检查.venv是否已存在
if [ -d ".venv" ]; then
    echo "虚拟环境已存在，跳过创建"
else
    echo "开始创建虚拟环境..."
fi
```

### 步骤2: 创建虚拟环境

**Windows**:
```batch
python -m venv .venv
```

**Linux/Mac**:
```bash
python3 -m venv .venv
# 或使用uv（如果可用）
uv venv .venv
```

### 步骤3: 确保pip可用

```bash
# Windows
.venv\Scripts\python.exe -m ensurepip --default-pip

# Linux/Mac
.venv/bin/python -m ensurepip --default-pip
```

### 步骤4: 安装依赖

**如果存在 requirements.txt**:
```bash
# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Linux/Mac
.venv/bin/python -m pip install -r requirements.txt
```

**如果存在 pyproject.toml**:
```bash
# Windows
.venv\Scripts\python.exe -m pip install -e .

# Linux/Mac
.venv/bin/python -m pip install -e .
```

### 步骤5: 安装Playwright浏览器（如果需要）

检测是否需要：
- 如果`requirements.txt`包含`playwright`
- 或者项目是web爬虫/自动化项目

```bash
# Windows
.venv\Scripts\python.exe -m playwright install chromium

# Linux/Mac
.venv/bin/python -m playwright install chromium
```

### 步骤6: 创建便捷脚本

**Windows - 初始化脚本 (`scripts/setup.bat`)**:
```batch
@echo off
echo ==========================================
echo Python项目虚拟环境初始化
echo ==========================================

REM 检查Python是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.10+
    exit /b 1
)

if not exist ".venv" (
    echo 创建虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo 错误: 虚拟环境创建失败
        exit /b 1
    )
)

REM 检查虚拟环境Python是否可用
.venv\Scripts\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 虚拟环境Python不可用
    exit /b 1
)

echo 安装依赖...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo 错误: 依赖安装失败
    exit /b 1
)

echo 安装完成！
echo 使用方法: .venv\Scripts\python.exe xxx.py
pause
```

**Linux/Mac - 初始化脚本 (`scripts/setup.sh`)**:
```bash
#!/bin/bash
set -e  # 遇到错误立即退出

echo "=========================================="
echo "Python项目虚拟环境初始化"
echo "=========================================="

# 检查Python是否可用
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到python3，请先安装Python 3.10+"
    exit 1
fi

# 显示Python版本
echo "检测到Python版本: $(python3 --version)"

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv .venv
    echo "✓ 虚拟环境创建成功"
fi

# 验证虚拟环境Python
if [ ! -f ".venv/bin/python" ]; then
    echo "错误: 虚拟环境Python不可用"
    exit 1
fi

# 安装依赖
echo "安装依赖..."
if [ -f "requirements.txt" ]; then
    .venv/bin/python -m pip install -r requirements.txt
    echo "✓ 依赖安装完成"
else
    echo "警告: 未找到requirements.txt，跳过依赖安装"
fi

echo ""
echo "=========================================="
echo "✓ 初始化完成！"
echo "=========================================="
echo ""
echo "使用方法:"
echo "  .venv/bin/python your_script.py"
echo ""
```

### 步骤7: 创建运行脚本

**Windows (`scripts/run.bat`)**:
```batch
@echo off
call .venv\Scripts\activate.bat
python %*
```

**Linux/Mac (`scripts/run.sh`)**:
```bash
#!/bin/bash
.venv/bin/python "$@"
```

### 步骤8: 更新.gitignore

确保`.gitignore`包含：
```gitignore
.venv/
venv/
__pycache__/
*.pyc
*.egg-info/
```

### 步骤9: 创建README说明

添加到README.md：
```markdown
## 虚拟环境

本项目使用`.venv`虚拟环境。

### 初始化

```bash
# Windows
scripts\setup.bat

# Linux/Mac
bash scripts/setup.sh
```

### 使用

```bash
# Windows
.venv\Scripts\python.exe your_script.py

# Linux/Mac
.venv/bin/python your_script.py
```

### 安装新依赖

```bash
# Windows
.venv\Scripts\python.exe -m pip install package_name

# Linux/Mac
.venv/bin/python -m pip install package_name
```
```

## 输出成果

执行完成后应生成：

1. **虚拟环境目录**:
   - `.venv/` - 虚拟环境根目录
   - `.venv/Scripts/` (Windows) 或 `.venv/bin/` (Linux/Mac)

2. **脚本工具**:
   - `scripts/setup.bat` - Windows初始化脚本
   - `scripts/setup.sh` - Linux/Mac初始化脚本
   - `scripts/run.bat` - Windows运行脚本
   - `scripts/run.sh` - Linux/Mac运行脚本

3. **配置文件**:
   - `.gitignore` - 包含虚拟环境忽略规则
   - `README.md` - 添加虚拟环境使用说明

## 注意事项

1. **始终使用虚拟环境运行Python脚本**
   ```bash
   # 正确 ✓
   .venv\Scripts\python.exe script.py

   # 错误 ✗
   python script.py
   ```

2. **不要提交.venv到Git**
   - 已在.gitignore中配置
   - 团队成员运行初始化脚本即可

3. **依赖更新后重新安装**
   ```bash
   .venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
   ```

4. **跨平台路径兼容**
   - Windows: `.venv\Scripts\python.exe`
   - Linux/Mac: `.venv/bin/python`

## 与其他skill的配合

- **ask-me**: 先用ask-me了解需求，再用python-venv初始化Python环境
- **git-commit-push**: 初始化完成后，提交代码到Git仓库

## 示例对话

**用户**: "创建一个Python爬虫项目"

**Claude**:
1. (ask-me skill) 深入了解需求
2. 创建项目结构
3. (python-venv skill) 自动初始化虚拟环境
4. 创建requirements.txt
5. 运行setup脚本安装依赖
6. 创建README说明

**用户**: "这个项目需要用到playwright"

**Claude**:
1. 检测到playwright依赖
2. 创建虚拟环境
3. 安装playwright和浏览器
4. 测试环境是否正常

## 技术细节

### 检测是否需要安装playwright

```python
import os

def needs_playwright():
    """检测是否需要安装playwright浏览器"""
    # 检查requirements.txt
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            content = f.read()
            if 'playwright' in content:
                return True

    # 检查是否是web自动化项目
    py_files = [f for f in os.listdir('.') if f.endswith('.py')]
    for py_file in py_files[:5]:  # 检查前5个文件
        with open(py_file, 'r') as f:
            content = f.read()
            if 'playwright' in content or 'selenium' in content:
                return True

    return False
```

### 平台检测

```python
import platform

def get_python_path():
    """获取虚拟环境Python路径"""
    system = platform.system()

    if system == 'Windows':
        return '.venv\\Scripts\\python.exe'
    else:  # Linux, Darwin, etc.
        return '.venv/bin/python'

def get_pip_path():
    """获取虚拟环境pip路径"""
    system = platform.system()

    if system == 'Windows':
        return '.venv\\Scripts\\pip.exe'
    else:
        return '.venv/bin/pip'
```

### 验证安装

```python
def verify_installation():
    """验证虚拟环境是否正确安装"""
    python_path = get_python_path()

    # 检查Python是否可用
    result = os.system(f'{python_path} --version')
    if result != 0:
        return False

    # 检查关键包是否安装
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            packages = [line.split('==')[0].strip() for line in f if line.strip() and not line.startswith('#')]

        for pkg in packages:
            result = os.system(f'{python_path} -c "import {pkg}; print()"')
            # 静默处理导入错误

    return True
```

## 故障排查

### 问题1: 虚拟环境创建失败

**可能原因**: Python未安装或不在PATH中

**解决方案**:
```bash
# 检查Python
python --version
python3 --version

# 使用完整路径
C:\Python313\python.exe -m venv .venv
```

### 问题2: pip安装失败

**可能原因**: 网络问题或依赖包不存在

**解决方案**:
```bash
# 使用国内镜像
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 或者手动逐个安装
.venv\Scripts\python.exe -m pip install playwright
```

### 问题3: Playwright浏览器下载失败

**可能原因**: 网络问题或防火墙阻止

**解决方案**:
```bash
# 设置镜像
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright

# 然后安装
.venv\Scripts\python.exe -m playwright install chromium
```

## 最佳实践

1. **项目根目录保持简洁**
   - `.venv/` 在根目录
   - `requirements.txt` 在根目录
   - `scripts/` 目录存放工具脚本

2. **依赖版本固定**
   - 使用 `package==version` 格式
   - 确保团队成员环境一致

3. **开发依赖分离**
   - `requirements.txt` - 生产依赖
   - `requirements-dev.txt` - 开发依赖（可选）

4. **定期更新依赖**
   ```bash
   .venv\Scripts\python.exe -m pip list --outdated
   .venv\Scripts\python.exe -m pip install --upgrade package_name
   ```

5. **清理虚拟环境**
   ```bash
   # Windows
   rmdir /s /q .venv

   # Linux/Mac
   rm -rf .venv

   # 然后重新初始化
   scripts/setup.bat  # 或 bash scripts/setup.sh
   ```

## 依赖项目规则

遵循用户的全局指令：
- **Python虚拟环境**: 永远使用 `.venv` 作为目录名
- **包管理**: 优先使用 `uv`，其次是 `.venv/Scripts/python.exe -m pip`
- **项目根目录**: 保持简洁，只保留必须存在的文件

## 示例模板

### requirements.txt 模板

```txt
# Web自动化/爬虫
playwright==1.48.0
beautifulsoup4==4.12.3
httpx==0.27.0

# 数据处理
pandas==2.0.0
numpy==1.24.0

# 配置管理
pyyaml==6.0.1
python-dotenv==1.0.1
```

### setup.bat 模板

```batch
@echo off
REM Python项目虚拟环境初始化

echo 初始化Python虚拟环境...

REM 检查Python是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.10+
    exit /b 1
)

REM 创建虚拟环境
if not exist ".venv" (
    echo 创建.venv虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo 错误: 虚拟环境创建失败
        exit /b 1
    )
)

REM 验证虚拟环境
.venv\Scripts\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 虚拟环境Python不可用
    exit /b 1
)

REM 安装依赖
echo 安装项目依赖...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo 错误: 依赖安装失败
    exit /b 1
)

REM 安装playwright浏览器（如果需要）
findstr /C:"playwright" requirements.txt >nul
if %errorlevel%==0 (
    echo 安装Playwright浏览器...
    .venv\Scripts\python.exe -m playwright install chromium
)

echo.
echo ==========================================
echo ✓ 初始化完成！
echo ==========================================
echo.
echo 使用方法:
echo   .venv\Scripts\python.exe your_script.py
echo.

pause
```

## 验收标准

虚拟环境初始化成功的标志：

1. ✅ `.venv/` 目录存在
2. ✅ 可以运行 `.venv/Scripts/python.exe --version`
3. ✅ `requirements.txt` 中的依赖都已安装
4. ✅ 如果需要playwright，浏览器已安装
5. ✅ `scripts/setup.bat` 和 `scripts/setup.sh` 已创建
6. ✅ `.gitignore` 已更新
7. ✅ README.md 中添加了使用说明

## 后续支持

虚拟环境创建后，可以：

1. **添加开发环境配置**
   - VSCode配置
   - PyCharm配置

2. **配置测试框架**
   - pytest配置
   - unittest配置

3. **设置代码格式化**
   - black配置
   - flake8配置

4. **集成CI/CD**
   - GitHub Actions配置
   - 自动化测试和部署
