# HYC下载站 v2.3 - API 文档

## 快速开始

```bash
# 测试健康检查
curl http://localhost:8080/api/v1/health

# 获取文件列表
curl http://localhost:8080/api/v1/files

# 下载文件
curl -O http://localhost:8080/downloads/ubuntu-22.04.iso
```

## 认证方式

项目支持可选的认证功能，通过 `settings.json` 配置。

### 公开访问模式（默认）

```json
{
  "auth_type": "none"
}
```

当 `auth_type: none` 时，所有接口无需认证即可访问，适合公开下载站点。

### 启用认证

如需启用认证：

```json
{
  "auth_type": "basic",
  "auth_user": "admin",
  "auth_pass": "yourpassword"
}
```

或使用 Token 认证：

```json
{
  "auth_type": "token",
  "auth_token": "your-secret-token"
}
```

**支持的认证方式：**

| 方式 | 请求头 |
|------|--------|
| Bearer Token | `Authorization: Bearer <token>` |
| Basic Auth | `Authorization: Basic <base64(username:password)>` |

**注意：** 旧版 `api_keys.json` 已被 `admin_keys.json` 替代。

---

## 文件管理

### 列出文件

**GET** `/api/v1/files`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 否 | 目录路径 (默认根目录) |
| recursive | boolean | 否 | 是否递归列出子目录 |

**响应示例：**
```json
{
  "files": [
    {
      "name": "ubuntu-22.04.iso",
      "path": "ubuntu-22.04.iso",
      "size": 4588563456,
      "size_formatted": "4.3 GB",
      "type": "application/octet-stream",
      "modified": "2024-01-15T10:30:00",
      "sha256": "abc123...",
      "download_count": 1523
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 1,
    "total_pages": 1
  }
}
```

---

### 获取文件信息

**GET** `/api/v1/file/{path}`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 文件路径 |

**响应示例：**
```json
{
  "name": "ubuntu-22.04.iso",
  "path": "ubuntu-22.04.iso",
  "size": 4588563456,
  "size_formatted": "4.3 GB",
  "type": "application/octet-stream",
  "modified": "2024-01-15T10:30:00",
  "sha256": "abc123def456...",
  "download_count": 1523
}
```

**错误响应 (404)：**
```json
{
  "error": "File not found",
  "path": "nonexistent.iso"
}
```

---

### 文件预览

**GET** `/api/v1/file/{path}/preview`

预览图片、JSON、Markdown、文本、PDF、音频等文件。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 文件路径 |

**响应示例（图片）：**
```json
{
  "path": "images/logo.png",
  "name": "logo.png",
  "size": 24576,
  "type": "image/png",
  "preview_available": true,
  "preview_type": "image",
  "data_url": "data:image/png;base64,iVBORw0KGgo...",
  "truncated": false
}
```

**响应示例（JSON）：**
```json
{
  "path": "config.json",
  "name": "config.json",
  "size": 1024,
  "type": "application/json",
  "preview_available": true,
  "preview_type": "json",
  "content": {
    "server_name": "HYC Download",
    "port": 8080
  },
  "truncated": false
}
```

**支持的预览类型：** 图片、SVG、JSON、Markdown、XML、CSV、YAML、音频、PDF、文本文件

**错误响应 (413)：**
```json
{
  "error": "File too large for preview (max 10 MB)",
  "file_size": 15728640,
  "max_preview_size": 10485760
}
```

---

### 删除文件

**DELETE** `/api/v1/file/{path}` (需要认证)

**响应示例：**
```json
{
  "success": true,
  "message": "File deleted successfully",
  "path": "old-file.iso"
}
```

**错误响应 (403)：**
```json
{
  "error": "Permission denied",
  "code": "FORBIDDEN"
}
```

---

### 创建目录

**PUT** `/api/v1/mkdir` (需要认证)

**请求体：**
```json
{
  "path": "/downloads/new-folder"
}
```

**响应示例：**
```json
{
  "success": true,
  "message": "Directory created",
  "path": "/downloads/new-folder"
}
```

---

### 上传文件

**POST** `/api/v1/upload` (需要认证)

**表单参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| path | string | 目标目录 |
| file | binary | 要上传的文件 |

**响应示例：**
```json
{
  "success": true,
  "message": "File uploaded successfully",
  "name": "uploaded-file.iso",
  "size": 104857600,
  "path": "/downloads/uploaded-file.iso"
}
```

---

### 批量操作

**POST** `/api/v1/batch` (需要认证)

