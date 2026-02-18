#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Go模块代理处理器
支持Go模块代理协议
"""

import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional
from datetime import datetime


class GoProxy:
    """Go模块代理"""

    def __init__(self, config: dict):
        self.config = config

        # 配置 - 使用 storage_dir（基于 base_dir）
        self.upstream_url = config.get('upstream_url', 'https://proxy.golang.org')
        self.storage_dir = config.get('storage_dir', './downloads/go')
        self.base_dir = config.get('base_dir', './downloads')
        self.mode = config.get('mode', 'proxy')  # proxy | direct

        # 确保存储目录存在
        os.makedirs(self.storage_dir, exist_ok=True)

    def handle_request(self, handler, path: str) -> bool:
        """
        处理Go模块请求
        路径格式: /golang.org/x/net/@v/list
                  /golang.org/x/net/@v/v1.0.0.info
                  /golang.org/x/net/@v/v1.0.0.zip
                  /golang.org/x/net/@latest
        """
        try:
            parts = path.strip('/').split('/')

            if len(parts) < 2:
                return self._handle_index(handler)

            # 解析模块路径和操作
            module_parts = []

            for i, part in enumerate(parts):
                if part.startswith('@'):
                    # 找到操作部分
                    module_path = '/'.join(parts[:i])
                    action = parts[i:]
                    break
            else:
                # 没有找到操作符
                module_path = '/'.join(parts)
                action = []

            if not action:
                handler.send_error(400, "Invalid Go module path")
                return False

            action_type = action[0]

            if action_type == '@v':
                # 版本相关操作
                if len(action) >= 3:
                    version = action[2]
                    return self._handle_version(handler, module_path, version)
                elif len(action) == 2:
                    # /@v/list
                    return self._handle_version_list(handler, module_path)

            elif action_type == '@latest':
                # /@latest
                return self._handle_latest(handler, module_path)

            elif action_type == '@all':
                # /@all
                return self._handle_all(handler, module_path)

            elif action_type == '@list':
                # /@list
                return self._handle_module_list(handler, module_path)

            else:
                handler.send_error(400, f"Unknown action: {action_type}")
                return False

        except Exception as e:
            handler.send_error(500, str(e))
            return False

    def _handle_index(self, handler) -> bool:
        """处理索引请求"""
        handler.send_json_response({
            'proxy_url': self.upstream_url,
            'mode': self.mode,
            'cache_stats': self.get_cache_stats()
        })
        return True

    def _handle_version_list(self, handler, module: str) -> bool:
        """处理版本列表请求 /@v/list"""
        cache_key = f"vlist:{module}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        url = f"{self.upstream_url}/{module}/@v/list"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except urllib.error.HTTPError as e:
            if e.code == 404:
                handler.send_error(404, f"Module not found: {module}")
            else:
                handler.send_error(502, f"Failed to fetch: {str(e)}")
            return False

    def _handle_version_info(self, handler, module: str, version: str) -> bool:
        """处理版本信息请求 /@v/version.info"""
        cache_key = f"info:{module}:{version}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        url = f"{self.upstream_url}/{module}/@v/{version}.info"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except urllib.error.HTTPError as e:
            handler.send_error(502, f"Failed to fetch info: {str(e)}")
            return False

    def _handle_version(self, handler, module: str, suffix: str) -> bool:
        """处理版本相关请求"""
        if suffix.endswith('.info'):
            version = suffix[:-5]
            return self._handle_version_info(handler, module, version)

        elif suffix.endswith('.zip'):
            version = suffix[:-4]
            return self._handle_zip(handler, module, version)

        elif suffix.endswith('.mod'):
            version = suffix[:-4]
            return self._handle_mod(handler, module, version)

        elif suffix.endswith('.sum'):
            version = suffix[:-4]
            return self._handle_sum(handler, module, version)

        else:
            handler.send_error(400, f"Unknown suffix: {suffix}")
            return False

    def _handle_latest(self, handler, module: str) -> bool:
        """处理最新版本请求 /@latest"""
        cache_key = f"latest:{module}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        url = f"{self.upstream_url}/{module}/@latest"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except urllib.error.HTTPError as e:
            handler.send_error(502, f"Failed to fetch latest: {str(e)}")
            return False

    def _handle_zip(self, handler, module: str, version: str) -> bool:
        """处理zip下载"""
        cache_key = f"zip:{module}:{version}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/zip')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        url = f"{self.upstream_url}/{module}/@v/{version}.zip"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/zip')
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except urllib.error.HTTPError as e:
            handler.send_error(502, f"Failed to fetch zip: {str(e)}")
            return False

    def _handle_mod(self, handler, module: str, version: str) -> bool:
        """处理mod文件"""
        cache_key = f"mod:{module}:{version}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        url = f"{self.upstream_url}/{module}/@v/{version}.mod"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except urllib.error.HTTPError as e:
            handler.send_error(502, f"Failed to fetch mod: {str(e)}")
            return False

    def _handle_sum(self, handler, module: str, version: str) -> bool:
        """处理sum文件"""
        cache_key = f"sum:{module}:{version}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        url = f"{self.upstream_url}/{module}/@v/{version}.sum"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except urllib.error.HTTPError as e:
            if e.code == 404:
                # 没有sum文件时返回空
                handler.send_response(200)
                handler.send_header('Content-Type', 'text/plain; charset=utf-8')
                handler.end_headers()
                handler.wfile.write(b'')
            else:
                handler.send_error(502, f"Failed to fetch sum: {str(e)}")
            return False

    def _handle_all(self, handler, module: str) -> bool:
        """处理/@all请求 - 返回模块及其所有依赖的zip包"""
        cache_key = f"all:{module}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/zip')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取所有依赖的zip
        url = f"{self.upstream_url}/{module}/@all.zip"

        try:
            data = self._fetch(url)

            if not data:
                handler.send_error(404, f"Module not found: {module}")
                return False

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/zip')
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except urllib.error.HTTPError as e:
            if e.code == 404:
                handler.send_error(404, f"Module not found: {module}")
            else:
                handler.send_error(502, f"Failed to fetch @all: {str(e)}")
            return False

    def _handle_module_list(self, handler, module: str) -> bool:
        """处理/@list请求 - 返回模块及其依赖的路径列表"""
        cache_key = f"list:{module}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 首先获取模块的 go.mod 文件以提取依赖
        mod_url = f"{self.upstream_url}/{module}/@v/{module}.mod"

        try:
            mod_data = self._fetch(mod_url)
            if not mod_data:
                handler.send_error(404, f"Module not found: {module}")
                return False

            # 解析go.mod获取依赖
            modules = [module]
            mod_content = mod_data.decode('utf-8', errors='replace')

            # 提取require语句中的依赖
            import re
            require_pattern = r'require\s+\(([^\)]+)\)'
            inline_require_pattern = r'require\s+([^\s]+)\s+([^\s]+)'

            # 处理多行require
            matches = re.findall(require_pattern, mod_content, re.DOTALL)
            for match in matches:
                for line in match.strip().split('\n'):
                    line = line.strip()
                    if line and not line.startswith('//'):
                        parts = line.split()
                        if parts:
                            modules.append(parts[0])

            # 处理单行require
            matches = re.findall(inline_require_pattern, mod_content)
            for match in matches:
                if match[0] not in modules:
                    modules.append(match[0])

            # 生成列表输出
            list_output = '\n'.join(sorted(set(modules))) + '\n'

            if self.cache_enabled:
                self._set_cache(cache_key, list_output.encode())

            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(list_output.encode())
            return True

        except urllib.error.HTTPError as e:
            if e.code == 404:
                handler.send_error(404, f"Module not found: {module}")
            else:
                handler.send_error(502, f"Failed to fetch @list: {str(e)}")
            return False

    def _fetch(self, url: str) -> Optional[bytes]:
        """从URL获取数据"""
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Go-Mirror/1.0')

            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read()

        except Exception:
            return None

    def _get_cache(self, cache_key: str) -> Optional[bytes]:
        """获取缓存"""
        if not self.cache_enabled:
            return None

        cache_path = self._get_cache_path(cache_key)
        meta_path = cache_path + '.meta'

        if not os.path.exists(cache_path):
            return None

        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                if time.time() > meta.get('expires', 0):
                    return None
            except Exception:
                pass

        try:
            with open(cache_path, 'rb') as f:
                return f.read()
        except Exception:
            return None

    def _set_cache(self, cache_key: str, data: bytes):
        """设置缓存"""
        cache_path = self._get_cache_path(cache_key)
        meta_path = cache_path + '.meta'

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        try:
            with open(cache_path, 'wb') as f:
                f.write(data)

            meta = {
                'cached_at': time.time(),
                'expires': time.time() + self.cache_ttl,
                'size': len(data)
            }

            with open(meta_path, 'w') as f:
                json.dump(meta, f)

        except Exception as e:
            print(f"Go缓存写入失败: {e}")

    def _get_cache_path(self, cache_key: str) -> str:
        """获取缓存路径"""
        subdir = cache_key[:2]
        return os.path.join(self.storage_dir, subdir, cache_key)

    def get_cache_stats(self) -> dict:
        """获取缓存统计"""
        if not os.path.exists(self.storage_dir):
            return {'files': 0, 'size': 0}

        total_size = 0
        file_count = 0

        for root, dirs, files in os.walk(self.storage_dir):
            for f in files:
                if not f.endswith('.meta'):
                    file_count += 1
                    total_size += os.path.getsize(os.path.join(root, f))

        return {
            'files': file_count,
            'size': total_size,
            'size_formatted': self._format_size(total_size)
        }

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.2f} {units[i]}"
