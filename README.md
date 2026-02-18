# HYC下载站 v2.2

模块化重构的Python镜像文件服务器，支持API版本化、实时通信、系统监控、数据库集成等高级功能。

## 项目结构

```
vs1/
├── main.py                      # 主入口文件
├── requirements.txt             # 依赖列表
├── settings.json                # 主配置文件
├── config.example.json          # 配置文件示例
├── api/                         # API模块
│   ├── __init__.py
│   ├── router.py                # API路由器
│   ├── v1.py                    # API v1（基础功能）
│   ├── v2.py                    # API v2（增强功能）
│   ├── admin.py                 # 管理接口
│   ├── ws_handler.py            # WebSocket处理
│   ├── sse_handler.py           # SSE事件流
│   └── docs/                    # API文档
├── core/                        # 核心模块
│   ├── __init__.py
│   ├── config.py                # 配置管理
│   ├── config_hotreload.py     # 配置热重载
│   ├── utils.py                 # 工具函数
│   ├── server.py                # 服务器核心
│   ├── database.py              # 数据库管理
│   ├── mirror_sync.py           # 镜像同步管理
│   ├── sync_scheduler.py        # 同步调度器
│   ├── sync_engine.py           # 同步引擎
│   ├── cache_manager.py         # 缓存管理
│   ├── cache_prewarm.py         # 缓存预热
│   ├── monitor.py               # 系统监控
│   ├── health_check.py          # 健康检查
│   ├── alerts.py                # 告警系统
│   ├── security.py              # 安全模块
│   ├── api_auth.py              # API认证
│   ├── api_docs.py              # API文档
│   ├── optimization.py          # 性能优化
│   ├── scheduler.py             # 任务调度
│   ├── graceful_restart.py      # 优雅重启
│   └── prometheus.py            # Prometheus监控
├── handlers/                    # HTTP请求处理器
│   ├── __init__.py
│   └── http_handler.py          # HTTP请求处理
├── api/ui/                      # Web管理界面
├── scripts/                     # 辅助脚本
├── docker/                      # Docker配置
└── k8s/                        # Kubernetes配置
```

## 安装

```bash
pip install -r requirements.txt
```

### 依赖

- psutil - 系统监控
- python-multipart - 多部分表单数据处理
- paramiko - SFTP支持（可选）

## 使用

### 基本使用

```bash
# 启动服务器（默认端口8080）
python main.py

# 指定端口和目录
python main.py -p 8080 -d ./downloads

# 启用HTTPS
python main.py --ssl-cert cert.pem --ssl-key key.pem

# 使用配置文件
python main.py --config config.json

# 指定API版本 (默认: v2)
python main.py --api-version v2

# 使用settings.json配置文件
python main.py --settings settings.json

# 检查系统兼容性
python main.py --check-compat
```

### 认证

```bash
# 无认证
python main.py --auth-type none

# 基本认证
python main.py --auth-type basic --auth-user admin --auth-pass password

# 令牌认证
python main.py --auth-type token --auth-token your_token_here
```

### 功能开关

```bash
# 禁用监控/同步/加速源
python main.py --enable-monitor --enable-sync --enable-mirrors

# 禁用WebSocket/SSE (适合低端设备)
python main.py --disable-ws --disable-sse

# 禁用文件哈希计算
python main.py --disable-hash

# 启用下载统计
python main.py --enable-stats --show-hash

# 启用目录浏览
python main.py --directory-listing true
```

### 镜像加速源

```bash
# 启用/禁用所有加速源功能
python main.py --enable-mirrors    # 启用
python main.py --enable-mirrors=false  # 禁用

# 各个镜像的启用/禁用通过 settings.json 配置
# 在 mirrors.xxx.enabled 中设置，例如:
# "docker": { "enabled": true, ... }
# "pypi": { "enabled": true, ... }
```

### 镜像同步配置

镜像同步支持多种同步类型，通过 `settings.json` 中的 `sync_sources` 配置：

