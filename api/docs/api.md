# HYC下载站 v2.2 - API 文档

## 快速开始

```bash
# 设置 API Key
export API_KEY="your-api-key-here"

# 测试健康检查
curl http://localhost:8080/api/v1/health

# 获取文件列表
curl http://localhost:8080/api/v1/files

# 认证请求示例
curl -H "X-API-Key: $API_KEY" http://localhost:8080/api/v2/admin/stats
```

## 认证方式

| 方式 | 说明 |
|------|------|
| `Authorization: Bearer <token>` | Bearer Token |
| `X-API-Key: <key>` | API Key (推荐) |
| `Cookie: hyc_auth=<session>` | Session Cookie |
| `?key=<query>` | Query Parameter |

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

**DELETE** `/api/v1/sync/{name}` (需要认证)

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

## 缓存管理

### 获取缓存统计

**GET** `/api/v1/cache/stats`

**响应示例：**
```json
{
  "size": 10737418240,
  "size_formatted": "10.0 GB",
  "count": 1520,
  "hit_rate": 85.5,
  "expired_count": 45,
  "last_clean": "2024-01-15T02:00:00"
}
```

---

### 清理缓存

**POST** `/api/v1/cache/clean` (需要认证)

**请求体 (可选)：**
```json
{
  "pattern": "*.tmp"
}
```

**响应示例：**
```json
{
  "success": true,
  "cleaned": 125,
  "freed": 1073741824,
  "freed_formatted": "1.0 GB"
}
```

---

### 清空缓存

**DELETE** `/api/v1/cache` (需要认证)

**响应示例：**
```json
{
  "success": true,
  "message": "Cache cleared",
  "previous_size": "10.0 GB",
  "entries_removed": 1520
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

## 认证管理

### 验证认证状态

**POST** `/api/v2/admin/auth/verify`

**成功响应 (200)：**
```json
{
  "valid": true,
  "level": "admin",
  "user_id": "admin",
  "permissions": ["admin:*", "files:*", "sync:*"],
  "expires_at": 1736841600
}
```

**未认证响应 (401)：**
```json
{
  "valid": false,
  "error": "Invalid or expired token"
}
```

---

### 列出 API 密钥

**GET** `/api/v2/admin/keys` (需要 admin 权限)

**响应示例：**
```json
{
  "keys": [
    {
      "key_id": "ky_abc123",
      "name": "Production API Key",
      "level": "admin",
      "created_at": 1705315200,
      "last_used": 1705318800,
      "expires_at": 1736851200,
      "enabled": true,
      "permissions": ["admin:*", "files:*", "sync:*"]
    }
  ],
  "count": 2
}
```

---

### 创建 API 密钥

**POST** `/api/v2/admin/keys` (需要 admin 权限)

**请求体：**
```json
{
  "name": "New API Key",
  "level": "user",
  "expires_at": 1736851200,
  "permissions": ["files:read", "stats:read"],
  "allowed_ips": ["192.168.1.0/24"]
}
```

**响应示例：**
```json
{
  "success": true,
  "key": {
    "key_id": "ky_ghi789",
    "key": "hyc_abc123def456...",
    "name": "New API Key",
    "level": "user",
    "created_at": 1705315200,
    "expires_at": 1736851200
  },
  "warning": "请立即保存密钥，关闭此页面后将无法再次查看"
}
```

---

### 删除密钥

**DELETE** `/api/v2/admin/keys/{key_id}` (需要 admin 权限)

**响应示例：**
```json
{
  "success": true,
  "message": "API key deleted",
  "key_id": "ky_abc123"
}
```

---

### 禁用/启用密钥

**PUT** `/api/v2/admin/keys/{key_id}/disable`
**PUT** `/api/v2/admin/keys/{key_id}/enable`

**响应示例：**
```json
{
  "success": true,
  "key_id": "ky_abc123",
  "enabled": false
}
```

---

### 列出活跃会话

**GET** `/api/v2/admin/sessions` (需要 admin 权限)

**响应示例：**
```json
{
  "sessions": [
    {
      "session_id": "sess_abc123",
      "user_id": "admin",
      "level": "admin",
      "created_at": 1705315200,
      "last_activity": 1705318800,
      "ip": "192.168.1.100",
      "expires_at": 1736851200
    }
  ],
  "count": 1
}
```

---

### 销毁会话

**DELETE** `/api/v2/admin/sessions/{session_id}` (需要 admin 权限)

**响应示例：**
```json
{
  "success": true,
  "message": "Session destroyed",
  "session_id": "sess_abc123"
}
```

---

### 获取认证统计

**GET** `/api/v2/admin/stats` (需要 admin 权限)

**响应示例：**
```json
{
  "total_keys": 15,
  "enabled_keys": 12,
  "disabled_keys": 3,
  "expired_keys": 2,
  "active_sessions": 5,
  "keys_by_level": {
    "admin": 3,
    "user": 12
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

> 最后更新: 2024-01-15
> 版本: 2.2.0
