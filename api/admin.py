#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
管理员API处理器
提供管理员密钥管理和认证相关API
"""

import json
import time
from datetime import datetime
from core.api_auth import APIAuthManager, require_auth


class AdminAPI:
    """管理员API处理器"""

    def __init__(self, config: dict):
        self.config = config
        self.auth_manager = APIAuthManager(config)

    @require_auth(required_level="admin", permission="admin:keys")
    def handle_request(self, handler, method, path, query_params):
        """处理管理员API请求"""

        # 解析路径
        parts = path.strip('/').split('/')

        # 根路径 - 列出API
        if len(parts) == 0 or parts[0] == '':
            self._api_overview(handler)
            return

        action = parts[0]

        if action == 'keys':
            self._handle_keys(handler, method, parts[1:] if len(parts) > 1 else [])
        elif action == 'auth':
            self._handle_auth(handler, method, query_params)
        elif action == 'sessions':
            self._handle_sessions(handler, method, parts[1:] if len(parts) > 1 else [])
        elif action == 'stats':
            self._handle_stats(handler)
        else:
            handler.send_json_response({
                "error": f"Unknown admin action: {action}",
                "available_actions": ["keys", "auth", "sessions", "stats"]
            }, 404)

    def _api_overview(self, handler):
        """API概览"""
        handler.send_json_response({
            "name": "HYC Admin API",
            "version": "1.0",
            "description": "管理员认证和密钥管理API",
            "endpoints": {
                "GET /api/v2/admin/keys": "列出所有管理员密钥",
                "POST /api/v2/admin/keys": "创建新的管理员密钥",
                "DELETE /api/v2/admin/keys/{key_id}": "删除管理员密钥",
                "PUT /api/v2/admin/keys/{key_id}/disable": "禁用密钥",
                "PUT /api/v2/admin/keys/{key_id}/enable": "启用密钥",
                "GET /api/v2/admin/sessions": "列出活跃会话",
                "DELETE /api/v2/admin/sessions/{session_id}": "销毁会话",
                "POST /api/v2/admin/auth/verify": "验证认证状态",
                "GET /api/v2/admin/stats": "获取认证统计"
            },
            "authentication": {
                "methods": [
                    "Authorization: Bearer <key>",
                    "X-API-Key: <key>",
                    "Cookie: hyc_auth=<session>",
                    "?key=<key>"
                ]
            }
        })

    def _handle_keys(self, handler, method, parts):
        """处理密钥管理"""
        # POST /api/v2/admin/keys - 创建密钥
        if method == 'POST':
            self._create_key(handler, parts)
            return

        # GET /api/v2/admin/keys - 列出密钥（parts为空或只有'action'元素）
        if len(parts) == 0 or (len(parts) == 1 and parts[0] == 'keys'):
            if method == 'GET':
                self._list_keys(handler)
            else:
                handler.send_json_response({"error": "Invalid request"}, 400)
            return

        # parts格式: ['xxx', 'action'] 或 ['xxx']
        key_id = parts[0]
        action = parts[1] if len(parts) > 1 else None

        # GET /api/v2/admin/keys/{key_id} - 获取密钥详情
        if method == 'GET':
            self._get_key(handler, key_id)
        # DELETE /api/v2/admin/keys/{key_id} - 删除密钥
        elif method == 'DELETE':
            self._delete_key(handler, key_id)
        # PUT /api/v2/admin/keys/{key_id}/disable - 禁用密钥
        elif action == 'disable' and method == 'PUT':
            self._disable_key(handler, key_id)
        # PUT /api/v2/admin/keys/{key_id}/enable - 启用密钥
        elif action == 'enable' and method == 'PUT':
            self._enable_key(handler, key_id)
        else:
            handler.send_json_response({"error": "Invalid request"}, 400)

    def _list_keys(self, handler):
        """列出所有密钥"""
        keys = self.auth_manager.list_admin_keys()
        handler.send_json_response({
            "keys": keys,
            "count": len(keys)
        })

    def _create_key(self, handler, parts):
        """创建新密钥"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No data provided"}, 400)
            return

        try:
            data = json.loads(handler.rfile.read(content_length))

            name = data.get('name', f"Key-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            level = data.get('level', 'admin')
            expires_at = data.get('expires_at')
            allowed_ips = data.get('allowed_ips')
            permissions = data.get('permissions')

            result = self.auth_manager.create_admin_key(
                name=name,
                level=level,
                expires_at=expires_at,
                allowed_ips=allowed_ips,
                permissions=permissions
            )

            handler.send_json_response({
                "success": True,
                "key": result
            })

        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def _get_key(self, handler, key_id):
        """获取密钥详情"""
        keys = self.auth_manager.list_admin_keys()
        for key in keys:
            if key['key_id'] == key_id:
                handler.send_json_response({
                    "key": key
                })
                return

        handler.send_json_response({"error": "Key not found"}, 404)

    def _delete_key(self, handler, key_id):
        """删除密钥"""
        success = self.auth_manager.delete_admin_key(key_id)
        if success:
            handler.send_json_response({
                "success": True,
                "message": f"Key {key_id} deleted"
            })
        else:
            handler.send_json_response({"error": "Key not found"}, 404)

    def _disable_key(self, handler, key_id):
        """禁用密钥"""
        success = self.auth_manager.disable_admin_key(key_id)
        if success:
            handler.send_json_response({
                "success": True,
                "message": f"Key {key_id} disabled"
            })
        else:
            handler.send_json_response({"error": "Key not found"}, 404)

    def _enable_key(self, handler, key_id):
        """启用密钥"""
        success = self.auth_manager.enable_admin_key(key_id)
        if success:
            handler.send_json_response({
                "success": True,
                "message": f"Key {key_id} enabled"
            })
        else:
            handler.send_json_response({"error": "Key not found"}, 404)

    def _handle_auth(self, handler, method, query_params):
        """处理认证相关"""
        # POST /api/v2/admin/auth/verify - 验证当前认证状态
        if method == 'POST':
            auth_result = handler.auth_result if hasattr(handler, 'auth_result') else {}

            if auth_result.get('authenticated'):
                handler.send_json_response({
                    "authenticated": True,
                    "level": auth_result.get('level'),
                    "key_id": auth_result.get('key_id'),
                    "name": auth_result.get('name'),
                    "permissions": auth_result.get('permissions', [])
                })
            else:
                handler.send_json_response({
                    "authenticated": False
                }, 401)

        else:
            handler.send_json_response({"error": "Invalid method"}, 405)

    def _handle_sessions(self, handler, method, parts):
        """处理会话管理"""
        if method == 'GET':
            # 列出活跃会话
            sessions = []
            for session_id, session in self.auth_manager.sessions.items():
                if time.time() < session.expires_at:
                    sessions.append({
                        "session_id": session.session_id,
                        "user_id": session.user_id,
                        "level": session.level,
                        "created_at": session.created_at,
                        "expires_at": session.expires_at,
                        "last_activity": session.last_activity
                    })

            handler.send_json_response({
                "sessions": sessions,
                "count": len(sessions)
            })

        elif method == 'DELETE' and len(parts) >= 1 and parts[0]:
            # 销毁会话（parts格式: ['xxx'] 或 []）
            session_id = parts[0]
            success = self.auth_manager.destroy_session(session_id)
            if success:
                handler.send_json_response({
                    "success": True,
                    "message": f"Session {session_id} destroyed"
                })
            else:
                handler.send_json_response({"error": "Session not found"}, 404)

        else:
            handler.send_json_response({"error": "Invalid request"}, 400)

    def _handle_stats(self, handler):
        """获取认证统计"""
        stats = self.auth_manager.get_stats()
        handler.send_json_response(stats)