```json
{
  "sync_sources": {
    "my-http-mirror": {
      "type": "http",
      "url": "https://example.com/mirror/",
      "target": "downloads/mirror",
      "enabled": true,
      "auto_sync": true,
      "schedule": { "enabled": true, "type": "cron", "cron": "0 4 * * *" }
    },
    "my-ftp-mirror": {
      "type": "ftp",
      "host": "ftp.example.com",
      "port": 21,
      "username": "anonymous",
      "password": "anonymous@example.com",
      "remote_path": "/pub",
      "target": "downloads/ftp",
      "enabled": true
    },
    "my-sftp-mirror": {
      "type": "sftp",
      "host": "sftp.example.com",
      "port": 22,
      "username": "syncuser",
      "password": "password",
      "private_key": "/path/to/id_rsa",
      "remote_path": "/mirror",
      "target": "downloads/sftp"
    },
    "my-git-repo": {
      "type": "git",
      "url": "https://github.com/example/repo.git",
      "branch": "main",
      "depth": 1,
      "target": "downloads/git"
    },
    "my-s3-mirror": {
      "type": "s3",
      "endpoint": "https://s3.amazonaws.com",
      "bucket": "my-bucket",
      "access_key": "AKIAIOSFODNN7EXAMPLE",
      "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
      "region": "us-east-1",
      "prefix": "mirrors/",
      "target": "downloads/s3"
    },
    "my-oss-mirror": {
      "type": "oss",
      "bucket": "my-bucket",
      "access_key": "your-access-key",
      "secret_key": "your-secret-key",
      "region": "cn-hangzhou",
      "target": "downloads/oss"
    },
    "my-cos-mirror": {
      "type": "cos",
      "bucket": "my-bucket",
      "access_key": "your-access-key",
      "secret_key": "your-secret-key",
      "region": "ap-guangzhou",
      "target": "downloads/cos"
    },
    "my-rsync-mirror": {
      "type": "rsync",
      "source": "rsync://rsync.example.com/module/path",
      "target": "downloads/rsync",
      "exclude": ["*.tmp", "*.log"]
    },
    "my-local-mirror": {
      "type": "local",
      "path": "/mnt/external drive/mirrors",
      "target": "downloads/local"
    }
  }
}
```

**支持的同步类型：**

| 类型 | 说明 | 必需配置 |
|------|------|----------|
| `http` / `https` | HTTP/HTTPS同步 | `url`, `target` |
| `ftp` | FTP同步 | `host`, `target` |
| `sftp` | SFTP同步 | `host`, `username`, `target` |
| `rsync` | Rsync同步 | `source`, `target` |
| `git` | Git仓库克隆/更新 | `url`, `target` |
| `s3` | AWS S3 / MinIO | `bucket`, `access_key`, `secret_key`, `endpoint` |
| `oss` | 阿里云OSS | `bucket`, `access_key`, `secret_key` |
| `cos` | 腾讯云COS | `bucket`, `access_key`, `secret_key` |
| `webdav` | WebDAV同步 | `url`, `username`, `password` |
| `local` | 本地目录同步 | `path`, `target` |

### 下载限速

```bash
# 全局限速 (字节/秒)
python main.py --rate-limit 10485760  # 10MB/s
```

### 低端设备优化

```bash
# 使用预设配置
python main.py --preset ultra_low   # 超低功耗
python main.py --preset low         # 低配置
python main.py --preset medium       # 中等
python main.py --preset high         # 高性能
python main.py --preset auto         # 自动检测

# 自定义参数
python main.py --memory-limit 256M \
  --workers 2 \
  --chunk-size 64K \
  --buffer-size 128K
```

### 调试选项

```bash
# 启用所有调试
python main.py --debug

# 启用特定调试
python main.py --debug-http
python main.py --debug-auth
python main.py --debug-api
python main.py --debug-v2
python main.py --debug-error
python main.py --debug-download

# 输出到调试文件
python main.py --debug-log /var/log/hyc-debug.log

# 指定调试类型
python main.py --debug-types http auth api v2 error

# 详细输出
python main.py -v
python main.py -vv
python main.py -q  # 静默模式
```

### 启动参数完整列表