**请求体：**
```json
{
  "operation": "delete",
  "files": ["file1.iso", "file2.iso", "file3.iso"],
  "target_dir": ""
}
```

**响应示例：**
```json
{
  "success": true,
  "operation": "delete",
  "processed": 3,
  "failed": 0,
  "details": [
    {"path": "file1.iso", "status": "deleted"},
    {"path": "file2.iso", "status": "deleted"},
    {"path": "file3.iso", "status": "deleted"}
  ]
}
```

---

### 搜索文件

**GET** `/api/v1/search`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词 |
| type | string | 否 | 搜索类型 (all, file, dir) |
| limit | integer | 否 | 返回结果数量限制 |

**响应示例：**
```json
{
  "query": "ubuntu",
  "total": 5,
  "results": [
    {
      "name": "ubuntu-22.04.iso",
      "path": "ubuntu-22.04.iso",
      "size": 4588563456,
      "size_formatted": "4.3 GB",
      "modified": "2024-01-15T10:30:00"
    }
  ]
}
```

---

## 镜像同步

### 获取同步源列表

**GET** `/api/v1/sync/sources`

**响应示例：**
```json
{
  "sources": [
    {
      "name": "ubuntu-releases",
      "type": "http",
      "url": "https://releases.ubuntu.com/",
      "target": "ubuntu/",
      "enabled": true,
      "auto_sync": true,
      "last_sync": "2024-01-15T02:00:00",
      "status": "idle"
    }
  ],
  "count": 2
}
```

---

### 添加同步源

**POST** `/api/v1/sync/sources` (需要认证)

**请求体：**
```json
{
  "name": "new-mirror",
  "type": "http",
  "url": "https://example.com/mirror/",
  "target": "custom/",
  "enabled": true,
  "auto_sync": true
}
```

---

### 删除同步源

**DELETE** `/api/v1/sync/sources/{name}` (需要认证)

**响应示例：**
```json
{
  "success": true,
  "message": "Sync source deleted",
  "name": "ubuntu-releases"
}
```

---

### 更新同步源配置

**PUT** `/api/v1/sync/sources/{name}` (需要认证)

**请求体：**
```json
{
  "config": {
    "enabled": true,
    "auto_sync": true,
    "schedule": "0 2 * * *"
  }
}
```

**响应示例：**
```json
{
  "success": true,
  "name": "ubuntu-releases"
}
```

---

### 开始同步

**POST** `/api/v1/sync/start` (需要认证)

**请求体：**
```json
{
  "sources": ["ubuntu-releases", "debian-cd"]
}
```

**响应示例：**
```json
{
  "success": true,
  "message": "Sync started",
  "sources": ["ubuntu-releases", "debian-cd"],
  "started_at": "2024-01-15T10:00:00"
}
```

---

### 停止同步

**POST** `/api/v1/sync/stop` (需要认证)

**响应示例：**
```json
{
  "success": true,
  "message": "Sync stopped",
  "stopped_at": "2024-01-15T10:30:00",
  "synced_files": 1250,
  "failed_files": 3
}
```

---

### 获取同步状态

**GET** `/api/v1/sync/status`

**响应示例：**
```json
{
  "running": true,
  "progress": 45.5,
  "synced": 1250,
  "total": 2748,
  "current_source": "ubuntu-releases",
  "speed": "2.5 MB/s",
  "eta": "5m 30s",
  "started_at": "2024-01-15T10:00:00"
}
```

---

## 加速源

### 列出可用包

**GET** `/api/v1/mirror/{type}/list`

**type 可选值：** `docker`, `apt`, `yum`, `pypi`, `npm`, `go`

**响应示例：**
```json
{
  "type": "docker",
  "total": 150,
  "page": 1,
  "per_page": 50,
  "packages": [
    {
      "name": "ubuntu",
      "description": "Ubuntu base image",
      "versions": ["latest", "22.04", "20.04", "18.04"],
      "size": "25 MB"
    }
  ]
}
```

---

### 搜索包

**GET** `/api/v1/mirror/{type}/search`

**响应示例：**
```json
{
  "type": "pypi",
  "query": "django",
  "total": 5,
  "results": [
    {
      "name": "Django",
      "version": "5.0.1",
      "summary": "The Web framework for perfectionists with deadlines.",
      "author": "Django Software Foundation",
      "size": "8.2 MB",
      "requires_python": ">=3.10"
    }
  ]
}
```

---

### 压缩/解压缩

