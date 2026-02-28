---
name: docker-cn-source
description: 自动配置 Docker/Docker Compose 使用国内镜像源（apt/yum/apk/pip/npm）
allowed-tools: Read, Write, Edit, Glob, Grep
---

# Docker 国内源配置

自动检测并配置 Docker 项目使用国内镜像源，加速镜像拉取和构建过程。

## 工作流程

### 第一步：扫描项目

使用 `Glob` 工具搜索项目中的 Docker 相关文件：

```bash
**/Dockerfile
**/docker-compose.yml
**/docker-compose.yaml
```

### 第二步：分析基础镜像

对于每个找到的 Dockerfile，分析 `FROM` 指令确定：

1. **Linux 发行版类型**
   - `debian:*`, `ubuntu:*` → Debian 系 → 使用 `apt`
   - `centos:*`, `rhel:*`, `rockylinux:*`, `almalinux:*` → RedHat 系 → 使用 `yum`
   - `alpine:*` → Alpine → 使用 `apk`

2. **编程语言和包管理器**
   - 检测 `RUN pip install` → Python pip
   - 检测 `RUN npm install` → Node npm
   - 检测 `RUN yum install` / `RUN apt-get install` → 系统包

### 第三步：配置国内镜像源

根据检测结果，在 Dockerfile 中添加相应的镜像源配置。

#### APT (Debian/Ubuntu)

在第一个 `RUN apt-get update` 之前添加：

```dockerfile
# 使用阿里云镜像
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# 或者使用清华镜像
RUN sed -i 's|http://archive.ubuntu.com|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list
```

#### YUM (CentOS/RHEL)

在第一个 `RUN yum install` 之前添加：

```dockerfile
# 使用阿里云镜像
RUN sed -i 's|mirrorlist=|#mirrorlist=|g' /etc/yum.repos.d/CentOS-*.repo && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=https://mirrors.aliyun.com|g' /etc/yum.repos.d/CentOS-*.repo
```

#### APK (Alpine)

在第一个 `RUN apk add` 之前添加：

```dockerfile
# 使用阿里云镜像
RUN sed -i 's|https://dl-cdn.alpinelinux.org|https://mirrors.aliyun.com|g' /etc/apk/repositories
```

#### PIP (Python)

在第一个 `RUN pip install` 之前添加：

```dockerfile
# 使用清华镜像
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用阿里云镜像
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
```

#### NPM (Node)

在第一个 `RUN npm install` 之前添加：

```dockerfile
# 使用淘宝镜像（新地址）
RUN npm config set registry https://registry.npmmirror.com
```

### 第四步：修改文件

使用 `Edit` 工具修改检测到的 Dockerfile 文件：

1. 在 `FROM` 指令后添加换行
2. 插入相应的镜像源配置命令
3. 保持原有代码结构不变

### 第五步：输出摘要

向用户报告：
- 找到的文件列表
- 检测到的技术栈
- 添加的配置命令
- 修改的文件路径

## 国内镜像源配置表

| 包管理器 | 镜像源 | 地址 |
|---------|--------|------|
| apt | 阿里云 | `https://mirrors.aliyun.com` |
| apt | 清华大学 | `https://mirrors.tuna.tsinghua.edu.cn` |
| apt | 网易 | `https://mirrors.163.com` |
| yum | 阿里云 | `https://mirrors.aliyun.com` |
| yum | 清华大学 | `https://mirrors.tuna.tsinghua.edu.cn` |
| apk | 阿里云 | `https://mirrors.aliyun.com` |
| apk | 清华大学 | `https://mirrors.tuna.tsinghua.edu.cn` |
| pip | 清华大学 | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| pip | 阿里云 | `https://mirrors.aliyun.com/pypi/simple/` |
| npm | 淘宝 | `https://registry.npmmirror.com` |

## 默认选择策略

- **APT 系统**：使用阿里云镜像（稳定快速）
- **YUM 系统**：使用阿里云镜像
- **APK 系统**：使用阿里云镜像
- **PIP**：使用清华镜像（更新及时）
- **NPM**：使用淘宝新镜像（registry.npmmirror.com）

## docker-compose.yml 处理

对于 docker-compose.yml，检测并添加：

```yaml
# 添加国内 Docker 镜像加速
services:
  xxx:
    # 如果使用 build，添加镜像源参数
    build:
      args:
        APT_MIRROR: https://mirrors.aliyun.com
        PIP_INDEX_URL: https://pypi.tuna.tsinghua.edu.cn/simple
```

## 注意事项

1. **避免重复配置**：检查文件中是否已存在镜像源配置
2. **保持代码格式**：修改时保持原有的缩进和换行风格
3. **添加注释**：在添加的配置前添加注释说明用途
4. **兼容性检查**：确保配置命令与基础镜像版本兼容

## 示例转换

### 原始 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

CMD ["python", "app.py"]
```

### 转换后 Dockerfile

```dockerfile
FROM python:3.11-slim

# 配置国内镜像源
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

CMD ["python", "app.py"]
```

## 使用场景

当用户说以下内容时，启动此 skill：
- "/docker-cn-source"
- "配置 docker 国内源"
- "docker 构建太慢了"
- "加速 docker build"