```
服务器配置:
  --host HOST              监听地址 (默认: 0.0.0.0)
  -p, --port PORT          监听端口 (默认: 8080)
  -d, --base-dir DIR       文件存储目录 (默认: ./downloads)
  --server-name NAME       服务器名称 (默认: HYC下载站)

HTTPS配置:
  --ssl-cert FILE          SSL证书文件路径
  --ssl-key FILE           SSL私钥文件路径

认证配置:
  --auth-type TYPE         认证类型: none/basic/token (默认: none)
  --auth-user USER         基本认证用户名 (默认: admin)
  --auth-pass PASS         基本认证密码
  --auth-token TOKEN       令牌认证密钥

功能配置:
  --directory-listing BOOL 启用目录浏览 (默认: True)
  --enable-stats BOOL      启用下载统计 (默认: True)
  --show-hash             显示文件哈希值
  --ignore-hidden         忽略隐藏文件 (默认: True)
  --max-upload-size SIZE  最大上传文件大小 (默认: 1G)
  --api-version VERSION   API版本: v1/v2 (默认: v2)

实时通信:
  --enable-ws             启用WebSocket (默认: True)
  --enable-sse            启用SSE (默认: True)

系统监控:
  --enable-monitor        启用系统监控 (默认: True)
  --monitor-interval SEC  监控采集间隔(秒) (默认: 5)

同步配置:
  --enable-sync           启用镜像同步 (默认: True)
  --sync-config FILE      同步配置文件路径

镜像加速源:
  --enable-mirrors        启用下载加速源 (默认: True)
  # 各个镜像通过 settings.json 配置 (mirrors.xxx.enabled)

下载限速:
  --rate-limit BYTES      全局下载限速 (默认: 0=不限速)

低端设备优化:
  --preset PRESET         设备预设: ultra_low/low/medium/high/auto (默认: auto)
  --memory-limit SIZE     内存限制 (例如: 256M, 512M, 1G)
  --workers NUM           工作进程数 (0=自动)
  --chunk-size SIZE       文件传输块大小 (默认: 128K)
  --buffer-size SIZE      缓冲区大小 (默认: 256K)
  --disable-ws            禁用WebSocket
  --disable-sse           禁用SSE
  --disable-hash          禁用文件哈希计算
  --check-compat          检查系统兼容性后退出

日志配置:
  --access-log FILE       访问日志文件路径
  -v, --verbose          详细输出 (可叠加: -vvv)
  -q, --quiet            静默模式

调试选项:
  -D, --debug            启用所有调试输出
  --debug-log FILE       调试日志文件路径
  --debug-http           调试HTTP请求
  --debug-auth           调试认证检查
  --debug-api            调试API路由
  --debug-v2             调试V2 API
  --debug-error          调试错误堆栈
  --debug-download       调试下载记录
  --debug-types TYPES    指定调试类型列表

配置文件:
  --settings FILE         默认配置文件路径 (默认: settings.json)
  --config FILE           覆盖配置文件路径 (JSON格式)
```

## API版本

### API v1 - 基础功能

- 文件管理：上传、下载、删除、搜索
- 目录浏览
- 基础统计
- 同步管理（HTTP/HTTPS、FTP、SFTP、本地）

#### 示例API端点

```
GET  /api/v1/files              # 列出文件
GET  /api/v1/file/{path}        # 获取文件信息
DELETE /api/v1/file/{path}      # 删除文件
POST /api/v1/upload             # 上传文件
GET  /api/v1/search?q={term}    # 搜索文件
GET  /api/v1/stats              # 获取统计
GET  /api/v1/health             # 健康检查
POST /api/v1/sync/start         # 开始同步
```

### API v2 - 增强功能

继承v1所有功能，额外提供：

- 增强搜索（模糊匹配、正则表达式、内容搜索）
- 按标签和日期范围搜索
- 文件元数据管理
- 文件版本控制
- 缩略图生成
- 实时服务器监控
- Webhook支持
- 历史数据分析

#### 示例API端点