**POST** `/api/v1/archive` (需要认证)

**请求体：**
```json
{
  "operation": "compress",  // 或 "extract"
  "files": ["file1.txt", "file2.txt"],
  "archive_name": "archive.zip",
  "target_dir": ""
}
```

**压缩响应示例：**
```json
{
  "operation": "compress",
  "archive_path": "archive.zip",
  "compressed_files": 2,
  "archive_size": 1048576
}
```

**解压缩响应示例：**
```json
{
  "operation": "extract",
  "extract_dir": "",
  "extracted_files": 5
}
```

**错误响应 (400)：**
```json
{
  "error": "Invalid operation"
}
```

---

### 获取服务器配置

**GET** `/api/v1/config`

**响应示例：**
```json
{
  "server_name": "HYC Download Station",
  "version": "2.3.0",
  "base_dir": "/downloads",
  "directory_listing": true,
  "max_upload_size": 1073741824,
  "enable_stats": true,
  "auth_type": "none",
  "sort_by": "name",
  "sort_reverse": false,
  "ignore_hidden": true,
  "enable_range": true,
  "show_hash": false,
  "calculate_hash": false,
  "max_search_results": 100,
  "api_version": "v1"
}
```

---

## 统计监控

### 获取系统统计

**GET** `/api/v1/stats`

**响应示例：**
```json
{
  "total_files": 1520,
  "total_dirs": 245,
  "total_size": 107374182400,
  "total_size_formatted": "100.0 GB",
  "downloads_total": 52340,
  "downloads_today": 1250,
  "downloads_week": 8750
}
```

---

### 获取监控数据

**GET** `/api/v1/monitor`

**响应示例：**
```json
{
  "cpu": {
    "percent": 35.5,
    "cores": 4
  },
  "memory": {
    "total": 8589934592,
    "used": 3221225472,
    "free": 5368709120,
    "percent": 37.5
  },
  "disk": {
    "total": 536870912000,
    "used": 107374182400,
    "free": 429496729600,
    "percent": 20.0
  },
  "network": {
    "rx_bytes": 1048576000,
    "tx_bytes": 524288000,
    "rx_speed": "1.2 MB/s",
    "tx_speed": "512 KB/s"
  },
  "uptime": 86400
}
```

---

### 健康检查

**GET** `/api/v1/health`

