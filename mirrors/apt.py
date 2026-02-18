#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
APT镜像代理处理器
支持Debian/Ubuntu软件源
"""

import os
import json
import time
import gzip
import re
import urllib.request
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class APTMirror:
    """APT镜像代理"""

    def __init__(self, config: dict):
        self.config = config

        # 配置 - 使用 storage_dir（基于 base_dir）
        self.mirrors = config.get('mirrors', [
            'http://archive.ubuntu.com/ubuntu',
            'http://security.ubuntu.com/ubuntu'
        ])
        self.storage_dir = config.get('storage_dir', './downloads/apt')
        self.base_dir = config.get('base_dir', './downloads')
        self.default_suite = config.get('suite', 'jammy')
        self.default_components = config.get('components', ['main', 'restricted', 'universe', 'multiverse'])
        self.default_arch = config.get('arch', 'amd64')

        # 确保存储目录存在
        os.makedirs(self.storage_dir, exist_ok=True)

    def handle_request(self, handler, path: str) -> bool:
        """
        处理APT请求
        路径格式: /ubuntu/dists/jammy/main/binary-amd64/Packages.gz
        """
        try:
            # 解析路径
            parts = path.strip('/').split('/')

            if len(parts) < 5:
                # 返回镜像列表或帮助信息
                return self._handle_index(handler)

            # 提取组件
            distro = parts[0]  # ubuntu, debian 等
            dist_type = parts[1]  # dists
            suite = parts[2]  # jammy, focal 等
            component = parts[3]  # main, updates 等
            rest = '/'.join(parts[4:])

            # 确定请求类型
            if rest.endswith('Packages.gz'):
                return self._handle_packages(handler, distro, suite, component, rest)
            elif rest.endswith('Packages'):
                return self._handle_packages_uncompressed(handler, distro, suite, component, rest)
            elif rest.endswith('Release'):
                return self._handle_release(handler, distro, suite, component, rest)
            elif rest.endswith('Release.gpg'):
                return self._handle_release_gpg(handler, distro, suite, component, rest)
            elif rest.endswith('InRelease'):
                return self._handle_inrelease(handler, distro, suite, component, rest)
            else:
                # 其他文件（源码包等）
                return self._handle_file(handler, distro, suite, rest)

        except Exception as e:
            handler.send_error(500, str(e))
            return False

    def _handle_index(self, handler) -> bool:
        """处理索引请求"""
        handler.send_json_response({
            'mirrors': self.mirrors,
            'default_suite': self.default_suite,
            'default_components': self.default_components,
            'cache_stats': self.get_cache_stats()
        })
        return True

    def _handle_packages(self, handler, distro: str, suite: str, component: str, path: str) -> bool:
        """处理Packages.gz请求"""
        cache_key = f"packages:{distro}:{suite}:{component}:{self.default_arch}"

        # 检查架构
        if 'binary-' in path:
            arch = path.split('binary-')[1].split('/')[0]
        else:
            arch = self.default_arch

        cache_key = f"packages:{distro}:{suite}:{component}:{arch}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/x-gzip')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        for mirror in self.mirrors:
            url = f"{mirror}/{path}"

            try:
                data = self._fetch(url)
                if data:
                    # 缓存
                    if self.cache_enabled:
                        self._set_cache(cache_key, data)

                    handler.send_response(200)
                    handler.send_header('Content-Type', 'application/x-gzip')
                    handler.send_header('Content-Length', str(len(data)))
                    handler.end_headers()
                    handler.wfile.write(data)
                    return True

            except Exception as e:
                continue

        handler.send_error(502, "Failed to fetch from all mirrors")
        return False

    def _handle_packages_uncompressed(self, handler, distro: str, suite: str, component: str, path: str) -> bool:
        """处理未压缩的Packages文件"""
        # 先获取gz版本
        gz_path = path + '.gz'

        for mirror in self.mirrors:
            url = f"{mirror}/{gz_path}"
            try:
                data = self._fetch(url)
                if data:
                    # 解压
                    packages_data = gzip.decompress(data)

                    handler.send_response(200)
                    handler.send_header('Content-Type', 'text/plain')
                    handler.send_header('Content-Length', str(len(packages_data)))
                    handler.end_headers()
                    handler.wfile.write(packages_data)
                    return True

            except Exception:
                continue

        handler.send_error(502, "Failed to fetch packages")
        return False

    def _handle_release(self, handler, distro: str, suite: str, component: str, path: str) -> bool:
        """处理Release文件"""
        cache_key = f"release:{distro}:{suite}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 获取Release文件
        release_path = f"/{distro}/dists/{suite}/Release"

        for mirror in self.mirrors:
            url = mirror + release_path
            try:
                data = self._fetch(url)
                if data:
                    if self.cache_enabled:
                        self._set_cache(cache_key, data)

                    handler.send_response(200)
                    handler.send_header('Content-Type', 'text/plain')
                    handler.send_header('Content-Length', str(len(data)))
                    handler.end_headers()
                    handler.wfile.write(data)
                    return True

            except Exception:
                continue

        handler.send_error(502, "Failed to fetch Release")
        return False

    def _handle_release_gpg(self, handler, distro: str, suite: str, component: str, path: str) -> bool:
        """处理Release.gpg文件"""
        cache_key = f"release_gpg:{distro}:{suite}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/pgp-signature')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 尝试获取
        gpg_path = f"/{distro}/dists/{suite}/Release.gpg"

        for mirror in self.mirrors:
            url = mirror + gpg_path
            try:
                data = self._fetch(url)
                if data:
                    if self.cache_enabled:
                        self._set_cache(cache_key, data)

                    handler.send_response(200)
                    handler.send_header('Content-Type', 'application/pgp-signature')
                    handler.end_headers()
                    handler.wfile.write(data)
                    return True

            except Exception:
                continue

        handler.send_error(404, "Release.gpg not found")
        return False

    def _handle_inrelease(self, handler, distro: str, suite: str, component: str, path: str) -> bool:
        """处理InRelease文件 - 获取或生成签名后的Release信息"""
        cache_key = f"inrelease:{distro}:{suite}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 尝试从上游获取 InRelease
        inrelease_path = f"/{distro}/dists/{suite}/InRelease"

        for mirror in self.mirrors:
            url = mirror + inrelease_path
            try:
                data = self._fetch(url)
                if data:
                    if self.cache_enabled:
                        self._set_cache(cache_key, data)

                    handler.send_response(200)
                    handler.send_header('Content-Type', 'text/plain')
                    handler.send_header('Content-Length', str(len(data)))
                    handler.end_headers()
                    handler.wfile.write(data)
                    return True
            except Exception:
                continue

        # 如果没有 InRelease，尝试生成一个（基于 Release + 方括号注释）
        # 注意：这不是有效的签名，但可以用于不验证签名的客户端
        release_cache_key = f"release:{distro}:{suite}"
        release_data = self._get_cache(release_cache_key)

        if not release_data:
            # 尝试获取 Release
            release_path = f"/{distro}/dists/{suite}/Release"
            for mirror in self.mirrors:
                url = mirror + release_path
                try:
                    release_data = self._fetch(url)
                    if release_data:
                        break
                except Exception:
                    continue

        if release_data:
            # 添加注释说明这是未签名的 Release
            comment = f"# Note: This is a synthesized InRelease (original InRelease not available)\n"
            inrelease_data = comment + release_data.decode('utf-8', errors='replace')

            if self.cache_enabled:
                self._set_cache(cache_key, inrelease_data.encode())

            handler.send_response(200)
            handler.send_header('Content-Type', 'text/plain')
            handler.send_header('Content-Length', str(len(inrelease_data)))
            handler.end_headers()
            handler.wfile.write(inrelease_data.encode())
            return True

        handler.send_error(502, "Failed to fetch InRelease")
        return False

    def _handle_file(self, handler, distro: str, suite: str, path: str) -> bool:
        """处理普通文件请求（如源码包）"""
        cache_key = f"file:{distro}:{path.replace('/', ':')}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        for mirror in self.mirrors:
            url = f"{mirror}/{path}"
            try:
                data = self._fetch(url)
                if data:
                    if self.cache_enabled:
                        self._set_cache(cache_key, data)

                    handler.send_response(200)
                    handler.send_header('Content-Type', 'application/octet-stream')
                    handler.send_header('Content-Length', str(len(data)))
                    handler.end_headers()
                    handler.wfile.write(data)
                    return True

            except Exception:
                continue

        handler.send_error(404, "File not found")
        return False

    def _fetch(self, url: str) -> Optional[bytes]:
        """从URL获取数据"""
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'APT-Mirror/1.0')

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

        # 检查过期
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
            print(f"APT缓存写入失败: {e}")

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
