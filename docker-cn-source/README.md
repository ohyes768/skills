# Docker 国内源配置 (Docker CN Source)

这是一个 Claude Code 自定义 skill，自动配置 Docker 和 Docker Compose 使用国内镜像源，大幅加速镜像拉取和构建过程。

## 为什么需要这个 skill？

在中国大陆使用 Docker 时，经常会遇到：
- **镜像拉取慢**：默认从 Docker Hub 拉取镜像速度很慢
- **构建慢**：apt/yum/pip/npm 等包管理器使用海外源，下载依赖极慢
- **频繁超时**：网络不稳定导致构建失败

这个 skill 通过自动配置国内镜像源，解决以上所有问题。

## 工作原理

```
扫描项目 Dockerfile
    ↓
自动检测：Linux 发行版 + 包管理器
    ↓
智能配置对应的国内镜像源
    ↓
修改 Dockerfile 添加镜像源配置
```

## 支持的镜像源

| 类型 | 支持的包管理器 | 默认镜像源 |
|-----|--------------|-----------|
| 系统包 | apt (Debian/Ubuntu) | 阿里云 |
| 系统包 | yum (CentOS/RHEL) | 阿里云 |
| 系统包 | apk (Alpine) | 阿里云 |
| Python | pip | 清华大学 |
| Node.js | npm | 淘宝新镜像 |

## 使用方法

### 方式 1：直接触发
在对话中说：
- "/docker-cn-source"
- "配置 docker 国内源"
- "docker 构建太慢了"

### 方式 2：项目根目录触发
在包含 Dockerfile 的项目中，直接调用 skill。

## 示例

### 转换前

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
```

### 转换后

```dockerfile
FROM python:3.11-slim

# 配置国内镜像源
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
```

## 速度对比

| 操作 | 使用海外源 | 使用国内源 | 提升 |
|-----|----------|----------|-----|
| pip install flask | ~30秒 | ~2秒 | 15x |
| apt-get update | ~60秒 | ~5秒 | 12x |
| npm install express | ~45秒 | ~3秒 | 15x |

## 特性

- **自动检测**：智能识别 Linux 发行版和包管理器
- **安全修改**：只添加配置，不破坏原有代码
- **避免重复**：检测已存在的配置，避免重复添加
- **注释清晰**：添加的配置都有明确注释

## 检测能力

### 基础镜像识别

| FROM 指令 | 检测结果 |
|----------|---------|
| `FROM python:3.11-slim` | Debian + apt + pip |
| `FROM node:20-alpine` | Alpine + apk + npm |
| `FROM centos:7` | CentOS + yum |
| `FROM ubuntu:22.04` | Ubuntu + apt |

### 包管理器识别

| 指令 | 检测结果 |
|-----|---------|
| `RUN pip install` | Python pip |
| `RUN npm install` | Node npm |
| `RUN apt-get install` | APT |
| `RUN yum install` | YUM |
| `RUN apk add` | APK |

## 国内镜像源列表

### APT (Debian/Ubuntu)
- **阿里云**：`https://mirrors.aliyun.com`（默认）
- **清华大学**：`https://mirrors.tuna.tsinghua.edu.cn`
- **网易**：`https://mirrors.163.com`

### YUM (CentOS/RHEL)
- **阿里云**：`https://mirrors.aliyun.com`（默认）
- **清华大学**：`https://mirrors.tuna.tsinghua.edu.cn`

### APK (Alpine)
- **阿里云**：`https://mirrors.aliyun.com`（默认）
- **清华大学**：`https://mirrors.tuna.tsinghua.edu.cn`

### PIP (Python)
- **清华大学**：`https://pypi.tuna.tsinghua.edu.cn/simple`（默认）
- **阿里云**：`https://mirrors.aliyun.com/pypi/simple/`

### NPM (Node.js)
- **淘宝新镜像**：`https://registry.npmmirror.com`（默认）

## 注意事项

1. **备份原文件**：skill 会直接修改 Dockerfile，建议使用 git 管理以便回退
2. **网络环境**：如果网络环境特殊，可能需要手动调整镜像源
3. **镜像更新**：国内镜像通常有几分钟到几小时的同步延迟

## 与其他 skill 配合

1. **docker-cn-source** - 配置国内镜像源
2. **其他开发 skill** - 进行后续开发
3. **git-commit-push** - 提交修改

## 常见问题

**Q: 支持 Docker Desktop 吗？**
A: 此 skill 配置的是 Dockerfile 内的镜像源，不影响 Docker Desktop 本身。

**Q: 可以自定义镜像源吗？**
A: 当前版本使用默认最优镜像源。如需自定义，可以在配置后手动修改 SKILL.md。

**Q: 如何撤销更改？**
A: 如果使用 git 管理，直接 `git checkout` 即可撤销。

**Q: 支持 Windows 容器吗？**
A: 当前仅支持 Linux 容器，Windows 容器不需要配置镜像源。

## 文件结构

```
docker-cn-source/
├── SKILL.md      # Skill 定义文件（Claude 读取并执行）
└── README.md     # 说明文档（你正在阅读）
```

## 技术细节

### APT 配置原理

```bash
# 替换默认源为阿里云
sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources
```

### YUM 配置原理

```bash
# 禁用 mirrorlist，启用 baseurl 并指向阿里云
sed -i 's|mirrorlist=|#mirrorlist=|g' /etc/yum.repos.d/CentOS-*.repo
sed -i 's|#baseurl=http://mirror.centos.org|baseurl=https://mirrors.aliyun.com|g' /etc/yum.repos.d/CentOS-*.repo
```

### APK 配置原理

```bash
# 替换默认源为阿里云
sed -i 's|https://dl-cdn.alpinelinux.org|https://mirrors.aliyun.com|g' /etc/apk/repositories
```

### PIP 配置原理

```bash
# 设置全局镜像源
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### NPM 配置原理

```bash
# 设置淘宝镜像
npm config set registry https://registry.npmmirror.com
```

## 反馈与改进

如果这个 skill 对你有帮助，或者有改进建议，欢迎反馈！