**成功响应 (200)：**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00",
  "version": "2.2.0",
  "uptime": 86400,
  "components": {
    "api": "ok",
    "database": "ok",
    "cache": "ok",
    "storage": "ok"
  }
}
```

**异常响应 (503)：**
```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00",
  "error": "Database connection failed",
  "components": {
    "api": "ok",
    "database": "error",
    "cache": "ok",
    "storage": "ok"
  }
}
```

---

## Webhooks

### 列出 Webhooks

**GET** `/api/v2/webhooks` (需要 admin 权限)

**响应示例：**
```json
{
  "webhooks": [
    {
      "id": "wh_abc123",
      "name": "Download Notification",
      "url": "https://example.com/webhook",
      "events": ["download", "sync.complete"],
      "enabled": true,
      "created_at": "2024-01-10T10:00:00",
      "last_triggered": "2024-01-15T10:25:00",
      "trigger_count": 1250
    }
  ],
  "count": 1
}
```

---

### 创建 Webhook

**POST** `/api/v2/webhooks` (需要 admin 权限)

**请求体：**
```json
{
  "name": "New Download",
  "url": "https://example.com/webhook",
  "events": ["download"],
  "secret": "webhook-secret-key"
}
```

---

### 删除 Webhook

**DELETE** `/api/v2/webhooks/{webhook_id}` (需要 admin 权限)

---

### 测试 Webhook

**POST** `/api/v2/webhooks/{webhook_id}/test` (需要 admin 权限)

**响应示例：**
```json
{
  "success": true,
  "webhook_id": "wh_abc123",
  "status_code": 200,
  "response_time": 150,
  "response_body": "{\"status\":\"ok\"}"
}
```

---

## Minecraft 服务器核心 API

### 获取核心列表

**GET** `/api/v1/mc/corelist`

**响应示例：**
```json
{
  "corelist": [
    {
      "project": "paper",
      "metadata": {
        "current": "1.21.1"
      },
      "versions": ["1.21.1", "1.21", "1.20.6", "1.20.4"]
    },
    {
      "project": "spigot",
      "metadata": {
        "current": "1.20.4"
      },
      "versions": ["1.20.4", "1.20.1", "1.19.4"]
    }
  ]
}
```

---

### 获取特定核心版本列表

**GET** `/api/v1/mc/corelist/{name}`

**响应示例：**
```json
{
  "project": "paper",
  "metadata": {
    "current": "1.21.1"
  },
  "versions": ["1.21.1", "1.21", "1.20.6"]
}
```

---

### 获取所有版本

**GET** `/api/v1/mc/versions`

**GET** `/api/v1/mc/versions/{name}`

**响应示例：**
```json
{
  "core": "paper",
  "versions": {
    "paper": {
      "1.21.1": [
        {
          "version": "1.21.1",
          "file_name": "paper-1.21.1.jar",
          "size": 47185920,
          "modified": "2024-01-15T10:30:00"
        }
      ],
      "1.21": [
        {
          "version": "1.21",
          "file_name": "paper-1.21.jar",
          "size": 46000000,
          "modified": "2024-01-10T08:00:00"
        }
      ]
    }
  }
}
```

---

### 获取核心信息

**GET** `/api/v1/mc/info/{name}/{version}`

**响应示例：**
```json
{
  "core_name": "paper",
  "version": "1.21.1",
  "major_version": "1.21",
  "file_name": "paper-1.21.1.jar",
  "size": 47185920,
  "size_formatted": "45.0 MB",
  "modified": "2024-01-15T10:30:00",
  "sha256": "abc123...",
  "download_url": "/api/v1/mc/download/paper/1.21.1"
}
```

---

### 下载核心

**GET** `/api/v1/mc/download/{name}/{version}`

返回文件下载响应（302 重定向或直接文件流）

---

## 镜像站管理 API

### 获取镜像站信息

**GET** `/api/v1/mirror/info`

**响应示例：**
```json
{
  "server_name": "HYC Download Station",
  "version": "2.3.0",
  "uptime": 86400,
  "total_files": 1520,
  "total_size": 107374182400,
  "api_version": "v1"
}
```

---

### 刷新镜像源

**POST** `/api/v1/mirror/refresh` (需要认证)

**响应示例：**
```json
{
  "success": true,
  "message": "Mirror refresh initiated"
}
```

---

### 获取镜像状态

**GET** `/api/v1/mirror/status`

**响应示例：**
```json
{
  "running": true,
  "active_syncs": 2,
  "completed_syncs": 1250,
  "failed_syncs": 3,
  "last_sync": "2024-01-15T02:00:00"
}
```

---

### 获取同步速度

**GET** `/api/v1/mirror/speed`

**响应示例：**
```json
{
  "upload": 1024,
  "download": 5120,
  "unit": "KB/s"
}
```

---

### 获取带宽使用

**GET** `/api/v1/mirror/bandwidth`

**响应示例：**
```json
{
  "total": 10737418240,
  "used": 2147483648,
  "percentage": 20.0
}
```

---

## API v2 - 增强版 API

API v2 是 v1 的超集，添加了更多增强功能。

### 认证 API

#### 验证认证状态

**POST** `/api/v2/admin/auth/verify`

**成功响应 (200)：**
```json
{
  "valid": true,
  "level": "admin",
  "user_id": "admin",
  "permissions": ["admin:*", "files:*", "sync:*"],
  "expires_at": null
}
```

**未认证响应 (401)：**
```json
{
  "valid": false,
  "error": "Invalid or expired credentials"
}
```

---

### 增强搜索 API

#### 增强搜索

**GET** `/api/v2/search/enhanced`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词 |
| type | string | 否 | 搜索类型 (all, file, dir) |
| mode | string | 否 | 搜索模式 (fuzzy, exact, regex) |
| limit | integer | 否 | 返回结果数量限制 |
| offset | integer | 否 | 偏移量 |

**响应示例：**
```json
{
  "query": "ubuntu",
  "total": 25,
  "results": [
    {
      "name": "ubuntu-22.04.iso",
      "path": "ubuntu/ubuntu-22.04.iso",
      "type": "file",
      "size": 4588563456,
      "size_formatted": "4.3 GB",
      "modified": "2024-01-15T10:30:00"
    }
  ],
  "search_mode": "fuzzy",
  "took_ms": 15
}
```

#### 按标签搜索

**GET** `/api/v2/search/by-tag`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| tag | string | 是 | 标签名称 |
| limit | integer | 否 | 返回结果数量限制 |

#### 按日期搜索

**GET** `/api/v2/search/by-date`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| from | string | 否 | 开始日期 (ISO格式) |
| to | string | 否 | 结束日期 (ISO格式) |
| order | string | 否 | 排序 (asc, desc) |

---

### 增强统计 API

#### 详细统计

**GET** `/api/v2/stats/detailed`

**响应示例：**
```json
{
  "total_files": 1520,
  "total_dirs": 245,
  "total_size": 107374182400,
  "total_size_formatted": "100.0 GB",
  "downloads_total": 52340,
  "downloads_today": 1250,
  "downloads_week": 8750,
  "file_types": {
    "application/octet-stream": 850,
    "text/plain": 320,
    "image/png": 150
  },
  "top_downloads": [
    {"path": "ubuntu-22.04.iso", "count": 1523}
  ]
}
```

#### 热门文件

**GET** `/api/v2/stats/trending`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| period | string | 否 | 时间周期 (day, week, month) |
| limit | integer | 否 | 返回数量限制 |

#### 下载趋势

**GET** `/api/v2/stats/download-trend`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| from | string | 否 | 开始日期 |
| to | string | 否 | 结束日期 |
| period | string | 否 | 聚合周期 (hour, day, week) |

#### 按周期下载统计

**GET** `/api/v2/stats/download-by-period`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| period | string | 否 | 周期 (hour, day, week, month) |
| limit | integer | 否 | 返回数量限制 |

#### 下载排行

**GET** `/api/v2/stats/rank`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 否 | 排行类型 (downloads, size, recent) |
| limit | integer | 否 | 返回数量限制 |

---

### 文件操作 API

#### 文件元数据

**GET** `/api/v2/file/{path}/metadata`

**PUT** `/api/v2/file/{path}/metadata` (需要认证)

**请求体：**
```json
{
  "tags": ["linux", "os", "lts"],
  "description": "Ubuntu 22.04 LTS Server",
  "custom_fields": {
    "version": "22.04",
    "architecture": "amd64"
  }
}
```

**响应示例：**
```json
{
  "path": "ubuntu-22.04.iso",
  "name": "ubuntu-22.04.iso",
  "size": 4588563456,
  "modified": "2024-01-15T10:30:00",
  "tags": ["linux", "os", "lts"],
  "description": "Ubuntu 22.04 LTS Server",
  "custom_fields": {
    "version": "22.04",
    "architecture": "amd64"
  },
  "created_at": "2024-01-10T08:00:00",
  "last_accessed": "2024-01-15T10:30:00"
}
```

#### 文件版本

**GET** `/api/v2/file/{path}/versions`

**POST** `/api/v2/file/{path}/versions` (需要认证)

**响应示例：**
```json
{
  "path": "config.json",
  "current_version": 3,
  "versions": [
    {
      "version": 3,
      "modified": "2024-01-15T10:30:00",
      "modified_by": "admin",
      "size": 2048,
      "changes": "Updated timeout settings"
    },
    {
      "version": 2,
      "modified": "2024-01-10T08:00:00",
      "modified_by": "admin",
      "size": 1920,
      "changes": "Added new endpoints"
    }
  ]
}
```

#### 缩略图

**GET** `/api/v2/file/{path}/thumbnail`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| size | string | 否 | 尺寸 (small, medium, large) |

**响应：** 图片文件或 404

#### 批量元数据操作

**GET** `/api/v2/metadata/batch`

**PUT** `/api/v2/metadata/batch` (需要认证)

**请求体：**
```json
{
  "files": ["file1.txt", "file2.txt"],
  "action": "add_tags",
  "tags": ["batch", "uploaded"]
}
```

---

### 监控 API

#### 实时监控

**GET** `/api/v2/monitor/realtime`

**响应示例：**
```json
{
  "cpu": {
    "percent": 35.5,
    "cores": 4,
    "freq_mhz": 2400
  },
  "memory": {
    "total": 8589934592,
    "used": 3221225472,
    "percent": 37.5,
    "available": 5368709120
  },
  "disk": {
    "total": 536870912000,
    "used": 107374182400,
    "percent": 20.0,
    "read_bytes": 10485760,
    "write_bytes": 5242880
  },
  "network": {
    "rx_bytes": 1048576000,
    "tx_bytes": 524288000,
    "rx_speed": "1.2 MB/s",
    "tx_speed": "512 KB/s",
    "connections": 45
  },
  "uptime": 86400,
  "timestamp": "2024-01-15T10:30:00"
}
```

#### 监控历史

**GET** `/api/v2/monitor/history`

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| metric | string | 否 | 指标类型 (cpu, memory, disk, network) |
| from | string | 否 | 开始时间 |
| to | string | 否 | 结束时间 |
| interval | string | 否 | 采样间隔 |

#### 详细监控

**GET** `/api/v2/monitor/detailed`

---

### 健康检查 API

#### 镜像源健康检查

**GET** `/api/v2/health/sources`

**响应示例：**
```json
{
  "sources": [
    {
      "name": "ubuntu-releases",
      "status": "healthy",
      "latency_ms": 45,
      "last_check": "2024-01-15T10:25:00",
      "success_rate": 99.5
    },
    {
      "name": "debian-cd",
      "status": "degraded",
      "latency_ms": 120,
      "last_check": "2024-01-15T10:25:00",
      "success_rate": 95.0,
      "message": "High latency detected"
    }
  ],
  "total": 5,
  "healthy": 4,
  "degraded": 1,
  "unhealthy": 0
}
```

#### 检查特定镜像源

**GET** `/api/v2/health/check/{name}

