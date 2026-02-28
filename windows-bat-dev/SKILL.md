# Windows 批处理脚本开发最佳实践

## 技能说明

在编写 Windows 批处理脚本（.bat/.cmd）时，遵循以下最佳实践，避免常见的编码和路径问题。

## 核心原则

### 1. 编码问题 - 全英文（最重要）

**问题**：批处理文件默认使用系统 ANSI 编码，中文字符会显示为乱码

**黄金法则**：
- ✅ **所有输出、注释、提示必须使用纯英文**
- ❌ 绝不在批处理文件中使用任何中文字符
- ❌ 不要使用 `chcp 65001`（可能引发其他问题）

```bat
# 错误示例 - 包含中文
@echo off
echo 安装依赖
echo 错误: uv 未安装
REM 检查环境

# 正确示例 - 全英文
@echo off
echo Installing dependencies
echo ERROR: uv not installed
REM Check environment
```

**英文命名对照表**：
| 中文 | 英文 |
|------|------|
| 安装 | Install / Setup |
| 配置 | Config / Configuration |
| 启动 | Start / Run |
| 停止 | Stop |
| 错误 | ERROR |
| 警告 | WARNING |
| 成功 | SUCCESS / OK |
| 失败 | FAILED |
| 检查 | Check / Checking |
| 下载 | Download |
| 编译 | Build / Compile |
| 清理 | Clean / Cleanup |
| 部署 | Deploy / Deployment |

### 2. 路径问题 - 始终从脚本位置定位

**问题**：用户可能从任何目录运行脚本，相对路径会失效

**解决方案**：
- ✅ 脚本开头添加 `cd /d "%~dp0.."` 切换到项目根目录
- ✅ `%~dp0` = 脚本所在目录
- ✅ `%~dp0..` = 脚本的父目录（项目根目录）

```bat
# 始终在脚本开头添加
cd /d "%~dp0.."
```

**路径符号说明**：
| 符号 | 含义 |
|------|------|
| `%~dp0` | 脚本所在目录（带驱动器和末尾反斜杠） |
| `%~dp0..` | 脚本的父目录 |
| `%~dp0..\config` | 父目录下的 config |
| `cd /d` | 切换目录（`/d` 允许跨驱动器） |

### 3. 错误检查 - 验证文件和命令存在性

```bat
REM Check if command exists
where go >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Go not found
    pause
    exit /b 1
)

REM Check if file exists
if not exist "config.yaml" (
    echo ERROR: config.yaml not found
    pause
    exit /b 1
)

REM Check if directory exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found
    pause
    exit /b 1
)
```

### 4. 进度提示 - 让用户知道执行状态

```bat
echo [1/5] Checking Go environment...
echo [2/5] Setting build environment...
echo [3/5] Downloading dependencies...
echo [4/5] Cleaning old files...
echo [5/5] Building...
```

## 脚本模板

### 通用安装脚本模板

```bat
@echo off
REM Install dependencies script

REM Change to project root
cd /d "%~dp0.."

echo ============================================
echo Installing dependencies
echo ============================================
echo.

REM Check required command
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: uv not installed
    echo Please install: pip install uv
    pause
    exit /b 1
)

REM Create virtual environment if not exists
if not exist ".venv" (
    echo Creating virtual environment...
    uv venv
)

REM Install dependencies
echo Installing dependencies...
uv pip install -e .

echo.
echo ============================================
echo Installation complete
echo ============================================

pause
```

### 通用启动脚本模板

```bat
@echo off
REM Startup script

REM Change to project root
cd /d "%~dp0.."

echo ============================================
echo Starting application
echo ============================================
echo.

REM Check required file
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found
    echo Please run: scripts\install.bat
    pause
    exit /b 1
)

REM Run main program
.venv\Scripts\python.exe main.py

pause
```

### 通用编译脚本模板

