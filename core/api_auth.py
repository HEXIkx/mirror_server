#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API认证模块
提供细粒度的API权限控制，支持管理员认证
"""

import os
import json
import hashlib
import time
import secrets
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps


# class AuthLevel(Enum):  # 预留：用于细粒度权限控制
#     """认证级别"""
#     NONE = "none"      # 无需认证
#     USER = "user"      # 普通用户
#     ADMIN = "admin"    # 管理员


@dataclass
class AdminKey:
    """管理员密钥"""
    key_id: str                    # 密钥ID
    key_hash: str                 # 密钥哈希
    name: str                    # 密钥名称
    level: str = "admin"         # 权限级别
    created_at: float = field(default_factory=time.time)
    last_used: float = None       # 最后使用时间
    expires_at: float = None     # 过期时间
    allowed_ips: List[str] = field(default_factory=list)  # 允许的IP
    enabled: bool = True
    permissions: List[str] = field(default_factory=list)  # 允许的API路径

    def is_valid(self) -> bool:
        """检查密钥是否有效"""
        if not self.enabled:
            return False

        # 检查过期时间
        if self.expires_at and time.time() > self.expires_at:
            return False

        return True


@dataclass
class AuthSession:
    """认证会话"""
    session_id: str
    user_id: str
    level: str
    created_at: float
    expires_at: float
    last_activity: float
    permissions: List[str]


class APIAuthManager:
    """API认证管理器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.admin_keys: Dict[str, AdminKey] = {}
        self.sessions: Dict[str, AuthSession] = {}

        # 配置文件路径
        self.keys_file = config.get('admin_keys_file', 'admin_keys.json') if config else 'admin_keys.json'
        self.sessions_file = config.get('auth_sessions_file', 'auth_sessions.json') if config else 'auth_sessions.json'

        # 会话超时时间
        self.session_timeout = config.get('auth_session_timeout', 3600) if config else 3600

        # Cookie名称
        self.cookie_name = 'hyc_auth'
        self.cookie_max_age = config.get('auth_cookie_max_age', 86400) if config else 86400

        # IP 白名单
        self.ip_whitelist = config.get('ip_whitelist', []) if config else []
        self.ip_whitelist_enabled = config.get('ip_whitelist_enabled', False) if config else False

    @property
    def db(self):
        """动态获取数据库实例"""
        # 每次都从 config 中获取最新的 db 实例
        return self.config.get('_db_instance')

    def _get_client_ip(self, handler) -> str:
        """从 handler 获取客户端 IP"""
        try:
            # 尝试从 X-Forwarded-For 获取真实 IP
            forwarded = handler.headers.get('X-Forwarded-For')
            if forwarded:
                return forwarded.split(',')[0].strip()
            # 获取连接地址
            return handler.client_address[0]
        except Exception:
            return None

    def _check_ip_whitelist(self, ip: str) -> bool:
        """检查 IP 是否在白名单中"""
        if not self.ip_whitelist_enabled or not self.ip_whitelist:
            # 未启用白名单或白名单为空，允许通过
            return True

        if not ip:
            # 没有 IP 信息，拒绝
            return False

        import ipaddress
        for pattern in self.ip_whitelist:
            try:
                # 尝试解析为网络地址 (CIDR)
                if '/' in pattern:
                    network = ipaddress.ip_network(pattern, strict=False)
                    if ipaddress.ip_address(ip) in network:
                        return True
                # 精确匹配
                elif pattern == ip:
                    return True
            except ValueError:
                # 不是有效的 CIDR 或 IP，继续下一个
                continue

        return False

    # === 密钥管理 ===

    def create_admin_key(self, name: str, level: str = "admin",
                        expires_at: float = None,
                        allowed_ips: List[str] = None,
                        permissions: List[str] = None) -> dict:
        """创建新的管理员密钥"""
        key_id = secrets.token_hex(8)
        key = secrets.token_hex(32)

        # 存储密钥哈希
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        admin_key = AdminKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            level=level,
            expires_at=expires_at,
            allowed_ips=allowed_ips or [],
            permissions=permissions or ['*'],
            enabled=True
        )

        self.admin_keys[key_id] = admin_key
        self._save_admin_keys()

        # 返回密钥（只返回一次，之后不再显示）
        return {
            "key_id": key_id,
            "key": key,  # 只返回一次
            "name": name,
            "level": level,
            "expires_at": expires_at,
            "message": "请妥善保管此密钥，只显示一次！"
        }

    def delete_admin_key(self, key_id: str) -> bool:
        """删除管理员密钥"""
        if key_id in self.admin_keys:
            del self.admin_keys[key_id]
            self._save_admin_keys()
            return True
        return False

    def list_admin_keys(self) -> List[dict]:
        """列出所有管理员密钥（不包含密钥内容）"""
        return [
            {
                "key_id": k.key_id,
                "name": k.name,
                "level": k.level,
                "created_at": k.created_at,
                "last_used": k.last_used,
                "expires_at": k.expires_at,
                "enabled": k.enabled,
                "permissions": k.permissions,
                "allowed_ips": k.allowed_ips
            }
            for k in self.admin_keys.values()
        ]

    def disable_admin_key(self, key_id: str) -> bool:
        """禁用管理员密钥"""
        if key_id in self.admin_keys:
            self.admin_keys[key_id].enabled = False
            self._save_admin_keys()
            return True
        return False

    def enable_admin_key(self, key_id: str) -> bool:
        """启用管理员密钥"""
        if key_id in self.admin_keys:
            self.admin_keys[key_id].enabled = True
            self._save_admin_keys()
            return True
        return False

    # === 认证验证 ===

    def validate_key(self, key: str, client_ip: str = None) -> Optional[dict]:
        """验证管理员密钥"""
        if not key:
            return None

        # 首先检查是否是静态 auth_token
        static_token = self.config.get('auth_token')
        if static_token and key == static_token:
            return {
                "valid": True,
                "key_id": "static_token",
                "name": "Static Token",
                "level": "admin",
                "permissions": ["*"]
            }

        # 然后检查 admin_keys 中的密钥
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        for key_id, admin_key in self.admin_keys.items():
            if admin_key.key_hash == key_hash:
                # 检查是否有效
                if not admin_key.is_valid():
                    return {"valid": False, "error": "密钥已禁用或过期"}

                # 检查IP限制
                if admin_key.allowed_ips and client_ip:
                    if not self._ip_matches(client_ip, admin_key.allowed_ips):
                        return {"valid": False, "error": "IP不在允许列表中"}

                # 更新最后使用时间
                admin_key.last_used = time.time()
                self._save_admin_keys()

                return {
                    "valid": True,
                    "key_id": key_id,
                    "name": admin_key.name,
                    "level": admin_key.level,
                    "permissions": admin_key.permissions
                }

        return {"valid": False, "error": "无效的密钥"}

    def validate_cookie(self, cookie_value: str, client_ip: str = None) -> Optional[dict]:
        """验证认证Cookie"""
        if not cookie_value:
            return None

        # Cookie格式: session_id.timestamp.signature
        parts = cookie_value.split('.')
        if len(parts) != 3:
            return None

        session_id, timestamp, signature = parts

        # 检查会话是否存在
        session = self.sessions.get(session_id)
        if not session:
            return None

        # 检查是否过期
        if time.time() > session.expires_at:
            del self.sessions[session_id]
            return None

        # 验证签名
        expected_sig = self._generate_signature(session_id, timestamp, session.user_id)
        if signature != expected_sig:
            return None

        # 检查IP限制
        if session.level == "admin":
            # 可以添加IP检查逻辑
            pass
        session.last_activity = time.time()

        return {
            "valid": True,
            "session_id": session_id,
            "user_id": session.user_id,
            "level": session.level,
            "permissions": session.permissions
        }

    def validate_session_id(self, session_id: str) -> Optional[dict]:
        """验证会话ID"""
        if not session_id:
            return None

        # 检查会话是否存在
        session = self.sessions.get(session_id)
        if not session:
            return None

        # 检查是否过期
        if time.time() > session.expires_at:
            del self.sessions[session_id]
            return None

        # 更新最后活动时间
        session.last_activity = time.time()

        return {
            "valid": True,
            "session_id": session_id,
            "user_id": session.user_id,
            "level": session.level,
            "permissions": session.permissions
        }

    def validate_request(self, handler, required_level: str = "admin") -> dict:
        """
        验证请求的认证状态

        支持的认证方式（优先级从高到低）：
        1. Authorization: Bearer <key>
        2. Authorization: Basic <credentials> (用户名:密码)
        3. X-API-Key: <key>
        4. Cookie: hyc_auth=<session>
        5. ?key=<key> (查询参数)
        """
        import base64

        # 获取认证信息
        auth_header = handler.headers.get('Authorization')
        api_key = handler.headers.get('X-API-Key')
        cookie = handler.headers.get('Cookie', '')
        client_ip = handler.client_address[0] if hasattr(handler, 'client_address') else None

        # 提取cookie值
        cookie_value = None
        for c in cookie.split(';'):
            c = c.strip()
            if c.startswith(f'{self.cookie_name}='):
                cookie_value = c[len(self.cookie_name)+1:]
                break

        # 获取查询参数中的key
        parsed_path = handler.path.split('?')
        query_key = None
        if len(parsed_path) > 1:
            from urllib.parse import parse_qs
            query = parse_qs(parsed_path[1])
            query_key = query.get('key', [None])[0]

        # 按优先级验证
        # 1. Bearer Token
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]
            result = self.validate_key(token, client_ip)
            if result and result.get('valid'):
                return {
                    "authenticated": True,
                    "method": "bearer",
                    **result
                }

        # 2. Basic Auth (用户名:密码)
        if auth_header and auth_header.startswith('Basic '):
            try:
                credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
                if ':' in credentials:
                    username, password = credentials.split(':', 1)
                    result = self.validate_basic_auth(username, password, client_ip)
                    if result and result.get('valid'):
                        return {
                            "authenticated": True,
                            "method": "basic",
                            **result
                        }
            except Exception:
                pass

        # 3. API Key Header
        if api_key:
            result = self.validate_key(api_key, client_ip)
            if result and result.get('valid'):
                return {
                    "authenticated": True,
                    "method": "api_key",
                    **result
                }

        # 3. Cookie
        if cookie_value:
            result = self.validate_cookie(cookie_value, client_ip)
            if result and result.get('valid'):
                return {
                    "authenticated": True,
                    "method": "cookie",
                    **result
                }

        # 4. Query Parameter
        if query_key:
            result = self.validate_key(query_key, client_ip)
            if result and result.get('valid'):
                return {
                    "authenticated": True,
                    "method": "query",
                    **result
                }

        # 未认证
        return {
            "authenticated": False,
            "error": "Authentication required",
            "required_level": required_level
        }

    def validate_basic_auth(self, username: str, password: str, client_ip: str = None) -> dict:
        """
        验证Basic Auth用户名密码

        Args:
            username: 用户名
            password: 密码
            client_ip: 客户端IP

        Returns:
            认证结果字典，valid=True表示认证成功
        """
        # 获取配置中的用户名密码
        config_user = self.config.get('auth_user', '')
        config_pass = self.config.get('auth_pass', '')
        auth_type = self.config.get('auth_type', 'none')

        # IP 白名单检查
        if not self._check_ip_whitelist(client_ip):
            if self.db:
                self.db.add_login_log(username, client_ip, 'failed', 'IP不在白名单')
            return {"valid": False, "reason": "IP不在白名单内"}

        # 如果认证类型为none，任何用户都可以通过
        if auth_type == 'none':
            return {
                "valid": True,
                "user_id": username or 'anonymous',
                "level": "admin",
                "key_id": "basic_auth",
                "name": f"Basic Auth - {username or 'anonymous'}",
                "permissions": ["*"]
            }

        # 优先验证数据库（如果数据库有用户）
        if self.db:
            user = self.db.get_user(username)
            if user:
                if self.db.verify_password(password, user['password_hash']):
                    self.db.add_login_log(username, client_ip, 'success', '数据库验证')
                    return {
                        "valid": True,
                        "user_id": user['id'],
                        "username": username,
                        "level": user.get('role', 'admin'),
                        "key_id": "db_auth",
                        "name": f"User - {username}",
                        "permissions": ["*"]
                    }
                else:
                    self.db.add_login_log(username, client_ip, 'failed', '数据库密码错误')
                    return {"valid": False, "reason": "用户名或密码错误"}

        # 回退到配置文件验证
        if username == config_user and password == config_pass:
            if self.db:
                self.db.add_login_log(username, client_ip, 'success', '配置文件验证')
            return {
                "valid": True,
                "user_id": username,
                "level": "admin",
                "key_id": "config_auth",
                "name": f"Basic Auth - {username}",
                "permissions": ["*"]
            }

        # 记录失败日志
        if self.db:
            self.db.add_login_log(username, client_ip, 'failed', '配置验证失败')

        return {"valid": False}

    def check_permission(self, auth_result: dict, permission: str) -> bool:
        """检查是否有权限访问特定API"""
        if not auth_result.get('authenticated'):
            return False

        permissions = auth_result.get('permissions', [])

        # '*' 表示所有权限
        if '*' in permissions:
            return True

        # 检查具体权限
        # 支持通配符匹配
        if permission in permissions:
            return True

        # 检查通配符匹配
        for p in permissions:
            if p.endswith('*'):
                prefix = p.rstrip('*')
                if permission.startswith(prefix):
                    return True

        return False

    # === 会话管理 ===

    def create_session(self, user_id: str, level: str,
                       permissions: List[str] = None) -> dict:
        """创建认证会话"""
        session_id = secrets.token_hex(32)
        timestamp = time.time()

        session = AuthSession(
            session_id=session_id,
            user_id=user_id,
            level=level,
            created_at=timestamp,
            expires_at=timestamp + self.session_timeout,
            last_activity=timestamp,
            permissions=permissions or ['*']
        )

        self.sessions[session_id] = session
        self._save_sessions()

        # 生成Cookie值
        signature = self._generate_signature(session_id, timestamp, user_id)
        cookie_value = f"{session_id}.{timestamp}.{signature}"

        return {
            "session_id": session_id,
            "cookie_name": self.cookie_name,
            "cookie_value": cookie_value,
            "cookie_max_age": self.cookie_max_age,
            "expires": timestamp + self.session_timeout
        }

    def destroy_session(self, session_id: str) -> bool:
        """销毁会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._save_sessions()
            return True
        return False

    # === 内部方法 ===

    def _generate_signature(self, session_id: str, timestamp: str, user_id: str) -> str:
        """生成签名"""
        # 使用配置的密钥或生成临时密钥
        secret = self.config.get('auth_secret', 'default_secret_change_me')
        data = f"{session_id}.{timestamp}.{user_id}.{secret}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _ip_matches(self, client_ip: str, allowed_ips: List[str]) -> bool:
        """检查IP是否匹配"""
        for pattern in allowed_ips:
            if pattern == client_ip:
                return True
            # 支持CIDR范围
            if '/' in pattern:
                from ipaddress import ip_network, ip_address
                try:
                    network = ip_network(pattern, strict=False)
                    if ip_address(client_ip) in network:
                        return True
                except Exception:
                    pass
        return False

    def _load_admin_keys(self):
        """加载管理员密钥"""
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        key = AdminKey(
                            key_id=item['key_id'],
                            key_hash=item['key_hash'],
                            name=item['name'],
                            level=item.get('level', 'admin'),
                            created_at=item.get('created_at', time.time()),
                            last_used=item.get('last_used'),
                            expires_at=item.get('expires_at'),
                            allowed_ips=item.get('allowed_ips', []),
                            enabled=item.get('enabled', True),
                            permissions=item.get('permissions', ['*'])
                        )
                        self.admin_keys[key.key_id] = key
            except Exception as e:
                print(f"加载管理员密钥失败: {e}")

    def _save_admin_keys(self):
        """保存管理员密钥"""
        data = []
        for key in self.admin_keys.values():
            data.append({
                "key_id": key.key_id,
                "key_hash": key.key_hash,
                "name": key.name,
                "level": key.level,
                "created_at": key.created_at,
                "last_used": key.last_used,
                "expires_at": key.expires_at,
                "allowed_ips": key.allowed_ips,
                "enabled": key.enabled,
                "permissions": key.permissions
            })

        try:
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存管理员密钥失败: {e}")

    def _save_sessions(self):
        """保存会话"""
        data = []
        for session in self.sessions.values():
            data.append({
                "session_id": session.session_id,
                "user_id": session.user_id,
                "level": session.level,
                "created_at": session.created_at,
                "expires_at": session.expires_at,
                "last_activity": session.last_activity,
                "permissions": session.permissions
            })

        try:
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_stats(self) -> dict:
        """获取认证统计"""
        active_sessions = sum(
            1 for s in self.sessions.values()
            if time.time() < s.expires_at
        )

        return {
            "total_keys": len(self.admin_keys),
            "enabled_keys": sum(1 for k in self.admin_keys.values() if k.enabled),
            "active_sessions": active_sessions,
            "session_timeout": self.session_timeout
        }


# === API认证装饰器 ===

def require_auth(required_level: str = "admin", permission: str = None):
    """
    API认证装饰器

    使用方式:
        @require_auth()
        def api_endpoint(self, handler):
            ...

        @require_auth(permission="sync:start")
        def api_sync_start(self, handler):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, handler, *args, **kwargs):
            # 检查是否需要认证
            if required_level == "none":
                return func(self, handler, *args, **kwargs)

            # 获取配置中的auth_type
            config = getattr(handler, 'config', {})
            auth_type = config.get('auth_type', 'none')

            # 如果auth_type为none，跳过认证
            if auth_type == "none":
                # 设置一个默认的auth_result，以便后续代码使用
                handler.auth_result = {
                    "authenticated": True,
                    "level": "admin",
                    "user_id": "anonymous",
                    "permissions": ["*"]
                }
                return func(self, handler, *args, **kwargs)

            # 获取认证管理器
            auth_manager = getattr(handler, 'auth_manager', None)
            if not auth_manager:
                handler.send_json_response({
                    "error": "认证系统未初始化",
                    "code": "AUTH_NOT_INITIALIZED"
                }, 500)
                return

            # 验证请求
            auth_result = auth_manager.validate_request(handler, required_level)

            if not auth_result.get('authenticated'):
                # 返回认证要求信息
                handler.send_response(401)
                handler.send_header('WWW-Authenticate', 'Bearer realm="HYC API"')
                handler.send_header('Access-Control-Allow-Origin', '*')
                handler.send_json_response({
                    "error": "未认证或认证已过期",
                    "code": "UNAUTHORIZED",
                    "required_level": required_level,
                    "auth_methods": [
                        "Authorization: Bearer <key>",
                        "X-API-Key: <key>",
                        f"Cookie: {auth_manager.cookie_name}=<session>",
                        "?key=<key>"
                    ]
                })
                return

            # 检查权限
            if permission:
                if not auth_manager.check_permission(auth_result, permission):
                    handler.send_json_response({
                        "error": "权限不足",
                        "code": "FORBIDDEN",
                        "required_permission": permission
                    }, 403)
                    return

            # 将认证结果存入handler
            handler.auth_result = auth_result

            # 调用原函数
            return func(self, handler, *args, **kwargs)

        return wrapper
    return decorator