**响应示例：**
```json
{
  "name": "ubuntu-releases",
  "status": "healthy",
  "latency_ms": 45,
  "http_code": 200,
  "last_check": "2024-01-15T10:30:00",
  "message": "Connection successful"
}
```

#### 故障切换

**GET** `/api/v2/health/failover`

**响应示例：**
```json
{
  "enabled": true,
  "auto_failover": true,
  "current_primary": "ubuntu-releases",
  "fallback": "ubuntu-alternate",
  "failover_count": 2,
  "last_failover": "2024-01-14T02:00:00"
}
```

**POST** `/api/v2/health/failover/{type}` (需要认证)

触发手动故障切换

#### 健康检查统计

**GET** `/api/v2/health/stats`

---

### Webhooks API

#### 列出 Webhooks

**GET** `/api/v2/webhooks` (需要 admin 权限)

**响应示例：**
```json
{
  "webhooks": [
    {
      "id": "wh_abc123",
      "name": "Download Notification",
      "url": "https://example.com/webhook",
      "events": ["download", "sync.complete"],
      "enabled": true,
      "created_at": "2024-01-10T10:00:00",
      "last_triggered": "2024-01-15T10:25:00",
      "trigger_count": 1250,
      "success_rate": 99.8
    }
  ],
  "count": 1
}
```

