#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""API路由模块"""

import re
from urllib.parse import urlparse, parse_qs

from .v1 import APIv1
from .v2 import APIv2
from .admin import AdminAPI
from core.api_auth import APIAuthManager


class APIRouter:
    """API路由器 - 支持版本化API"""

    def __init__(self, config):
        self.config = config
        self.api_versions = {
            'v1': APIv1(config),
            'v2': APIv2(config)
        }
        self.default_version = config.get('api_version', 'v1')

        # 初始化认证管理器（使用共享实例）
        if not config.get('_auth_manager'):
            config['_auth_manager'] = APIAuthManager(config)
        self.auth_manager = config['_auth_manager']

        # 初始化Admin API
        self.admin_api = AdminAPI(config)

    def handle_request(self, handler, method, path, query):
        """处理API请求"""
        # 注入认证管理器到handler
        handler.auth_manager = self.auth_manager

        # 解析路径，提取API版本
        # 格式: /api/v1/... 或 /api/v2/... 或 /api/...

        # 移除 /api/ 前缀
        if path.startswith('api/'):
            api_path = path[4:]
        else:
            api_path = path

        # 解析版本号
        parts = api_path.split('/')
        if parts[0] in ['v1', 'v2']:
            api_version = parts[0]
            api_action = '/'.join(parts[1:]) if len(parts) > 1 else ''
        else:
            # 检查是否是直接访问的 admin API (不带版本前缀)
            if api_path.startswith('admin/'):
                admin_action = api_path[6:]  # 移除 'admin/'
                try:
                    self.admin_api.handle_request(handler, method, admin_action, {})
                except Exception as e:
                    handler.send_json_response({
                        "error": f"Admin API处理错误: {str(e)}",
                        "path": admin_action
                    }, 500)
                return
            else:
                handler.send_error(400, "未指定API请求版本/指定版本错误")
                return

        # 解析查询参数
        parsed_query = parse_qs(query)

        # 检查是否是 admin API (带版本前缀，如 /api/v2/admin/stats)
        # 注意：auth/verify 应该交给 APIv2 处理，而不是 admin_api
        if api_version in ['v1', 'v2'] and api_action.startswith('admin/') and not api_action.startswith('admin/auth'):
            admin_action = api_action[6:]  # 移除 'admin/'
            try:
                self.admin_api.handle_request(handler, method, admin_action, parsed_query)
            except Exception as e:
                handler.send_json_response({
                    "error": f"Admin API处理错误: {str(e)}",
                    "path": admin_action
                }, 500)
            return

        # 获取对应的API处理器
        api_handler = self.api_versions.get(api_version)
        if not api_handler:
            handler.send_json_response({
                "error": f"不支持的API版本: {api_version}",
                "supported_versions": list(self.api_versions.keys())
            }, 400)
            return

        # 调用对应的API处理器
        try:
            # 调试模式输出路由信息 (debug-api)
            if handler._is_debug_enabled('api'):
                msg = f"\n=== DEBUG API Router ===\n  Version: {api_version}\n  Action: {api_action}\n  Method: {method}\n  Query: {parsed_query}"
                handler._debug_log('api', msg, '\033[35m')

            api_handler.handle_request(handler, method, api_action, parsed_query)
        except Exception as e:
            if handler._is_debug_enabled('error'):
                import traceback
                tb_str = traceback.format_exc()
                msg = f"\n=== DEBUG API ERROR ===\n{tb_str}"
                handler._debug_log('error', msg, '\033[31m')
            handler.send_json_response({
                "error": f"API处理错误: {str(e)}",
                "version": api_version,
                "path": api_action
            }, 500)
