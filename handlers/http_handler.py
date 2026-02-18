#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP请求处理模块"""

import os
import json
import re
import time
import mimetypes
import base64
import hashlib
import shutil
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse, parse_qs

from core.utils import format_file_size, get_file_hash, sanitize_filename, is_safe_path
from api.router import APIRouter
from mirrors import get_mirror_handler


class MirrorServerHandler(BaseHTTPRequestHandler):
    """镜像服务器请求处理器"""

    config = None
    sync_manager = None
    monitor = None  # 系统监控器实例
    protocol_version = 'HTTP/1.1'
    api_router = None
    debug_log_file = None  # 调试日志文件路径
    _debug_categories = set()  # 启用的调试类别
    _mirror_handlers = {}  # 镜像处理器实例缓存

    @classmethod
    def _setup_debug(cls, config):
        """根据配置设置调试模式"""
        if config is None:
            cls._debug_categories = set()
            cls.debug_log_file = None
            return

        # debug 可以是：
        # - true/false: 全局开启/关闭
        # - 列表: 只开启指定的类别
        debug_setting = config.get('debug', False)
        if debug_setting is True:
            # 全局开启所有
            cls._debug_categories = {'http', 'api', 'auth', 'v2', 'error', 'download'}
        elif isinstance(debug_setting, list):
            cls._debug_categories = set(debug_setting)
        else:
            cls._debug_categories = set()

        # 设置 debug 日志文件
        cls.debug_log_file = config.get('debug_log_file')

    @classmethod
    def _write_debug_log(cls, msg):
        """写入调试日志到文件"""
        if cls.debug_log_file:
            try:
                with open(cls.debug_log_file, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
            except Exception:
                pass

    def __init__(self, *args, **kwargs):
        if 'config' in kwargs:
            self.config = kwargs.pop('config')
        else:
            self.config = MirrorServerHandler.config

        if 'sync_manager' in kwargs:
            self.sync_manager = kwargs.pop('sync_manager')
        else:
            self.sync_manager = MirrorServerHandler.sync_manager

        if 'monitor' in kwargs:
            self.monitor = kwargs.pop('monitor')
        else:
            self.monitor = MirrorServerHandler.monitor

        super().__init__(*args, **kwargs)

        # 初始化API路由（使用共享的 auth_manager）
        if self.config is not None:
            # 从 config 中获取共享的 auth_manager
            self.auth_manager = self.config.get('_auth_manager')
            if not self.auth_manager:
                # 如果没有，创建新的并保存到 config
                MirrorServerHandler.api_router = APIRouter(self.config)
                self.auth_manager = self.config.get('_auth_manager')
            if self.api_router is None:
                MirrorServerHandler.api_router = APIRouter(self.config)

    def _is_debug_enabled(self, category):
        """检查特定调试类别是否启用"""
        # 如果 debug_categories 为空，检查单个配置
        if not MirrorServerHandler._debug_categories:
            return self.config and self.config.get(f'debug_{category}', False)
        return category in MirrorServerHandler._debug_categories

    def _debug_log(self, category, msg, color='\033[36m'):
        """输出调试日志
        - 如果没有设置 debug_log_file，默认在终端输出
        - 如果设置了 debug_log_file，只输出到文件（错误除外）
        """
        if not self._is_debug_enabled(category):
            return

        # 格式化消息
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        formatted_msg = f"[DEBUG {timestamp}] [{category.upper()}] {msg}"

        # 写入日志文件
        self._write_debug_log(formatted_msg)

        # 是否在终端输出
        # 如果设置了 debug_log_file，不在终端输出（除非是错误）
        debug_log_file = MirrorServerHandler.debug_log_file
        if not debug_log_file:
            # 没有设置日志文件，默认在终端输出
            print(f"{color}{formatted_msg}\033[0m")

    def log_message(self, format_str, *args):
        """自定义日志输出"""
        is_verbose = self.config and self.config.get('verbose', 0) > 0

        # 调试模式输出详细日志 (debug-http)
        if self._is_debug_enabled('http'):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            msg = f"{self.address_string()} - {format_str % args}"
            self._debug_log('http', msg, '\033[36m')

        # 详细模式输出（仅当没有设置 debug_log_file 时在终端输出）
        if is_verbose and not self._is_debug_enabled('http'):
            msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} - {format_str % args}"
            print(msg)

        # 访问日志
        if self.config and self.config.get('access_log'):
            log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} - {self.command} {self.path} {self.protocol_version} {self.headers.get('User-Agent', 'Unknown')}\n"
            try:
                with open(self.config['access_log'], 'a', encoding='utf-8') as f:
                    f.write(log_entry)
            except Exception as e:
                print(f"写入访问日志失败: {e}")

    def _handle_mirror_request(self, path: str):
        """处理镜像加速源请求"""
        # 调试模式输出 (debug-http)
        if self._is_debug_enabled('http'):
            msg = f"\n=== DEBUG Mirror Request ===\n  Path: {path}"
            self._debug_log('http', msg, '\033[33m')

        # 确定镜像类型
        if path.startswith("pypi/") or path.startswith("simple/"):
            mirror_type = "pypi"
            mirror_path = path  # 保留完整路径，让 pypi.py 来处理
        elif path.startswith("npm/"):
            mirror_type = "npm"
            mirror_path = path.replace("npm/", "")
        elif path.startswith("go/"):
            mirror_type = "go"
            mirror_path = path.replace("go/", "")
        else:
            self.send_error(404, "Unknown mirror type")
            return

        # 尝试从Referer中提取镜像名称
        mirror_name = None
        if 'mirrors/' in referer:
            # 例如: http://localhost:8080/api/v2/mirrors/pypi-cn/simple/
            import re
            match = re.search(r'mirrors/([^/]+)', referer)
            if match:
                mirror_name = match.group(1)

        # 获取镜像处理器
        import sys
        handler = self._get_mirror_handler(mirror_type, mirror_name)
        if not handler:
            self.send_error(404, f"Mirror type not available: {mirror_type}")
            return

        # 处理请求
        try:
            handler.handle_request(self, mirror_path)
        except Exception as e:
            if self._is_debug_enabled('error'):
                import traceback
                tb_str = traceback.format_exc()
                msg = f"\n=== DEBUG Mirror Handler ERROR ===\n{tb_str}"
                self._debug_log('error', msg, '\033[31m')
            self.send_error(500, f"Mirror handler error: {str(e)}")

    def _get_mirror_handler(self, mirror_type: str, mirror_name: str = None):
        """获取或创建镜像处理器实例"""
        import sys

        # 如果指定了镜像名称，优先使用该镜像的配置
        cache_key = f"{mirror_type}:{mirror_name}" if mirror_name else mirror_type

        # 检查缓存
        if cache_key in MirrorServerHandler._mirror_handlers:
            return MirrorServerHandler._mirror_handlers[cache_key]

        # 检查配置中是否启用了该镜像
        mirrors_config = self.config.get('mirrors', {}) if self.config else {}
        mirror_config = None

        # 优先使用指定的镜像名称
        if mirror_name and mirror_name in mirrors_config:
            mirror_config = mirrors_config[mirror_name]
        else:
            # 否则查找匹配类型的镜像
            for name, config in mirrors_config.items():
                if config.get('type') == mirror_type and config.get('enabled'):
                    mirror_config = config
                    break

        if not mirror_config:
            return None

        # 创建处理器实例
        handler_class = get_mirror_handler(mirror_type)
        if not handler_class:
            return None

        # 配置处理器 - 使用 base_dir 作为存储目录基础
        base_dir = self.config.get('base_dir', './downloads') if self.config else './downloads'
        # 获取镜像配置的存储目录（相对路径），拼接到 base_dir 下
        storage_subdir = mirror_config.get('storage_dir', mirror_type)
        storage_dir = os.path.join(base_dir, storage_subdir)
        handler = handler_class({
            'upstream_url': mirror_config.get('url', ''),
            'storage_dir': storage_dir,
            'base_dir': base_dir
        })

        # 缓存处理器
        MirrorServerHandler._mirror_handlers[cache_key] = handler
        return handler
    
    def check_auth(self, path=None):
        """检查认证"""
        # 获取检查路径
        if path is not None:
            check_path = path
        elif hasattr(self, 'path'):
            check_path = unquote(self.path).lstrip('/')
        else:
            check_path = ''

        # 根路径直接放行
        if not check_path or check_path == '/':
            return True

        if not self.config:
            return True

        # 公开端点（不需要认证）- 文件只读操作
        public_endpoints = [
            # 登录
            'api/v2/user/login',
            # 文件只读：列表/搜索/下载/mirror/mc
            'api/v1/files',
            'api/v1/file/',
            'api/v1/search',
            'api/v1/mirror/',
            'api/v1/mc/',
            'api/v1/stats',
            'api/v1/health',
            'api/v1/cache/stats',
            # v2只读
            'api/v2/search/',
            'api/v2/health',
            'api/v2/stats/',
            'api/v2/cache/stats',
        ]

        # 检查是否是公开端点
        for endpoint in public_endpoints:
            if check_path == endpoint or check_path.startswith(endpoint + '/'):
                return True

        # 需要认证的端点 - 所有修改操作
        protected_endpoints = [
            # 用户操作
            'api/v2/user/password',  # 改密码
            'api/v2/users',
            # 文件修改操作
            'api/v1/upload',
            'api/v1/mkdir',
            'api/v1/batch',
            'api/v1/archive',
            # 同步操作
            'api/v1/sync/start',
            'api/v1/sync/stop',
            'api/v1/sync/sources',
            # v2管理
            'api/v2/admin/',
            'api/v2/config',
            'api/v2/server/',
            'api/v2/cache/clean',
            'api/v2/webhooks',
            'api/v2/sync/',
            'api/v2/file/',  # 文件删除/重命名
        ]

        # 检查是否是需要认证的端点
        is_protected = False
        for endpoint in protected_endpoints:
            if check_path.startswith(endpoint):
                is_protected = True
                break

        # 如果不是受保护端点，直接放行
        if not is_protected:
            return True

        # 只有受保护端点才需要认证检查
        auth_type = self.config.get('auth_type', 'none')
        if auth_type == 'none':
            return True
        elif auth_type == 'basic':
            return self._check_basic_auth()
        elif auth_type == 'token':
            return self._check_token_auth()
        return False

    def _check_basic_auth(self):
        """检查基本认证"""
        auth_header = self.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Basic '):
            self.send_auth_required()
            return False
            
        try:
            auth_decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
            username, password = auth_decoded.split(':', 1)
            expected_user = self.config.get('auth_user', 'admin') if self.config else 'admin'
            expected_pass = self.config.get('auth_pass', 'admin123') if self.config else 'admin123'
            
            if username == expected_user and password == expected_pass:
                return True
            else:
                self.send_auth_required()
                return False
        except Exception:
            self.send_auth_required()
            return False

    def _check_token_auth(self):
        """检查令牌认证"""
        token = None
        # 从多个来源获取 token
        headers_dict = dict(self.headers)
        if 'token' in headers_dict:
            token = headers_dict['token']
        elif 'X-API-Key' in headers_dict:
            token = headers_dict['X-API-Key']
        elif 'Authorization' in headers_dict and headers_dict['Authorization'].startswith('Bearer '):
            token = headers_dict['Authorization'][7:]
        elif '?' in self.path:
            parsed = urlparse(self.path)
            query_params = parse_qs(parsed.query)
            token = query_params.get('token', [None])[0]

        if not token:
            self.send_json_response({"error": "Invalid or missing token", "code": "UNAUTHORIZED"}, 401)
            return False

        # 首先检查是否是会话 token
        if hasattr(self, 'auth_manager') and self.auth_manager:
            session = self.auth_manager.validate_session_id(token)
            if session and session.get('valid'):
                return True

        # 检查是否是静态 token
        expected_token = self.config.get('auth_token') if self.config else None
        if token and token == expected_token:
            return True

        # 验证失败
        self.send_json_response({"error": "Invalid or missing token", "code": "UNAUTHORIZED"}, 401)
        return False

    def send_auth_required(self):
        """发送认证要求"""
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Mirror Server"')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b'{"error": "Authentication Required", "code": "UNAUTHORIZED"}')

    def do_GET(self):
        """处理GET请求"""
        import sys
        sys.stderr.flush()
        # 调试模式输出请求详情 (debug-http)
        if self._is_debug_enabled('http'):
            msg = f"\n=== DEBUG GET Request ===\n  Path: {self.path}\n  Headers: {dict(self.headers)}"
            self._debug_log('http', msg, '\033[33m')

        try:
            # 确保配置已加载
            if self.config is None:
                self.config = MirrorServerHandler.config
            if self.sync_manager is None:
                self.sync_manager = MirrorServerHandler.sync_manager
            if self.api_router is None and self.config is not None:
                MirrorServerHandler.api_router = APIRouter(self.config)

            parsed_path = urlparse(self.path)
            path = unquote(parsed_path.path).lstrip('/')
            query = parsed_path.query

            # 检查认证（公开端点不需要认证）
            if not self.check_auth(path):
                return

            # 处理 /api/docs 和 /api/ui 路径（返回静态页面）
            if path.startswith("api/docs"):
                # 提供 api/docs 目录下的静态文件
                rel_path = path[9:]  # 去掉 "api/docs"
                if rel_path and not rel_path.startswith('/'):
                    rel_path = '/' + rel_path
                self.serve_docs(rel_path)
                return
            elif path.startswith("api/ui"):
                # 提供 api/ui 目录下的静态文件
                rel_path = path[7:]  # 去掉 "api/ui"
                if rel_path and not rel_path.startswith('/'):
                    rel_path = '/' + rel_path
                self.serve_ui(rel_path)
                return
            elif path.startswith("ui/") or path == "ui":
                # /ui/ 路径已废弃，返回 404
                self.send_error(404, "UI moved to /api/ui/")
                return
            elif path.startswith("docs/") or path == "docs":
                # /docs/ 路径已废弃，返回 404
                self.send_error(404, "Docs moved to /api/docs/")
                return

            # 处理 PyPI 包文件路径 - 转发到 API 路由
            # 这些路径来自 pip 下载请求，如 /pypi/packages/hash/file.tar.gz
            if path.startswith("pypi/packages/") or path.startswith("pypi/web/") or path.startswith("pypi/simple/"):
                # 转发到 API v2 路由
                api_path = "api/v2/" + path
                self.api_router.handle_request(self, 'GET', api_path, query)
                return

            # 处理 API 路径
            if path.startswith("api/"):
                # 使用API路由处理
                self.api_router.handle_request(self, 'GET', path, query)
            # 文件夹/文件访问（/pypi/ 也是本地文件夹）
            elif path == "":
                # 根路径显示文件列表
                self.serve_path("")
            elif path.startswith("file/"):
                # 文件下载路由 /file/path/to/file -> serve_path(path/to/file)
                file_rel_path = path[5:]  # 去掉 "file/" 前缀
                self.serve_path(file_rel_path)
            else:
                self.serve_path(path)
        except Exception as e:
            if self._is_debug_enabled('error'):
                import traceback
                tb_str = traceback.format_exc()
                msg = f"\n=== DEBUG GET ERROR ===\n{tb_str}"
                self._debug_log('error', msg, '\033[31m')
            self.handle_error(500, f"服务器内部错误: {str(e)}")

    def do_POST(self):
        """处理POST请求"""
        import time
        request_id = int(time.time() * 1000000)

        # 调试模式输出请求详情 (debug-http)
        if self._is_debug_enabled('http'):
            content_length = self.headers.get('Content-Length', 0)
            msg = f"\n=== DEBUG POST Request #{request_id} ===\n  Path: {self.path}\n  Content-Length: {content_length}"
            self._debug_log('http', msg, '\033[33m')

        try:
            # 确保配置已加载
            if self.config is None:
                self.config = MirrorServerHandler.config
            if self.api_router is None and self.config is not None:
                MirrorServerHandler.api_router = APIRouter(self.config)

            path = unquote(self.path).lstrip('/')

            # 调试模式输出完整路径 (debug-http)
            if self._is_debug_enabled('http'):
                msg = f"\n=== DEBUG POST Path Check ===\n  path: '{path}'\n  starts with api/: {path.startswith('api/')}"
                self._debug_log('http', msg, '\033[33m')

            # 检查认证（公开端点不需要认证）
            if not self.check_auth(path):
                return

            if path.startswith("api/"):
                parsed_path = urlparse(self.path)
                query = parsed_path.query
                self.api_router.handle_request(self, 'POST', path, query)
            else:
                self.send_error(405)
        except Exception as e:
            if self._is_debug_enabled('error'):
                import traceback
                tb_str = traceback.format_exc()
                msg = f"\n=== DEBUG POST ERROR ===\n{tb_str}"
                self._debug_log('error', msg, '\033[31m')
            self.handle_error(500, f"服务器内部错误: {str(e)}")

    def do_OPTIONS(self):
        """处理OPTIONS请求（CORS预检）"""
        # 调试模式输出 (debug-http)
        if self._is_debug_enabled('http'):
            msg = f"\n=== DEBUG OPTIONS Request ===\n  Path: {self.path}"
            self._debug_log('http', msg, '\033[34m')

        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods',
                         'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, Authorization, Token')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    def do_DELETE(self):
        """处理DELETE请求"""
        try:
            # 确保配置已加载
            if self.config is None:
                self.config = MirrorServerHandler.config
            if self.api_router is None and self.config is not None:
                MirrorServerHandler.api_router = APIRouter(self.config)

            if not self.check_auth():
                return
            parsed_path = urlparse(self.path)
            path = unquote(parsed_path.path).lstrip('/')
            query = parsed_path.query
            if path.startswith("api/"):
                self.api_router.handle_request(self, 'DELETE', path, query)
            else:
                self.send_error(405)
        except Exception as e:
            if self._is_debug_enabled('error'):
                import traceback
                tb_str = traceback.format_exc()
                msg = f"\n=== DEBUG DELETE ERROR ===\n{tb_str}"
                self._debug_log('error', msg, '\033[31m')
            self.handle_error(500, f"服务器内部错误: {str(e)}")

    def do_PUT(self):
        """处理PUT请求"""
        try:
            # 确保配置已加载
            if self.config is None:
                self.config = MirrorServerHandler.config
            if self.api_router is None and self.config is not None:
                MirrorServerHandler.api_router = APIRouter(self.config)

            if not self.check_auth():
                return
            parsed_path = urlparse(self.path)
            path = unquote(parsed_path.path).lstrip('/')
            query = parsed_path.query
            if path.startswith("api/"):
                self.api_router.handle_request(self, 'PUT', path, query)
            else:
                self.send_error(405)
        except Exception as e:
            if self._is_debug_enabled('error'):
                import traceback
                tb_str = traceback.format_exc()
                msg = f"\n=== DEBUG PUT ERROR ===\n{tb_str}"
                self._debug_log('error', msg, '\033[31m')
            self.handle_error(500, f"服务器内部错误: {str(e)}")

    def do_HEAD(self):
        """处理HEAD请求"""
        if not self.check_auth():
            return
        path = unquote(self.path).lstrip('/')
        if self.config is None:
            self.send_error(500)
            return
        file_path = os.path.join(self.config['base_dir'], path)
        if os.path.isfile(file_path):
            self.send_file_headers(file_path)
        else:
            self.send_error(404)

    # ==================== 静态文件服务 ====================

    def serve_docs(self, rel_path):
        """提供 api/docs 目录下的静态文件"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # handlers 目录的父目录
        docs_dir = os.path.join(base_dir, 'api', 'docs')

        if not os.path.isdir(docs_dir):
            self.send_error(404, "Docs directory not found")
            return

        # 默认提供 index.html
        if not rel_path or rel_path == '/':
            rel_path = 'index.html'

        file_path = os.path.join(docs_dir, rel_path)

        # 防止目录遍历
        if not os.path.realpath(file_path).startswith(os.path.realpath(docs_dir)):
            self.send_error(403, "Access denied")
            return

        if os.path.isfile(file_path):
            self.serve_file(file_path, f'api/docs/{rel_path}')
        else:
            # 提供 docs 目录索引
            self.serve_docs_index(docs_dir)

    def serve_docs_index(self, docs_dir):
        """提供 docs 目录索引页面"""
        try:
            items = []
            for name in sorted(os.listdir(docs_dir)):
                full_path = os.path.join(docs_dir, name)
                rel_path = f'docs/{name}'
                is_dir = os.path.isdir(full_path)
                items.append({
                    "name": name,
                    "path": rel_path + ("/" if is_dir else ""),
                    "is_dir": is_dir
                })
        except OSError:
            self.send_error(403)
            return

        # 生成 HTML
        title = "HYC下载站 - 文档"
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .item {{ background: white; padding: 15px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .item a {{ text-decoration: none; color: #0066cc; font-size: 18px; }}
        .item a:hover {{ color: #003399; }}
        .item.dir a {{ color: #ff6b35; }}
        .desc {{ color: #666; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
'''
        for item in items:
            if item['is_dir']:
                html += f'''
    <div class="item dir">
        <a href="/{item['path']}">{item['name']}/</a>
        <div class="desc">目录</div>
    </div>'''
            else:
                # 根据文件类型添加描述
                desc = ""
                if item['name'].endswith('.md'):
                    desc = "Markdown 文档"
                elif item['name'].endswith('.yaml') or item['name'].endswith('.yml'):
                    desc = "OpenAPI 配置"
                elif item['name'].endswith('.json'):
                    desc = "JSON 配置"
                else:
                    desc = "文件"
                html += f'''
    <div class="item">
        <a href="/{item['path']}">{item['name']}</a>
        <div class="desc">{desc}</div>
    </div>'''

        html += '''
</body>
</html>'''

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_ui(self, rel_path):
        """提供 api/ui 目录下的静态文件"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # handlers 目录的父目录
        ui_dir = os.path.join(base_dir, 'api', 'ui')

        if not os.path.isdir(ui_dir):
            self.send_error(404, "UI directory not found")
            return

        # 默认提供 index.html
        if not rel_path or rel_path == '/':
            rel_path = 'index.html'

        file_path = os.path.join(ui_dir, rel_path)

        # 防止目录遍历
        if not os.path.realpath(file_path).startswith(os.path.realpath(ui_dir)):
            self.send_error(403, "Access denied")
            return

        if os.path.isfile(file_path):
            self.serve_file(file_path, f'api/ui/{rel_path}')
        else:
            self.send_error(404, f"File not found: {rel_path}")

    def serve_path(self, rel_path):
        """处理路径请求（文件或目录）"""
        if self.config is None:
            self.send_error(500)
            return

        file_path = os.path.join(self.config['base_dir'], rel_path)

        if not is_safe_path(self.config['base_dir'], file_path):
            self.send_error(403, "Access denied")
            return

        if os.path.isdir(file_path):
            if self.config.get('directory_listing', True):
                self.serve_directory(file_path, rel_path)
            else:
                self.send_error(403, "Directory listing is disabled")
        elif os.path.isfile(file_path):
            self.serve_file(file_path, rel_path)
        else:
            self.send_error(404)

    def serve_directory(self, dir_path, rel_dir):
        """提供目录浏览（镜像站风格）"""
        try:
            # 检查是否有索引文件
            index_files = ['index.html', 'index.htm']
            for index_file in index_files:
                index_path = os.path.join(dir_path, index_file)
                if os.path.isfile(index_path):
                    self.serve_file(index_path, os.path.join(rel_dir, index_file))
                    return

            # 获取目录内容
            items = []
            for name in os.listdir(dir_path):
                full_path = os.path.join(dir_path, name)
                rel_item_path = os.path.join(rel_dir, name).replace("\\", "/")
                is_dir = os.path.isdir(full_path)

                if self.config.get('ignore_hidden', True) and name.startswith('.'):
                    continue

                try:
                    size = "-" if is_dir else format_file_size(os.path.getsize(full_path))
                    mtime = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime("%Y-%m-%d %H:%M")

                    sha256 = ""
                    if self.config.get('show_hash') and not is_dir:
                        sha256 = get_file_hash(full_path)[:16] + "..."
                    items.append({
                        "name": name,
                        "path": rel_item_path + ("/" if is_dir else ""),
                        "size": size,
                        "modified": mtime,
                        "is_dir": is_dir,
                        "sha256": sha256
                    })
                except OSError:
                    continue

            # 排序 - Windows 文件管理器风格：文件夹在前，按名称递增排序
            sort_by = self.config.get('sort_by', 'name')
            reverse = self.config.get('sort_reverse', False)  # 默认为 False（递增）
            if sort_by == 'name':
                # 文件夹优先，然后按名称递增排序（不区分大小写）
                items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=False)
            elif sort_by == 'size':
                # 文件夹优先，然后按大小递增排序
                items.sort(key=lambda x: (not x["is_dir"], os.path.getsize(os.path.join(dir_path, x["name"])) if not x["is_dir"] else 0), reverse=False)
            elif sort_by == 'modified':
                # 文件夹优先，然后按修改时间递增排序
                items.sort(key=lambda x: (not x["is_dir"], os.path.getmtime(os.path.join(dir_path, x["name"]))), reverse=False)

        except OSError:
            self.send_error(403)
            return

        # 构建面包屑
        breadcrumbs = []
        parts = [p for p in rel_dir.split("/") if p]
        current = ""
        breadcrumbs.append({"name": "HOME", "path": "/"})
        for part in parts:
            current = os.path.join(current, part).replace("\\", "/")
            breadcrumbs.append({"name": part, "path": "/" + current + "/"})

        # 生成HTML
        title = "HYC下载站"
        html = self._generate_directory_html(title, breadcrumbs, items, rel_dir)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode('utf-8'))))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def _generate_directory_html(self, title, breadcrumbs, items, rel_dir):
        """生成目录浏览HTML"""
        if rel_dir:  # 如果不是根目录
            parts = [p for p in rel_dir.split('/') if p]  # 过滤空部分
            if len(parts) > 1:
                parent_path = '/' + '/'.join(parts[:-1]) + '/'
            elif len(parts) == 1:
                parent_path = '/'
            else:
                parent_path = '/'
        else:
            parent_path = '/'  # 根目录没有上一级
        
        # 动态计算列数
        colspan = 4 if self.config.get('show_hash') else 3
        
        html = f"""<!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f8f9fa;
                color: #212529;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                padding: 20px;
            }}
            h1 {{
                margin: 0 0 20px 0;
                padding-bottom: 10px;
                border-bottom: 2px solid #e9ecef;
                color: #495057;
            }}
            .breadcrumb {{
                margin-bottom: 20px;
                font-size: 0.9em;
                color: #6c757d;
            }}
            .breadcrumb a {{
                color: #0066cc;
                text-decoration: none;
            }}
            .breadcrumb a:hover {{
                text-decoration: underline;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.95em;
            }}
            th {{
                text-align: left;
                padding: 12px 15px;
                background: #f1f3f5;
                border-bottom: 2px solid #dee2e6;
                font-weight: 600;
            }}
            td {{
                padding: 10px 15px;
                border-bottom: 1px solid #e9ecef;
            }}
            tr:hover {{
                background: #f8f9fa;
            }}
            a {{
                text-decoration: none;
                color: #0066cc;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .size {{
                text-align: right;
                font-family: 'SFMono-Regular', Consolas, monospace;
            }}
            .modified {{
                white-space: nowrap;
            }}
            .sha256 {{
                font-family: 'SFMono-Regular', Consolas, monospace;
                font-size: 0.85em;
                color: #6c757d;
            }}
            .server-info {{
                margin-top: 20px;
                padding-top: 15px;
                border-top: 1px solid #e9ecef;
                font-size: 0.85em;
                color: #6c757d;
                text-align: center;
            }}
            @media (max-width: 768px) {{
                .container {{ padding: 10px; }}
                table {{ font-size: 0.85em; }}
                th, td {{ padding: 8px 10px; }}
                .sha256 {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{title}</h1>
            <div class="breadcrumb">
                {' / '.join(f'<a href="{crumb["path"]}">{crumb["name"]}</a>' for crumb in breadcrumbs)}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Last Modified</th>
                        <th class="size">Size</th>
                        {('<th class="sha256">SHA256</th>' if self.config.get('show_hash') else '')}
                    </tr>
                </thead>
                <tbody>"""

        # 修复：只在非根目录显示上一级目录链接
        if rel_dir:  # 如果不是根目录
            html += f'<tr class="dir"><td colspan="{colspan}"><a href="{parent_path}">../</a></td></tr>\n'

        for item in items:
            html += f'<tr class="{"dir" if item["is_dir"] else "file"}">'
            html += f'<td><a href="/{item["path"]}">{item["name"]}{" /" if item["is_dir"] else ""}</a></td>'
            html += f'<td class="modified">{item["modified"]}</td>'
            html += f'<td class="size">{item["size"]}</td>'
            if self.config.get('show_hash'):
                html += f'<td class="sha256">{item["sha256"]}</td>'
            html += '</tr>\n'

        html += f"""
                </tbody>
            </table>
            <div class="server-info">
                <p>Files: {len(items)} | {self.config.get("server_name", "Mirror Server")}</p>
            </div>
        </div>
    </body>
    </html>"""
        return html

    def send_file_headers(self, file_path):
        """发送文件头信息（用于HEAD请求）"""
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.send_error(404)
            return
        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Content-Disposition",
                         f'attachment; filename="{os.path.basename(file_path)}"')
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header(
            "Last-Modified", self.date_time_string(os.path.getmtime(file_path)))
        self.end_headers()

    def serve_file(self, file_path, rel_path):
        """提供文件下载，支持断点续传和流式传输"""
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.send_error(404)
            return

        # 获取文件信息
        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        # 获取客户端IP
        client_ip = self.client_address[0] if hasattr(self, 'client_address') else 'unknown'

        # 检查Range头部（支持断点续传）
        range_header = self.headers.get('Range')
        range_start = 0
        range_end = file_size - 1

        if range_header and self.config.get('enable_range', True):
            match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                range_start = int(match.group(1))
                range_end_str = match.group(2)
                if range_end_str:
                    range_end = int(range_end_str)

                if range_start >= file_size or range_end >= file_size or range_start > range_end:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return

        # 计算传输内容
        content_length = range_end - range_start + 1

        # 发送响应头
        if range_start == 0 and range_end == file_size - 1:
            # 完整文件下载
            self.send_response(200)
        else:
            # 部分内容（206）
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {range_start}-{range_end}/{file_size}")

        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(content_length))
        # HTML 文件直接在浏览器中显示，不强制下载
        if mime_type == 'text/html':
            self.send_header("Content-Disposition", f'inline; filename="{os.path.basename(file_path)}"')
        else:
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(file_path)}"')
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Last-Modified", self.date_time_string(os.path.getmtime(file_path)))
        self.send_header("X-Download-IP", client_ip)
        self.send_header("X-File-Size", str(file_size))
        self.end_headers()

        # 流式传输文件
        chunk_size = 64 * 1024  # 64KB chunks for better performance
        bytes_sent = 0

        try:
            with open(file_path, 'rb') as f:
                f.seek(range_start)
                remaining = content_length

                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break

                    self.wfile.write(chunk)
                    bytes_sent += len(chunk)
                    remaining -= len(chunk)

        except Exception as e:
            print(f"文件传输错误: {e}")

        # 只对真正的下载（非 HTML 页面）更新统计和记录
        if self.config.get('enable_stats', True) and mime_type != 'text/html':
            self.record_download(rel_path, file_size, client_ip)

    def record_download(self, filepath, file_size=0, client_ip='unknown'):
        """记录下载（同时更新计数和创建下载记录）"""
        if not self.config.get('enable_stats', True):
            if hasattr(self, '_debug_log') and self._is_debug_enabled('download'):
                self._debug_log('download', f"Stats disabled, skipping download record for: {filepath}")
            return

        db = self._get_db()
        if hasattr(self, '_debug_log') and self._is_debug_enabled('download'):
            self._debug_log('download', f"record_download called for: {filepath}, db: {db}")
        user_agent = self.headers.get('User-Agent', 'Unknown') if hasattr(self, 'headers') else 'Unknown'

        if db:
            try:
                # 尝试更新 FileRecord 的下载计数（通过路径查找）
                try:
                    record = db.get_file_by_path(filepath)
                    if record:
                        db.increment_download_count(record.file_id)
                except Exception as e:
                    pass  # 忽略更新计数错误

                # 创建下载记录
                try:
                    new_record = db.add_download_record(
                        file_path=filepath,
                        file_size=file_size,
                        client_ip=client_ip,
                        user_agent=user_agent,
                        success=True
                    )
                    if hasattr(self, '_debug_log') and self._is_debug_enabled('download'):
                        self._debug_log('download', f"Download record created successfully: {filepath}")
                except Exception as e:
                    if hasattr(self, '_debug_log') and self._is_debug_enabled('download'):
                        self._debug_log('download', f"Error creating download record: {e}")
            except Exception as e:
                if hasattr(self, '_debug_log') and self._is_debug_enabled('download'):
                    self._debug_log('download', f"Error recording download: {e}")

    def _serve_file_chunked(self, file_path, rel_path, chunk_size=64*1024):
        """流式分块传输文件（用于大文件）- 备用功能"""
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.send_error(404)
            return

        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Content-Disposition",
                         f'attachment; filename="{os.path.basename(file_path)}"')
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception as e:
            print(f"流式传输错误: {e}")

        # 更新统计（serve_file_chunked 只用于真正的下载）
        if self.config.get('enable_stats', True):
            self.update_download_count(rel_path)

    def send_json_response(self, data, status_code=200):
        """发送JSON响应"""
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(json_data.encode('utf-8'))))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json_data.encode('utf-8'))

    def date_time_string(self, timestamp=None):
        """重写日期时间字符串格式化"""
        if timestamp is None:
            timestamp = time.time()
        return datetime.fromtimestamp(timestamp).strftime('%a, %d %b %Y %H:%M:%S GMT')

    def handle_error(self, code, message=None):
        """自定义错误处理"""
        error_messages = {
            400: "错误的请求",
            401: "未经授权",
            403: "禁止访问",
            404: "文件未找到",
            405: "方法不允许",
            413: "文件太大",
            416: "请求范围不符合要求",
            500: "内部服务器错误"
        }

        if message is None:
            message = error_messages.get(code, "未知错误")

        error_page = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{code} {message}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
        }}
        .error-container {{
            background: white;
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
            text-align: center;
            max-width: 400px;
        }}
        .error-code {{
            font-size: 4rem;
            font-weight: bold;
            color: #ef4444;
            margin: 0;
        }}
        .error-message {{
            font-size: 1.5rem;
            color: #374151;
            margin: 1rem 0;
        }}
        .error-description {{
            color: #6b7280;
            margin-bottom: 2rem;
        }}
        .home-link {{
            display: inline-block;
            background: #3b82f6;
            color: white;
            padding: 0.75rem 1.5rem;
            border-radius: 6px;
            text-decoration: none;
            transition: background-color 0.3s;
        }}
        .home-link:hover {{
            background: #2563eb;
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <h1 class="error-code">{code}</h1>
        <h2 class="error-message">{message}</h2>
        <p class="error-description">请求的页面遇到问题，请稍后重试。</p>
        <a href="/" class="home-link">返回首页</a>
    </div>
</body>
</html>"""

        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length",
                         str(len(error_page.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(error_page.encode('utf-8'))

    def send_error(self, code, message=None):
        """发送错误响应"""
        self.handle_error(code, message)

    # 统计相关方法
    def _get_db(self):
        """获取数据库实例"""
        if hasattr(self, 'config') and self.config:
            return self.config.get('_db_instance')
        return None

    def load_stats(self):
        """加载下载统计信息（优先使用数据库，回退到JSON）"""
        db = self._get_db()
        if db:
            try:
                # 使用专门的方法获取下载统计，避免会话问题
                return db.get_download_stats(limit=10000)
            except Exception as e:
                print(f"Error loading stats from database: {e}")

        # 回退到 JSON 文件
        stats_file = self.config.get('stats_file', 'stats.json')
        try:
            if os.path.exists(stats_file):
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading stats: {e}")
        return {}

    def save_stats(self, stats):
        """保存下载统计信息（优先使用数据库，回退到JSON）"""
        db = self._get_db()
        if db:
            # 数据库模式下，stats 由数据库直接管理，不需要手动保存
            return

        # 回退到 JSON 文件
        stats_file = self.config.get('stats_file', 'stats.json')
        try:
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving stats: {e}")

    def get_download_count(self, filepath):
        """获取特定文件的下载次数"""
        db = self._get_db()
        if db:
            try:
                file_record = db.get_file_by_path(filepath)
                if file_record:
                    return file_record.download_count if hasattr(file_record, 'download_count') else 0
            except Exception as e:
                print(f"Error getting download count from database: {e}")

        stats = self.load_stats()
        return stats.get(filepath, 0)

    def get_total_downloads(self):
        """获取总下载次数"""
        db = self._get_db()
        if db:
            try:
                stats = db.get_stats()
                return stats.get('total_downloads', 0)
            except Exception as e:
                print(f"Error getting total downloads from database: {e}")

        stats = self.load_stats()
        return sum(stats.values())

    def update_download_count(self, filepath):
        """更新文件的下载计数（优先使用数据库，通过路径查找）"""
        if not self.config.get('enable_stats', True):
            return

        db = self._get_db()
        if db:
            try:
                # 通过路径查找记录，获取 file_id
                record = db.get_file_by_path(filepath)
                if record:
                    db.increment_download_count(record.file_id)
                return
            except Exception as e:
                print(f"Error updating download count in database: {e}")

        # 回退到 JSON 文件
        stats = self.load_stats()
        stats[filepath] = stats.get(filepath, 0) + 1
        self.save_stats(stats)

    # ==================== 下载历史记录 ====================

    def load_download_history(self, limit=100):
        """加载下载历史记录（优先使用数据库，回退到JSON）"""
        db = self._get_db()
        if db:
            try:
                records = db.get_download_records(limit=limit)
                history = []
                for r in records:
                    history.append({
                        'timestamp': r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                        'filepath': r.file_path if hasattr(r, 'file_path') else getattr(r, 'filepath', str(r)),
                        'file_size': r.file_size if hasattr(r, 'file_size') else 0,
                        'client_ip': r.client_ip if hasattr(r, 'client_ip') else 'unknown',
                        'user_agent': r.user_agent if hasattr(r, 'user_agent') else 'Unknown',
                        'method': 'GET'
                    })
                return history
            except Exception as e:
                print(f"Error loading download history from database: {e}")

        # 回退到 JSON 文件
        history_file = self.config.get('download_history_file', 'download_history.json')
        try:
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data[-limit:]
        except Exception as e:
            print(f"Error loading download history: {e}")
        return []

    def save_download_history(self, history):
        """保存下载历史记录（数据库模式下不需要）"""
        db = self._get_db()
        if db:
            # 数据库模式下，history 由数据库直接管理
            return

        # 回退到 JSON 文件
        history_file = self.config.get('download_history_file', 'download_history.json')
        max_history = self.config.get('max_history_count', 1000)

        try:
            # 保留最近的记录
            history = history[-max_history:]
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving download history: {e}")

    def _log_download(self, filepath, file_size=0):
        """记录下载历史（优先使用数据库）- 备用功能"""
        if not self.config.get('enable_stats', True):
            return

        client_ip = self.client_address[0] if hasattr(self, 'client_address') else 'unknown'
        user_agent = self.headers.get('User-Agent', 'Unknown')

        db = self._get_db()
        if db:
            try:
                db.add_download_record(
                    file_path=filepath,
                    file_size=file_size,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    success=True,
                    duration=0
                )
                return
            except Exception as e:
                print(f"Error logging download to database: {e}")

        # 回退到 JSON 文件
        history = self.load_download_history(1000)

        entry = {
            'timestamp': datetime.now().isoformat(),
            'filepath': filepath,
            'file_size': file_size,
            'client_ip': client_ip,
            'user_agent': user_agent,
            'method': self.command if hasattr(self, 'command') else 'GET'
        }

        history.append(entry)
        self.save_download_history(history)