#### 创建 Webhook

**POST** `/api/v2/webhooks` (需要 admin 权限)

**请求体：**
```json
{
  "name": "New Webhook",
  "url": "https://example.com/webhook",
  "events": ["download", "sync.complete"],
  "secret": "webhook-secret-key",
  "headers": {
    "X-Custom-Header": "value"
  }
}
```

#### 获取 Webhook

**GET** `/api/v2/webhooks/{id}` (需要 admin 权限)

#### 更新 Webhook

**PUT** `/api/v2/webhooks/{id}` (需要 admin 权限)

#### 删除 Webhook

**DELETE** `/api/v2/webhooks/{id}` (需要 admin 权限)

#### 测试 Webhook

**POST** `/api/v2/webhooks/{id}/test` (需要 admin 权限)

**响应示例：**
```json
{
  "success": true,
  "webhook_id": "wh_abc123",
  "status_code": 200,
  "response_time": 150,
  "response_body": "{\"status\":\"ok\"}"
}
```

#### Webhook 交付历史

**GET** `/api/v2/webhooks/{id}/deliveries` (需要 admin 权限)

#### Webhook 统计

**GET** `/api/v2/webhooks/{id}/stats` (需要 admin 权限)

---

### 同步管理 API

#### 获取同步源

**GET** `/api/v2/sync/sources` (需要认证)

**POST** `/api/v2/sync/sources` (需要认证)

#### 控制同步

**POST** `/api/v2/sync/{name}/start` (需要认证)

**POST** `/api/v2/sync/{name}/stop` (需要认证)

**GET** `/api/v2/sync/{name}/status` (需要认证)

#### 同步历史

**GET** `/api/v2/sync/history` (需要认证)

#### 同步软件包

**POST** `/api/v2/sync/packages` (需要认证)

**GET** `/api/v2/sync/packages/{name}/status` (需要认证)

---

### 缓存管理 API

#### 缓存统计

**GET** `/api/v2/cache/stats` (需要认证)

#### 清理缓存

**POST** `/api/v2/cache/clean` (需要认证)

