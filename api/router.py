#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""API路由模块"""

import re
from urllib.parse import urlparse, parse_qs

from .v1 import APIv1
from .v2 import APIv2


class APIRouter:
    """API路由器 - 支持版本化API"""
    
    def __init__(self, config):
        self.config = config
        self.api_versions = {
            'v1': APIv1(config),
            'v2': APIv2(config)
        }
        self.default_version = config.get('api_version', 'v1')
        
    def handle_request(self, handler, method, path, query):
        """处理API请求"""
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
            # 没有指定版本，使用默认版本
            # api_version = self.default_version
            # api_action = api_path
            handler.send_error(400,"未指定API请求版本/指定版本错误")
            return
        
        # 解析查询参数
        parsed_query = parse_qs(query)
        
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
            api_handler.handle_request(handler, method, api_action, parsed_query)
        except Exception as e:
            handler.send_json_response({
                "error": f"API处理错误: {str(e)}",
                "version": api_version,
                "path": api_action
            }, 500)