# === 需要认证的API端点定义 ===

# 格式: (HTTP方法, 路径模式, 需要的权限)
# 路径模式支持: * 匹配任意字符, ** 匹配多级路径
ADMIN_API_ENDPOINTS = {
    # 同步管理
    'POST:/api/v2/sync/*': 'sync:manage',
    'POST:/api/v2/sync/*/start': 'sync:start',
    'POST:/api/v2/sync/*/stop': 'sync:stop',
    'DELETE:/api/v2/sync/*': 'sync:manage',

    # 缓存管理
    'POST:/api/v2/cache/clean': 'cache:manage',
    'DELETE:/api/v2/cache/*': 'cache:manage',

    # Webhook管理
    'POST:/api/v2/webhooks': 'webhook:create',
    'PUT:/api/v2/webhooks/*': 'webhook:update',
    'DELETE:/api/v2/webhooks/*': 'webhook:delete',
    'POST:/api/v2/webhooks/*/trigger': 'webhook:trigger',

    # 管理员密钥管理
    'POST:/api/v2/admin/keys': 'admin:keys',
    'DELETE:/api/v2/admin/keys/*': 'admin:keys',
    'PUT:/api/v2/admin/keys/*': 'admin:keys',

    # 服务器配置
    'PUT:/api/v2/config': 'config:manage',
    'POST:/api/v2/server/reload': 'server:reload',

    # 文件管理（高危操作）
    'DELETE:/api/v2/files/*': 'files:delete',
    'PUT:/api/v2/files/*/rename': 'files:rename',

    # 用户管理
    'POST:/api/v2/users': 'users:create',
    'DELETE:/api/v2/users/*': 'users:delete',
    'PUT:/api/v2/users/*': 'users:update',

    # === API v1 文件操作认证 ===
    # 文件删除
    'DELETE:/api/v1/file/*': 'files:delete',

    # 目录创建
    'PUT:/api/v1/mkdir': 'files:create',

    # 文件上传
    'POST:/api/v1/upload': 'files:upload',

    # 批量操作
    'POST:/api/v1/batch': 'files:batch',

    # 归档操作
    'POST:/api/v1/archive': 'files:archive',
}


def check_endpoint_auth(method: str, path: str, auth_manager: APIAuthManager) -> dict:
    """检查端点是否需要认证"""
    # 精确匹配
    key = f"{method}:{path}"
    if key in ADMIN_API_ENDPOINTS:
        return {
            "required": True,
            "permission": ADMIN_API_ENDPOINTS[key]
        }

    # 前缀匹配
    for pattern, permission in ADMIN_API_ENDPOINTS.items():
        if '*' in pattern:
            pat_method, pat_path = pattern.split(':', 1)
            if method == pat_method or pat_method == '*':
                if pat_path.endswith('*'):
                    prefix = pat_path.rstrip('*').rstrip('/')
                    if path.startswith(prefix):
                        return {
                            "required": True,
                            "permission": permission
                        }

    return {
        "required": False,
        "permission": None
    }