**请求体：**
```json
{
  "pattern": "*.tmp",
  "older_than": 86400
}
```

#### 缓存使用

**GET** `/api/v2/cache/usage` (需要认证)

**响应示例：**
```json
{
  "total_size": 10737418240,
  "total_size_formatted": "10.0 GB",
  "file_count": 1520,
  "by_type": {
    "pypi": 5368709120,
    "npm": 2684354560,
    "docker": 2147483648
  }
}
```

#### 热门缓存

**GET** `/api/v2/cache/popular` (需要认证)

---

### 缓存预热 API

#### 预热状态

**GET** `/api/v2/cache/prewarm` (需要认证)

**POST** `/api/v2/cache/prewarm` (需要认证)

**请求体：**
```json
{
  "urls": [
    "https://pypi.org/packages/source/d/django/Django-5.0.tar.gz",
    "https://registry.npmjs.org/react/-/react-18.2.0.tgz"
  ],
  "priority": "high"
}
```

#### 预热统计

**GET** `/api/v2/cache/prewarm/stats` (需要认证)

#### 预热项目

**GET** `/api/v2/cache/prewarm/items` (需要认证)

**POST** `/api/v2/cache/prewarm/items` (需要认证)

#### 预热历史

**GET** `/api/v2/cache/prewarm/history` (需要认证)

#### 清空预热队列

**POST** `/api/v2/cache/prewarm/clear` (需要认证)

#### 热门预热

**GET** `/api/v2/cache/prewarm/popular` (需要认证)

**POST** `/api/v2/cache/prewarm/popular` (需要认证)

#### 预热配置

**GET** `/api/v2/cache/prewarm/config` (需要认证)

**PUT** `/api/v2/cache/prewarm/config` (需要认证)

---

### 镜像加速 API

#### 列出镜像

**GET** `/api/v2/mirrors` (需要认证)

**POST** `/api/v2/mirrors` (需要认证)

**请求体：**
```json
{
  "name": "pypi-cn",
  "type": "pypi",
  "url": "https://pypi.cn",
  "enabled": true
}
```

#### 管理镜像

**PUT** `/api/v2/mirrors/{name}` (需要认证)

**DELETE** `/api/v2/mirrors/{name}` (需要认证)

#### 启用/禁用镜像

**PUT** `/api/v2/mirrors/{name}/enable` (需要认证)

**请求体：**
```json
{
  "enabled": true
}
```

#### 刷新镜像

**POST** `/api/v2/mirrors/{name}/refresh` (需要认证)

#### PyPI 镜像

**GET** `/api/v2/mirrors/pypi/{path}`

#### NPM 镜像

**GET** `/api/v2/mirrors/npm/{path}`

#### Go 镜像

**GET** `/api/v2/mirrors/go/{path}`

#### Docker 镜像

**GET** `/api/v2/mirrors/docker/{path}`

---

### 用户管理 API

#### 用户登录

**POST** `/api/v2/user/login`

**请求体：**
```json
{
  "username": "admin",
  "password": "password123"
}
```