```
GET  /api/v2/search/enhanced?q={term}           # 增强搜索
GET  /api/v2/search/by-tag?tag={tag}            # 按标签搜索
GET  /api/v2/search/by-date?start={date}        # 按日期搜索
GET  /api/v2/stats/detailed                     # 详细统计
GET  /api/v2/stats/trending                     # 热门文件
GET  /api/v2/file/{path}/metadata               # 获取文件元数据
PUT  /api/v2/file/{path}/metadata               # 更新文件元数据
GET  /api/v2/file/{path}/versions               # 获取文件版本
POST /api/v2/file/{path}/versions               # 创建文件版本
GET  /api/v2/file/{path}/thumbnail?w=200&h=200 # 获取缩略图
GET  /api/v2/monitor/realtime                  # 实时监控
GET  /api/v2/webhooks                          # 列出webhooks
POST /api/v2/webhooks                          # 创建webhook
```

## 配置

### 配置文件示例

参考 `config.example.json`

### 命令行参数

```
服务器配置:
  --host                  监听地址 (默认: 0.0.0.0)
  -p, --port              监听端口 (默认: 8080)
  -d, --base-dir          文件存储目录 (默认: ./downloads)
  --server-name           服务器名称

HTTPS配置:
  --ssl-cert              SSL证书文件路径
  --ssl-key               SSL私钥文件路径

认证配置:
  --auth-type             认证类型: none, basic, token
  --auth-user             基本认证用户名
  --auth-pass             基本认证密码
  --auth-token            令牌认证密钥

功能配置:
  --no-directory-listing  禁用目录浏览
  --no-stats              禁用下载统计
  --show-hash             显示文件哈希值
  --max-upload-size       最大上传文件大小 (默认: 1G)
  --sync-config           同步配置文件路径
  --api-version           API版本: v1, v2 (默认: v1)

日志配置:
  --access-log            访问日志文件路径
  -v, --verbose           详细输出
  -q, --quiet             静默模式

配置:
  --config                配置文件路径 (JSON格式)
```

## 模块说明

### core/ - 核心模块

- **config.py**: 配置管理和验证，支持多级配置合并
- **config_hotreload.py**: 配置文件热重载，无需重启生效
- **utils.py**: 通用工具函数（文件大小格式化、哈希计算等）
- **server.py**: 服务器核心类，基于aiohttp
- **database.py**: 数据库管理，支持SQLite/MySQL/PostgreSQL
- **mirror_sync.py**: 镜像同步管理器（支持HTTP/HTTPS、FTP、SFTP、本地、Rsync、Git、S3/OSS/COS、WebDAV）
- **sync_scheduler.py**: 同步调度器，定时执行同步任务
- **sync_engine.py**: 同步引擎，核心同步逻辑
- **cache_manager.py**: 缓存管理，智能缓存策略
- **cache_prewarm.py**: 缓存预热，启动时预加载热门资源
- **monitor.py**: 系统监控，CPU/内存/磁盘/网络实时监控
- **health_check.py**: 健康检查，系统组件状态检测
- **alerts.py**: 告警系统，异常情况自动告警
- **security.py**: 安全模块，防护和审计
- **api_auth.py**: API认证，Token/Key/Session管理
- **api_docs.py**: API文档自动生成
- **optimization.py**: 性能优化，自动检测设备配置
- **scheduler.py**: 通用任务调度器
- **graceful_restart.py**: 优雅重启，服务无缝更新
- **prometheus.py**: Prometheus监控指标导出

### api/ - API模块

