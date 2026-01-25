# HYC下载站 v2.1

模块化重构的Python镜像文件服务器，支持API版本化。

## 项目结构

```
mirror_server/
├── main.py                      # 主入口文件
├── requirements.txt             # 依赖列表
├── config.example.json          # 配置文件示例
├── core/                        # 核心模块
│   ├── __init__.py
│   ├── config.py                # 配置管理
│   ├── utils.py                 # 工具函数
│   ├── mirror_sync.py           # 镜像同步管理
│   └── server.py                # 服务器核心
├── api/                         # API模块
│   ├── __init__.py
│   ├── router.py                # API路由器
│   ├── v1.py                    # API v1（基础功能）
│   └── v2.py                    # API v2（增强功能）
└── handlers/                    # HTTP请求处理器
    ├── __init__.py
    └── http_handler.py          # HTTP请求处理
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

# 指定API版本
python main.py --api-version v2
```

### 认证

```bash
# 基本认证
python main.py --auth basic --auth-user admin --auth-pass password

# 令牌认证
python main.py --auth token --auth-token your_token_here
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

- **config.py**: 配置管理和验证
- **utils.py**: 通用工具函数（文件大小格式化、哈希计算等）
- **mirror_sync.py**: 镜像同步管理器（支持HTTP、FTP、SFTP、本地）
- **server.py**: 服务器核心类

### api/ - API模块

- **router.py**: API路由器，支持版本化
- **v1.py**: API v1实现（基础功能）
- **v2.py**: API v2实现（增强功能，继承v1）

### handlers/ - HTTP请求处理器

- **http_handler.py**: HTTP请求处理，包括文件服务、目录浏览等

## 特性

- ✅ 模块化设计，易于扩展
- ✅ API版本化支持（v1/v2）
- ✅ 镜像同步（HTTP/HTTPS、FTP、SFTP、本地目录）
- ✅ 文件上传下载（支持断点续传）
- ✅ 目录浏览（镜像站风格）
- ✅ 认证支持（无、基本认证、令牌认证）
- ✅ HTTPS支持
- ✅ 下载统计
- ✅ 文件搜索
- ✅ 批量操作
- ✅ 压缩/解压缩
- ✅ 增强搜索（v2）
- ✅ 文件元数据管理（v2）
- ✅ 服务器监控（v2）
- ✅ Webhook支持（v2）

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
