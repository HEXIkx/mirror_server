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
import cgi
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse, parse_qs

from core.utils import format_file_size, get_file_hash, sanitize_filename, is_safe_path
from api.router import APIRouter


class MirrorServerHandler(BaseHTTPRequestHandler):
    """镜像服务器请求处理器"""
    
    config = None
    sync_manager = None
    protocol_version = 'HTTP/1.1'
    api_router = None

    def __init__(self, *args, **kwargs):
        if 'config' in kwargs:
            self.config = kwargs.pop('config')
        else:
            self.config = MirrorServerHandler.config

        if 'sync_manager' in kwargs:
            self.sync_manager = kwargs.pop('sync_manager')
        else:
            self.sync_manager = MirrorServerHandler.sync_manager

        super().__init__(*args, **kwargs)

        # 初始化API路由
        if self.api_router is None and self.config is not None:
            MirrorServerHandler.api_router = APIRouter(self.config)

    def log_message(self, format_str, *args):
        """自定义日志输出"""
        if self.config and self.config.get('verbose', 0) > 0:
            msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} - {format_str % args}"
            print(msg)

        if self.config and self.config.get('access_log'):
            log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} - {self.command} {self.path} {self.protocol_version} {self.headers.get('User-Agent', 'Unknown')}\n"
            try:
                with open(self.config['access_log'], 'a', encoding='utf-8') as f:
                    f.write(log_entry)
            except Exception as e:
                print(f"写入访问日志失败: {e}")
    
    def check_auth(self):
        """检查认证"""
        if not self.config:
            return True
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
        if 'token' in dict(self.headers):
            token = self.headers['token']
        elif 'Authorization' in self.headers and self.headers['Authorization'].startswith('Bearer '):
            token = self.headers['Authorization'][7:]
        elif '?' in self.path:
            parsed = urlparse(self.path)
            query_params = parse_qs(parsed.query)
            token = query_params.get('token', [None])[0]

        expected_token = self.config.get('auth_token') if self.config else None
        if token and token == expected_token:
            return True
        else:
            self.send_json_response({"error": "Invalid or missing token"}, 401)
            return False

    def send_auth_required(self):
        """发送认证要求"""
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Mirror Server"')
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<h1>401 Unauthorized</h1>')

    def do_GET(self):
        """处理GET请求"""
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

            if not self.check_auth():
                return

            if path.startswith("api/"):
                # 使用API路由处理
                self.api_router.handle_request(self, 'GET', path, query)
            else:
                self.serve_path(path)
        except Exception as e:
            self.handle_error(500, f"服务器内部错误: {str(e)}")

    def do_POST(self):
        """处理POST请求"""
        try:
            # 确保配置已加载
            if self.config is None:
                self.config = MirrorServerHandler.config
            if self.api_router is None and self.config is not None:
                MirrorServerHandler.api_router = APIRouter(self.config)

            if not self.check_auth():
                return

            path = unquote(self.path).lstrip('/')
            if path.startswith("api/"):
                self.api_router.handle_request(self, 'POST', path, '')
            else:
                self.send_error(405)
        except Exception as e:
            self.handle_error(500, f"服务器内部错误: {str(e)}")

    def do_OPTIONS(self):
        """处理OPTIONS请求（CORS预检）"""
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
            path = unquote(self.path).lstrip('/')
            if path.startswith("api/"):
                self.api_router.handle_request(self, 'DELETE', path, '')
            else:
                self.send_error(405)
        except Exception as e:
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
            path = unquote(self.path).lstrip('/')
            if path.startswith("api/"):
                self.api_router.handle_request(self, 'PUT', path, '')
            else:
                self.send_error(405)
        except Exception as e:
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

            # 排序
            sort_by = self.config.get('sort_by', 'name')
            reverse = self.config.get('sort_reverse', False)
            if sort_by == 'name':
                items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=reverse)
            elif sort_by == 'size':
                items.sort(key=lambda x: (not x["is_dir"], os.path.getsize(os.path.join(dir_path, x["name"])) if not x["is_dir"] else 0), reverse=reverse)
            elif sort_by == 'modified':
                items.sort(key=lambda x: (not x["is_dir"], os.path.getmtime(os.path.join(dir_path, x["name"]))), reverse=reverse)

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
        """提供文件下载，支持断点续传"""
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.send_error(404)
            return

        # 更新下载统计
        if self.config.get('enable_stats', True):
            self.update_download_count(rel_path)

        # 获取文件信息
        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        # 检查Range头部（支持断点续传）
        range_header = self.headers.get('Range')
        if range_header and self.config.get('enable_range', True):
            match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                start = int(match.group(1))
                end = match.group(2)
                if end:
                    end = int(end)
                else:
                    end = file_size - 1

                if start >= file_size or end >= file_size or start > end:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return

                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(length))
                self.send_header(
                    "Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(file_path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    chunk_size = 8192
                    while remaining > 0:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                return

        # 普通文件下载
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

        with open(file_path, 'rb') as f:
            self.wfile.write(f.read())

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
    def load_stats(self):
        """加载下载统计信息"""
        stats_file = self.config.get('stats_file', 'stats.json')
        try:
            if os.path.exists(stats_file):
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading stats: {e}")
        return {}

    def save_stats(self, stats):
        """保存下载统计信息"""
        stats_file = self.config.get('stats_file', 'stats.json')
        try:
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving stats: {e}")

    def get_download_count(self, filepath):
        """获取特定文件的下载次数"""
        stats = self.load_stats()
        return stats.get(filepath, 0)

    def get_total_downloads(self):
        """获取总下载次数"""
        stats = self.load_stats()
        return sum(stats.values())

    def update_download_count(self, filepath):
        """更新文件的下载计数"""
        if not self.config.get('enable_stats', True):
            return

        stats = self.load_stats()
        stats[filepath] = stats.get(filepath, 0) + 1
        self.save_stats(stats)