**响应示例：**
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": 1736841600
}
```

#### 修改密码

**POST** `/api/v2/user/password` (需要认证)

**请求体：**
```json
{
  "old_password": "oldpassword",
  "new_password": "newpassword123"
}
```

#### 登录日志

**GET** `/api/v2/user/login-logs` (需要认证)

---

### 配置管理 API

#### 获取配置

**GET** `/api/v2/config` (需要 admin 权限)

**PUT** `/api/v2/config` (需要 admin 权限)

#### 重载配置

**POST** `/api/v2/config/reload` (需要 admin 权限)

**响应示例：**
```json
{
  "success": true,
  "message": "Configuration reloaded",
  "changes": 3
}
```

#### 配置变更历史

**GET** `/api/v2/config/changes` (需要 admin 权限)

---

### 告警管理 API

#### 获取告警

**GET** `/api/v2/alerts` (需要认证)

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| severity | string | 否 | 严重程度 (info, warning, error, critical) |
| acknowledged | boolean | 否 | 是否已确认 |
| limit | integer | 否 | 返回数量限制 |

**响应示例：**
```json
{
  "alerts": [
    {
      "id": "alert_001",
      "severity": "warning",
      "title": "High CPU Usage",
      "message": "CPU usage above 80% for 5 minutes",
      "timestamp": "2024-01-15T10:30:00",
      "acknowledged": false,
      "source": "monitor"
    }
  ],
  "count": 1,
  "unacknowledged": 1
}
```

#### 确认告警

**POST** `/api/v2/alerts/{id}/acknowledge` (需要认证)

#### 清空告警

**POST** `/api/v2/alerts/clear` (需要 admin 权限)

**请求体：**
```json
{
  "severity": "info",
  "older_than": 86400
}
```

#### 测试告警

**POST** `/api/v2/alerts/test` (需要 admin 权限)

**请求体：**
```json
{
  "type": "email",
  "recipients": ["admin@example.com"]
}
```

#### 告警配置

**GET** `/api/v2/alerts/config` (需要 admin 权限)

**PUT** `/api/v2/alerts/config` (需要 admin 权限)

**请求体：**
```json
{
  "email": {
    "enabled": true,
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "recipients": ["admin@example.com"]
  },
  "webhook": {
    "enabled": true,
    "url": "https://example.com/alerts"
  },
  "rules": [
    {
      "name": "High CPU",
      "condition": "cpu.percent > 80",
      "severity": "warning",
      "actions": ["email", "webhook"]
    }
  ]
}
```

---

### Prometheus 指标

**GET** `/api/v2/metrics`

返回 Prometheus 格式的指标数据。

---

### 活动日志 API

**GET** `/api/v2/activity` (需要认证)

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 否 | 活动类型 |
| limit | integer | 否 | 返回数量限制 |
| offset | integer | 否 | 偏移量 |

**响应示例：**
```json
{
  "activities": [
    {
      "id": 1001,
      "type": "file.download",
      "user": "admin",
      "path": "ubuntu-22.04.iso",
      "ip": "192.168.1.100",
      "timestamp": "2024-01-15T10:30:00",
      "details": {
        "size": "4.3 GB"
      }
    }
  ],
  "count": 1,
  "total": 52340
}
```

---

### 服务器管理 API

#### 重启管理

**GET** `/api/v2/server/restart` (需要认证)

**POST** `/api/v2/server/restart` (需要 admin 权限)

**请求体：**
```json
{
  "schedule": "2024-01-15T23:00:00",
  "notify_users": true
}
```

**响应示例：**
```json
{
  "success": true,
  "scheduled": true,
  "restart_time": "2024-01-15T23:00:00",
  "pending_requests": 15
}
```

#### 确认重启

**POST** `/api/v2/server/restart/confirm` (需要认证)

#### 立即重启

**POST** `/api/v2/server/restart/immediate` (需要 admin 权限)

#### 待处理请求

**GET** `/api/v2/server/restart/pending` (需要 admin 权限)

#### 重启历史

**GET** `/api/v2/server/restart/history` (需要 admin 权限)

#### 重启配置

**GET** `/api/v2/server/restart/config` (需要 admin 权限)

**PUT** `/api/v2/server/restart/config` (需要 admin 权限)

**请求体：**
```json
{
  "require_confirmation": true,
  "confirmation_timeout": 300,
  "notify_before_restart": true,
  "notify_seconds_before": 60,
  "allowed_users": ["admin"]
}
```

#### 服务器信息

**GET** `/api/v2/server/info`

**响应示例：**
```json
{
  "version": "2.3.0",
  "uptime": 86400,
  "hostname": "hyc-server",
  "platform": "Linux",
  "platform_version": "Ubuntu 22.04",
  "python_version": "3.11.0",
  "arch": "x86_64",
  "cpu_count": 4,
  "memory_total": 8589934592,
  "disk_total": 536870912000,
  "started_at": "2024-01-14T10:30:00"
}
```

---

### API 文档 API

#### 获取 API 文档

**GET** `/api/v2/api-docs.json`

**GET** `/api/v2/api-docs.yaml`

#### 生成 API 文档

**POST** `/api/v2/api-docs/generate` (需要 admin 权限)

---

## WebSocket

### 连接

**GET** `/ws`

建立 WebSocket 连接以接收实时更新。

**响应：** 101 Switching Protocols

---

## SSE 事件流

### 订阅

**GET** `/sse/stream`

订阅 Server-Sent Events 实时更新。

**响应：** 200 OK (流连接)

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 405 | 方法不允许 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## 状态码说明

| 状态码 | 说明 |
|--------|------|
| 101 | 连接升级成功 (WebSocket) |
| 200 | 成功 |
| 206 | 部分内容 (断点续传) |
| 301 | 永久重定向 |
| 304 | 未修改 |
| 416 | 请求范围不符合 |

---

> 最后更新: 2026-02-19
> 版本: 2.3.0
