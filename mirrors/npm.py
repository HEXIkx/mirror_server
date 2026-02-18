#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
npm镜像代理处理器
支持Node.js包管理器
"""

import os
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Optional
from datetime import datetime


class NpmMirror:
    """npm镜像代理"""

    def __init__(self, config: dict):
        self.config = config

        # 配置 - 使用 storage_dir（基于 base_dir）
        self.upstream_url = config.get('upstream_url', 'https://registry.npmjs.org')
        self.storage_dir = config.get('storage_dir', './downloads/npm')
        self.base_dir = config.get('base_dir', './downloads')

        # 确保存储目录存在
        os.makedirs(self.storage_dir, exist_ok=True)

    def handle_request(self, handler, path: str) -> bool:
        """
        处理npm请求
        路径格式: /lodash 或 /-/package/lodash/dist
        """
        try:
            parts = path.strip('/').split('/')

            if not parts:
                return self._handle_index(handler)

            if parts[0] == '-':
                # Scoped package 或其他特殊请求
                if len(parts) >= 4 and parts[1] == 'package':
                    return self._handleScopedPackage(handler, parts[2], parts[3] if len(parts) > 3 else None)
                elif len(parts) >= 3 and parts[1] == 'package':
                    return self._handle_package(handler, parts[2], None)
                else:
                    handler.send_error(400, "Invalid npm API path")
                    return False

            elif parts[0] == '@':
                # Scoped package
                if len(parts) >= 2:
                    scope = parts[0]
                    package = '/'.join(parts[1:])
                    return self._handle_scoped_package(handler, scope, package)
                else:
                    handler.send_error(400, "Invalid scoped package")
                    return False

            elif parts[0] == '-/':
                # npm特殊路径
                return self._handle_special(handler, '/'.join(parts))

            elif len(parts) == 1:
                # 单个包名
                return self._handle_package(handler, parts[0], None)

            else:
                # 其他请求
                return self._handle_package(handler, parts[0], parts[1] if len(parts) > 1 else None)

        except Exception as e:
            handler.send_error(500, str(e))
            return False

    def _handle_index(self, handler) -> bool:
        """处理索引请求"""
        handler.send_json_response({
            'registry_url': self.upstream_url,
            'cache_stats': self.get_cache_stats()
        })
        return True

    def _handle_package(self, handler, package: str, version: str = None) -> bool:
        """处理包元数据请求"""
        cache_key = f"package:{package}:{version or 'latest'}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        if version:
            url = f"{self.upstream_url}/{package}/{version}"
        else:
            url = f"{self.upstream_url}/{package}/latest"

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
            handler.send_error(404, f"Package not found: {package}")
            return False

    def _handle_scoped_package(self, handler, scope: str, package: str) -> bool:
        """处理scoped包"""
        full_name = f"{scope}/{package}"
        return self._handle_package(handler, full_name, None)

    def _handleScopedPackage(self, handler, scope: str, package: str) -> bool:
        """处理特殊路径的scoped包"""
        full_name = f"{scope}/{package}"
        return self._handle_package(handler, full_name, None)

    def _handle_special(self, handler, path: str) -> bool:
        """处理特殊npm路径"""
        # 简化实现：转发到上游
        url = f"{self.upstream_url}/{path}"

        try:
            data = self._fetch(url)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(502, f"Failed to fetch: {str(e)}")
            return False

    def _handle_tarball(self, handler, package: str, filename: str) -> bool:
        """处理tarball下载"""
        cache_key = f"tarball:{package}:{filename}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        url = f"{self.upstream_url}/{package}/-/{filename}"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(502, f"Failed to fetch tarball: {str(e)}")
            return False

    def _fetch(self, url: str) -> Optional[bytes]:
        """从URL获取数据"""
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'npm-Mirror/1.0')
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req, timeout=30) as response:
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
            print(f"npm缓存写入失败: {e}")

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
