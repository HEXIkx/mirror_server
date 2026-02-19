# Docker 部署指南

本项目提供多种 Docker 部署方式，支持多种架构和配置。

## 目录

- [快速开始](#快速开始)
- [Docker 镜像](#docker-镜像)
- [Dockerfile 说明](#dockerfile-说明)
- [Docker Compose](#docker-compose)
- [Kubernetes 部署](#kubernetes-部署)

## 快速开始

### 使用 Docker Hub 镜像（推荐）

```bash
# 拉取最新镜像
docker pull hx100cv/hyc-download:latest

# 运行容器
docker run -d \
  --name hyc-download \
  -p 8080:8080 \
  -v /data:/data \
  -v /downloads:/downloads \
  hx100cv/hyc-download:latest
```

### 使用 GitHub Container Registry

```bash
# 拉取镜像
docker pull ghcr.io/hexikx/mirror_server:latest

# 运行容器
docker run -d \
  --name hyc-download \
  -p 8080:8080 \
  -v /data:/data \
  -v /downloads:/downloads \
  ghcr.io/hexikx/mirror_server:latest
```

## Docker 镜像

### 多架构支持

项目自动构建以下架构的镜像：

| 架构 | 镜像标签 |
|------|----------|
| Linux AMD64 | `hx100cv/hyc-download:amd64-latest` |
| Linux ARM64 | `hx100cv/hyc-download:arm64v8-latest` |
| Linux ARMv7 | `hx100cv/hyc-download:arm32v7-latest` |

### 拉取特定架构

```bash
# AMD64
docker pull hx100cv/hyc-download:amd64-latest

# ARM64
docker pull hx100cv/hyc-download:arm64v8-latest

# ARMv7
docker pull hx100cv/hyc-download:arm32v7-latest
```

### 使用 Manifest（自动选择架构）

```bash
# 自动选择对应架构的镜像
docker pull hx100cv/hyc-download:latest
```

## Dockerfile 说明

### Dockerfile（推荐）

完整功能镜像，包含所有依赖。

```dockerfile
FROM hx100cv/hyc-download:latest
```

### Dockerfile.lite

轻量级镜像，适合资源受限的设备。

```dockerfile
FROM hx100cv/hyc-download:lite
```

### Dockerfile.multiarch

用于构建多架构镜像的 Dockerfile。

```bash
# 构建多架构镜像
docker buildx build -f docker/Dockerfile.multiarch \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  -t hx100cv/hyc-download:multi \
  --push .
```

## Docker Compose

### 基础用法

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 配置文件

项目提供以下 Docker Compose 配置文件：

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | 完整配置 |
| `docker-compose.lite.yml` | 轻量配置 |
| `docker-compose.raspberry.yml` | Raspberry Pi 配置 |

```bash
# 使用完整配置
docker-compose -f docker-compose.yml up -d

# 使用轻量配置
docker-compose -f docker-compose.lite.yml up -d

# 使用 Raspberry Pi 配置
docker-compose -f docker-compose.raspberry.yml up -d
```

### 带 Nginx 反向代理

```bash
docker-compose --profile with-nginx up -d
```

## Kubernetes 部署

### 部署文件

项目提供以下 K8s 配置文件：

| 文件 | 说明 |
|------|------|
| `k8s/deployment.yaml` | Deployment 配置 |
| `k8s/service.yaml` | Service 配置 |
| `k8s/helm/` | Helm Chart |

### 使用 Helm 部署

```bash
# 添加 Helm 仓库
helm repo add hyc-download https://hexikx.github.io/mirror_server

# 更新 Helm 仓库
helm repo update

# 部署
helm install my-hyc-download hyc-download/hyc-download
```

### 手动部署

```bash
# 应用配置
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 查看状态
kubectl get pods
kubectl get services
```

## 数据持久化

### 挂载卷

```bash
# 数据目录
-v /path/to/data:/data

# 下载目录
-v /path/to/downloads:/downloads

# 配置目录
-v /path/to/config:/app/config
```

### 使用命名卷

```yaml
volumes:
  - data:/data
  - downloads:/downloads
```

## 环境变量

### 支持的环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `HYC_HOST` | 监听地址 | `0.0.0.0` |
| `HYC_PORT` | 监听端口 | `8080` |
| `HYC_BASE_DIR` | 文件存储目录 | `/downloads` |
| `HYC_AUTH_TYPE` | 认证类型 | `none` |
| `HYC_AUTH_USER` | 认证用户名 | `admin` |
| `HYC_AUTH_PASS` | 认证密码 | `password` |
| `HYC_ENABLE_MONITOR` | 启用监控 | `true` |
| `HYC_ENABLE_MIRRORS` | 启用镜像加速 | `true` |
| `HYC_RATE_LIMIT` | 下载限速 | `0` |

### 示例

```bash
docker run -d \
  --name hyc-download \
  -p 8080:8080 \
  -e HYC_AUTH_TYPE=basic \
  -e HYC_AUTH_USER=admin \
  -e HYC_AUTH_PASS=secret \
  hx100cv/hyc-download:latest
```

## 健康检查

容器内置健康检查：

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/v1/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

## 日志

### 查看日志

```bash
# 实时日志
docker logs -f hyc-download

# 最近 100 行
docker logs --tail 100 hyc-download
```

### 日志级别

```bash
# 详细输出
docker run -e HYC_VERBOSE=1 hx100cv/hyc-download:latest

# 静默模式
docker run -e HYC_QUIET=1 hx100cv/hyc-download:latest
```

## 更新升级

### 拉取新版本

```bash
# 拉取最新镜像
docker pull hx100cv/hyc-download:latest

# 停止旧容器
docker-compose down

# 启动新容器
docker-compose up -d
```

### 使用 Watchtower 自动更新

```bash
# 运行 Watchtower
docker run -d \
  --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  hyc-download
```

## 故障排查

### 容器无法启动

```bash
# 查看详细错误
docker logs hyc-download

# 进入容器排查
docker exec -it hyc-download /bin/bash
```

### 端口冲突

```bash
# 检查端口占用
netstat -tlnp | grep 8080

# 修改映射端口
docker run -p 8888:8080 hx100cv/hyc-download:latest
```

### 权限问题

```bash
# 修改目录权限
chmod 777 /data /downloads

# 或使用用户运行
docker run -u 1000:1000 hx100cv/hyc-download:latest
```