- **router.py**: API路由器，支持版本化
- **v1.py**: API v1实现（基础功能）
- **v2.py**: API v2实现（增强功能，继承v1）
- **admin.py**: 管理接口，密钥/会话/Webhooks管理
- **ws_handler.py**: WebSocket处理，实时双向通信
- **sse_handler.py**: SSE事件流，单向实时推送
- **ui/**: Web管理界面

### handlers/ - HTTP请求处理器

- **http_handler.py**: HTTP请求处理，包括文件服务、目录浏览等

## 特性

- ✅ 模块化设计，易于扩展
- ✅ API版本化支持（v1/v2）
- ✅ 镜像同步（HTTP/HTTPS、FTP、SFTP、Rsync、Git、S3/OSS/COS、WebDAV、本地目录）
- ✅ 文件上传下载（支持断点续传）
- ✅ 目录浏览（镜像站风格）
- ✅ 认证支持（无、基本认证、令牌认证、API Key）
- ✅ HTTPS支持
- ✅ 下载统计
- ✅ 文件搜索（基础/增强/正则）
- ✅ 批量操作
- ✅ 压缩/解压缩
- ✅ 增强搜索（v2）
- ✅ 文件元数据管理（v2）
- ✅ 服务器监控（v2）
- ✅ Webhook支持（v2）
- ✅ 实时通信（WebSocket + SSE）
- ✅ 数据库支持（SQLite/MySQL/PostgreSQL）
- ✅ 缓存系统（智能/手动/全同步）
- ✅ 配置热重载
- ✅ 优雅重启
- ✅ Prometheus监控
- ✅ 告警系统
- ✅ 设备自动优化
- ✅ 多镜像加速源（Docker/APT/YUM/PyPI/npm/Go）
- ✅ Web管理界面

## 开发

### 添加新的API版本

1. 在 `api/` 目录下创建 `v3.py`
2. 继承 `APIv2` 或 `APIv1`
3. 实现所需方法
4. 在 `api/router.py` 中注册新版本

### 添加新的同步类型

在 `core/mirror_sync.py` 的 `MirrorSyncManager` 类中：
1. 添加 `_sync_{type}` 方法
2. 实现同步逻辑
3. 在 `_sync_worker` 中添加路由

## 构建和部署

### 使用 PyInstaller 打包成二进制文件

#### 构建当前平台

项目提供了 `build.py` 脚本，可以将项目打包成当前平台的二进制可执行文件。

```bash
# 安装 PyInstaller
pip install pyinstaller

# 查看支持的目标平台
python build.py --list

# 构建当前平台
python build.py

# 清理构建缓存
python build.py --clean
```

**支持的平台（仅当前平台）：**
- Linux: amd64, arm64, 386
- Windows: amd64, 386
- macOS: amd64, arm64

构建完成后，二进制文件和发布包会输出到 `dist/` 目录。

#### 跨平台构建（GitHub Actions）

使用 GitHub Actions 可以方便地构建多平台版本（Linux ARM、AMD64 等）：

```bash
# 1. 初始化 git 仓库
git init
git add .
git commit -m "Add build workflow"

# 2. 添加远程仓库（替换为你的仓库地址）
git remote add origin https://github.com/your-username/your-repo.git
git branch -M main
git push -u origin main
```

推送完成后：

1. 访问 GitHub 仓库
2. 点击 **Actions** 标签
3. 选择 **"Build Linux ARM Binaries"**
4. 点击 **"Run workflow"**
5. 等待 5-10 分钟后下载构建产物

**优势：**
- ✅ 完全免费
- ✅ 无需本地配置
- ✅ 支持多平台构建
- ✅ 自动化持续集成

详细说明请参考 [BUILD.md](../BUILD.md)

#### 快速开始

**Linux/macOS:**
```bash
# 给脚本添加执行权限
chmod +x docker-deploy.sh

# 构建并运行
./docker-deploy.sh build
./docker-deploy.sh run

# 使用 docker-compose
./docker-deploy.sh compose
```

**Windows:**
```batch
docker-deploy.bat build
docker-deploy.bat run
```

### HTTPS 支持

#### 使用 Nginx 反向代理

1. 创建 SSL 证书目录并放置证书
```bash
mkdir -p ssl
# 将 cert.pem 和 key.pem 放入 ssl/ 目录
```

2. 使用带 Nginx 的 docker-compose 启动
```bash
docker-compose --profile with-nginx up -d
```

#### 直接启用 HTTPS

```bash
python main.py --ssl-cert cert.pem --ssl-key key.pem
```

详细说明请参考 [DOCKER.md](DOCKER.md)

## 许可

本项目仅供学习和研究使用。