```bat
@echo off
REM Build script

REM Change to project root
cd /d "%~dp0.."

echo.
echo ======================================
echo   Build Script
echo ======================================
echo.

REM Check build tool
where go >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Go not found
    pause
    exit /b 1
)

REM Download dependencies
echo [1/4] Downloading dependencies...
go mod download
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies downloaded
echo.

REM Clean old files
echo [2/4] Cleaning old files...
if exist bin\app del /f /q bin\app 2>nul
if not exist bin mkdir bin
echo [OK] Cleaned
echo.

REM Build
echo [3/4] Building...
go build -o bin\app main.go
if %errorlevel% neq 0 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)
echo [OK] Build completed
echo.

REM Show result
echo [4/4] Done
echo ======================================
echo   Build SUCCESS!
echo ======================================
dir bin\app
echo.

pause
```

### 跨平台编译脚本模板（Go 示例）

```bat
@echo off
REM Cross-platform build script (Windows -> Linux)

REM Change to project root
cd /d "%~dp0.."

echo.
echo ======================================
echo   Cross-Compile Build Script
echo   Target: Linux AMD64
echo ======================================
echo.

REM Check build tool
echo [1/5] Checking build environment...
where go >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Go not found
    pause
    exit /b 1
)
echo [OK] Go found
echo.

REM Set cross-compile environment
echo [2/5] Setting build environment...
set GOOS=linux
set GOARCH=amd64
set CGO_ENABLED=0
echo [OK] Target: Linux AMD64
echo.

REM Download dependencies
echo [3/5] Downloading dependencies...
go mod download
echo [OK] Done
echo.

REM Clean old files
echo [4/5] Cleaning old files...
if exist bin\app del /f /q bin\app 2>nul
if not exist bin mkdir bin
echo [OK] Done
echo.

REM Build
echo [5/5] Building...
go build -ldflags="-s -w" -o bin\app main.go
if %errorlevel% neq 0 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)
echo [OK] Build completed
echo.

echo ======================================
echo   Build SUCCESS!
echo ======================================
echo Deployment:
echo   scp bin\app user@server:/path/
echo.

pause
```

## 常见陷阱

### ❌ 错误做法

```bat
# 1. 使用中文（会乱码）
echo 安装完成
REM 配置环境

# 2. 不切换目录，直接运行
go build main.go

# 3. 使用相对路径从其他目录运行
python main.py

# 4. 不检查错误
go mod download
go build

# 5. 不使用 pause，用户看不到输出
echo Done!
exit /b 0
```

### ✅ 正确做法

```bat
# 1. 使用英文
echo Installation complete
REM Configure environment

# 2. 先切换到项目根目录
cd /d "%~dp0.."
go build main.go

# 3. 使用基于根目录的相对路径
.venv\Scripts\python.exe main.py

# 4. 检查错误
go mod download
if %errorlevel% neq 0 (
    echo [ERROR] Download failed
    pause
    exit /b 1
)

# 5. 使用 pause
echo Done!
pause
```

## 特殊变量

| 变量 | 含义 |
|------|------|
| `%~dp0` | 脚本所在目录（带驱动器和末尾 \） |
| `%~f0` | 脚本完整路径 |
| `%~n0` | 脚本文件名（不含扩展名） |
| `%~x0` | 脚本扩展名 |
| `%cd%` | 当前目录 |
| `%errorlevel%` | 上一条命令的退出码 |

## 调试技巧

```bat
# Display current directory
echo Current directory: %cd%

# Display script location
echo Script location: %~dp0

# Display environment variables
echo GOOS: %GOOS%
echo GOARCH: %GOARCH%

# Pause to see output
pause
```

## 记住

1. **全英文** - 所有输出、注释、提示必须使用英文
2. **cd /d "%~dp0.."** - 从脚本位置定位到项目根目录
3. **检查错误** - 验证命令和文件存在性
4. **进度提示** - 让用户知道执行状态
5. **pause 结束** - 让用户看到输出
