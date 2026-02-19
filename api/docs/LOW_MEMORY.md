# 低端设备优化指南

## 支持的架构

| 架构 | 状态 | 说明 |
|------|------|------|
| X86_64/AMD64 | ✓ 完全支持 | 主流 PC/服务器 |
| X86_32/i386/i686 | ✓ 支持 | 老旧 PC 设备 |
| ARM64/AArch64 | ✓ 完全支持 | 树莓派4/5, Jetson |
| ARMv7/armhf | ✓ 支持 | 树莓派3/2, Orange Pi |
| ARMv6 | ⚠ 实验性 | 树莓派Zero |
| MIPS | ⚠ 实验性 | 路由器等 |

## 设备预设

### ultra_low (极低端设备)
- **内存**: < 256MB RAM
- **示例**: 树莓派 Zero, 老旧路由器
- **配置**:
  ```bash
  python main.py --preset ultra_low
  ```
- **自动设置**:
  - Workers: 1
  - 最大缓存: 50MB
  - 块大小: 32KB
  - 禁用: WebSocket, SSE, 哈希计算

### low (低端设备)
- **内存**: 256MB - 512MB RAM
- **示例**: 树莓派 2, 老旧 VPS
- **配置**:
  ```bash
  python main.py --preset low
  ```
- **自动设置**:
  - Workers: 1
  - 最大缓存: 100MB
  - 块大小: 64KB
  - 启用所有功能

### medium (中等设备)
- **内存**: 512MB - 1GB RAM
- **示例**: 树莓派 4 (1GB), 低配 VPS
- **配置**:
  ```bash
  python main.py --preset medium
  ```
- **自动设置**:
  - Workers: 2
  - 最大缓存: 256MB
  - 块大小: 128KB

### high (高端设备)
- **内存**: 1GB+ RAM
- **示例**: 树莓派 4 (4GB/8GB), 家用服务器
- **配置**:
  ```bash
  python main.py --preset high
  ```
- **自动设置**:
  - Workers: 4
  - 最大缓存: 512MB
  - 块大小: 256KB

### auto (自动检测)
- 根据系统资源自动选择预设
- **配置**:
  ```bash
  python main.py --preset auto  # 默认
  ```

## 手动配置

### 内存限制
```bash
# 设置 256MB 内存限制
python main.py --memory-limit 256M

# 设置 512MB 内存限制
python main.py --memory-limit 512M
```

### 工作进程
```bash
# 单进程 (低端设备)
python main.py --workers 1

# 双进程
python main.py --workers 2
```

### 传输优化
```bash
# 小块传输 (节省内存)
python main.py --chunk-size 32K --buffer-size 64K
```

### 禁用可选功能
```bash
# 禁用 WebSocket 和 SSE (节省内存)
python main.py --disable-ws --disable-sse

# 禁用哈希计算 (节省 CPU)
python main.py --disable-hash
```

## 树莓派部署

### 方式一: 使用预编译镜像
```bash
# 拉取 ARM64 镜像
docker pull hx100cv/hyc-download-station:v2.3-arm64

# 运行
docker run -d \
  --name hyc-server \
  -p 8080:8080 \
  -v ./data:/data \
  -v ./downloads:/downloads \
  hyc-download-station:v2.3-arm64
```

### 方式二: 使用 Docker Compose
```bash
# 树莓派专用配置
docker-compose -f docker-compose.raspberry.yml up -d
```

### 方式三: 轻量级配置
```bash
# 适用于 512MB RAM 的树莓派
docker-compose -f docker-compose.lite.yml up -d
```

## 系统兼容性检查

```bash
# 检查系统兼容性
python main.py --check-compat

# 或使用脚本
./scripts/check-compat.sh
```

输出示例:
```
========================================
  HYC下载站 v2.3 - 兼容性检查
========================================

系统信息:
  - 架构: aarch64
  - 系统: Linux

✓ ARM64 (64位) - 完全支持
✓ Python 3.11 - 支持

内存检查:
  - 总内存: 4096MB
  ✓ 内存 1GB+ - 使用 high 预设

...

推荐启动命令:
  python main.py --preset high
```

## Docker 多架构构建

### 环境准备
```bash
# 设置 QEMU 仿真 (x86_64 上构建 ARM)
./scripts/setup-qemu.sh
```

### 构建镜像
```bash
# 构建所有架构
./scripts/build-multiarch.sh v2.3 hyc-download-station

# 或手动构建
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag hx100cv/hyc-download-station:v2.3 \
  --file docker/Dockerfile.multiarch \
  --push .
```

### 手动构建特定架构
```bash
# ARMv7
docker build \
  --platform linux/arm/v7 \
  --tag hx100cv/hyc-download-station:v2.3-armv7 \
  --file docker/Dockerfile.lite \
  --push .

# ARM64
docker build \
  --platform linux/arm64 \
  --tag hx100cv/hyc-download-station:v2.3-arm64 \
  --file docker/Dockerfile.lite \
  --push .

# i386 (32位)
docker build \
  --platform linux/386 \
  --tag hx100cv/hyc-download-station:v2.3-i386 \
  --file docker/Dockerfile.lite \
  --push .
```

## 性能调优建议

### 树莓派 4 (4GB)
```bash
# 推荐配置
python main.py \
  --preset high \
  --memory-limit 1G \
  --workers 2
```

### 树莓派 3
```bash
# 推荐配置
python main.py \
  --preset medium \
  --memory-limit 512M \
  --workers 2
```

### 树莓派 2/Zero
```bash
# 推荐配置
python main.py \
  --preset low \
  --memory-limit 256M \
  --workers 1 \
  --chunk-size 16K \
  --disable-ws \
  --disable-sse
```

## 内存使用监控

启动后可以通过 API 查看内存使用:
```bash
# 查看内存状态
curl http://localhost:8080/api/v1/monitor

# 或在 Web 界面查看
# 访问 http://localhost:8080/api/ui/
```

## 故障排除

### 内存不足
```
症状: OOM (Out of Memory) 错误
解决:
  1. 使用 --preset ultra_low
  2. 减小 --memory-limit
  3. 增加 swap 空间
```

### 构建失败
```
症状: 无法导入模块
解决:
  1. 重新安装依赖: pip install -r requirements.txt
  2. 检查 Python 版本: python3 --version
```

### ARM 镜像运行失败
```
症状: Illegal instruction
解决:
  1. 确保使用正确的架构镜像
  2. 检查 QEMU 设置
```
