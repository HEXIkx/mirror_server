#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
通用HTTP镜像代理处理器
支持Maven、Gradle、RubyGems、Cargo、NuGet、CocoaPods、CRAN、CTAN、CUDA、Pacman等基于HTTP的镜像
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional
from datetime import datetime
from html import escape


class HttpMirror:
    """通用HTTP镜像代理 - 支持多种包管理器"""

    # 不同包管理器的默认上游URL
    DEFAULT_UPSTREAM = {
        'maven': 'https://repo1.maven.org/maven2',
        'gradle': 'https://services.gradle.org/distributions',
        'gem': 'https://rubygems.org',
        'cargo': 'https://crates.io',
        'nuget': 'https://api.nuget.org/v3',
        'cocoapods': 'https://cdn.cocoapods.org',
        'cran': 'https://cran.r-project.org',
        'ctan': 'https://ctan.math.illinois.edu',
        'cuda': 'https://developer.download.nvidia.com/compute/cuda/repos',
        'pacman': 'https://mirror.archlinux.org',
    }

    def __init__(self, config: dict):
        self.config = config
        self.mirror_type = config.get('type', 'http')

        # 配置
        self.upstream_url = config.get('upstream_url', self.DEFAULT_UPSTREAM.get(self.mirror_type, 'https://mirror.example.com'))
        self.storage_dir = config.get('storage_dir', f'./downloads/{self.mirror_type}')
        self.base_dir = config.get('base_dir', './downloads')
        self.cache_enabled = config.get('cache_enabled', True)
        self.cache_ttl = config.get('cache_ttl', 3600)  # 默认1小时

        # 确保存储目录存在
        os.makedirs(self.storage_dir, exist_ok=True)

    def handle_request(self, handler, path: str) -> bool:
        """处理HTTP镜像请求"""
        try:
            # 移除前导斜杠
            path = path.strip('/')

            if not path or path == self.mirror_type:
                return self._handle_index(handler)

            # 根据镜像类型分发请求
            if self.mirror_type == 'maven':
                return self._handle_maven(handler, path)
            elif self.mirror_type == 'gradle':
                return self._handle_gradle(handler, path)
            elif self.mirror_type == 'gem':
                return self._handle_gem(handler, path)
            elif self.mirror_type == 'cargo':
                return self._handle_cargo(handler, path)
            elif self.mirror_type == 'nuget':
                return self._handle_nuget(handler, path)
            elif self.mirror_type == 'cocoapods':
                return self._handle_cocoapods(handler, path)
            elif self.mirror_type == 'cran':
                return self._handle_cran(handler, path)
            elif self.mirror_type == 'ctan':
                return self._handle_ctan(handler, path)
            elif self.mirror_type == 'cuda':
                return self._handle_cuda(handler, path)
            elif self.mirror_type == 'pacman':
                return self._handle_pacman(handler, path)
            else:
                # 默认作为普通HTTP文件处理
                return self._handle_generic(handler, path)

        except Exception as e:
            handler.send_error(500, str(e))
            return False

    def _handle_index(self, handler) -> bool:
        """返回镜像索引信息"""
        handler.send_json_response({
            'type': self.mirror_type,
            'upstream_url': self.upstream_url,
            'storage_dir': self.storage_dir,
            'cache_enabled': self.cache_enabled,
            'cache_stats': self.get_cache_stats()
        })
        return True

    # ========== Maven ==========
    def _handle_maven(self, handler, path: str) -> bool:
        """处理Maven请求: /groupId/artifactId/version/artifactId-version.jar"""
        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== Gradle ==========
    def _handle_gradle(self, handler, path: str) -> bool:
        """处理Gradle请求: /gradle-x.x-bin.zip"""
        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== RubyGems ==========
    def _handle_gem(self, handler, path: str) -> bool:
        """处理RubyGems请求"""
        # API请求: /api/v1/gems/xxx.json
        # Spec请求: /quick/Marshal.4.8/xxx-x.x.0.gemspec.rz
        # 下载请求: /gems/xxx-x.x.0.gem

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== Cargo ==========
    def _handle_cargo(self, handler, path: str) -> bool:
        """处理Cargo请求"""
        # API: /api/v1/crates
        # 下载: /crates/xxx/xxx-x.x.x.crate

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== NuGet ==========
    def _handle_nuget(self, handler, path: str) -> bool:
        """处理NuGet请求"""
        # API v3: /v3-flatcontainer/xxx.nupkg

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== CocoaPods ==========
    def _handle_cocoapods(self, handler, path: str) -> bool:
        """处理CocoaPods请求"""
        # Specs: /Specs/xxx.podspec.json
        # Pods: /Pods/xxx/xxx.pod

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== CRAN ==========
    def _handle_cran(self, handler, path: str) -> bool:
        """处理CRAN请求"""
        # /src/contrib/xxx.tar.gz

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== CTAN ==========
    def _handle_ctan(self, handler, path: str) -> bool:
        """处理CTAN请求"""
        # /macros/latex/xxx.zip

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== CUDA ==========
    def _handle_cuda(self, handler, path: str) -> bool:
        """处理CUDA请求"""
        # /xxx/xxx.deb

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== Pacman ==========
    def _handle_pacman(self, handler, path: str) -> bool:
        """处理Pacman请求"""
        # /os/x86_64/xxx.db.tar.gz
        # /os/x86_64/xxx-x.x.x-x-x86_64.pkg.tar.zst

        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== Generic HTTP ==========
    def _handle_generic(self, handler, path: str) -> bool:
        """通用的HTTP文件代理"""
        # 先检查本地
        local_path = os.path.join(self.storage_dir, path)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            return self._serve_local_file(handler, local_path)

        # 从上游获取
        url = f"{self.upstream_url}/{path}"
        return self._proxy_request(handler, url)

    # ========== 辅助方法 ==========
    def _serve_local_file(self, handler, local_path: str) -> bool:
        """服务本地文件"""
        try:
            file_size = os.path.getsize(local_path)

            # 尝试确定内容类型
            content_type = self._guess_content_type(local_path)

            handler.send_response(200)
            handler.send_header('Content-Type', content_type)
            handler.send_header('Content-Length', str(file_size))
            handler.send_header('X-Local', 'true')
            handler.end_headers()

            with open(local_path, 'rb') as f:
                handler.wfile.write(f.read())

            return True
        except Exception as e:
            handler.send_error(500, f"Error serving file: {str(e)}")
            return False

    def _proxy_request(self, handler, url: str) -> bool:
        """代理请求到上游"""
        try:
            # 检查缓存
            cache_key = self._get_cache_key(url)
            if self.cache_enabled:
                cached = self._get_cache(cache_key)
                if cached:
                    return self._serve_cached(handler, cached, url)

            # 从上游获取
            req = urllib.request.Request(url)
            req.add_header('User-Agent', f'HTTP-Mirror/1.0 ({self.mirror_type})')

            # 处理Range请求
            range_header = handler.headers.get('Range')
            if range_header:
                req.add_header('Range', range_header)

            try:
                response = urllib.request.urlopen(req, timeout=60)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    handler.send_error(404, f"File not found: {url}")
                else:
                    handler.send_error(502, f"Upstream error: {str(e)}")
                return False
            except Exception as e:
                handler.send_error(502, f"Failed to connect upstream: {str(e)}")
                return False

            # 获取响应头
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            content_length = response.headers.get('Content-Length')
            content_range = response.headers.get('Content-Range')

            # 处理部分内容响应
            if content_range:
                handler.send_response(206)
                handler.send_header('Content-Range', content_range)
            else:
                handler.send_response(200)

            handler.send_header('Content-Type', content_type)
            if content_length:
                handler.send_header('Content-Length', content_length)
            handler.send_header('X-Upstream', self.upstream_url)
            handler.end_headers()

            # 读取并转发内容，同时缓存
            data = response.read()

            if self.cache_enabled and response.status == 200:
                self._set_cache(cache_key, data, content_type)

            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(502, f"Proxy error: {str(e)}")
            return False

    def _serve_cached(self, handler, cached: dict, url: str):
        """服务缓存的文件"""
        handler.send_response(200)
        handler.send_header('Content-Type', cached.get('content_type', 'application/octet-stream'))
        handler.send_header('Content-Length', len(cached.get('data', b'')))
        handler.send_header('X-Cached', 'true')
        handler.end_headers()
        handler.wfile.write(cached.get('data', b''))
        return True

    def _get_cache_key(self, url: str) -> str:
        """生成缓存键"""
        return urllib.parse.quote(url, safe='')

    def _get_cache_path(self, cache_key: str) -> str:
        """获取缓存文件路径"""
        # 使用前两个字符作为子目录
        subdir = cache_key[:2] if len(cache_key) >= 2 else 'cache'
        return os.path.join(self.storage_dir, '.cache', subdir, cache_key)

    def _get_cache(self, cache_key: str) -> Optional[dict]:
        """获取缓存"""
        if not self.cache_enabled:
            return None

        cache_path = self._get_cache_path(cache_key)
        meta_path = cache_path + '.meta'

        if not os.path.exists(cache_path):
            return None

        # 检查是否过期
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                if time.time() > meta.get('expires', 0):
                    return None
            except Exception:
                pass

        # 读取缓存数据
        try:
            with open(cache_path, 'rb') as f:
                data = f.read()
            with open(meta_path, 'r') as f:
                meta = json.load(f)
            return {
                'data': data,
                'content_type': meta.get('content_type', 'application/octet-stream')
            }
        except Exception:
            return None

    def _set_cache(self, cache_key: str, data: bytes, content_type: str = 'application/octet-stream'):
        """设置缓存"""
        try:
            cache_path = self._get_cache_path(cache_key)
            meta_path = cache_path + '.meta'

            os.makedirs(os.path.dirname(cache_path), exist_ok=True)

            # 写入数据
            with open(cache_path, 'wb') as f:
                f.write(data)

            # 写入元数据
            meta = {
                'cached_at': time.time(),
                'expires': time.time() + self.cache_ttl,
                'size': len(data),
                'content_type': content_type,
                'url': cache_key
            }
            with open(meta_path, 'w') as f:
                json.dump(meta, f)

        except Exception as e:
            print(f"[{self.mirror_type}] Cache write failed: {e}")

    def _guess_content_type(self, path: str) -> str:
        """根据文件扩展名猜测内容类型"""
        ext = os.path.splitext(path)[1].lower()

        content_types = {
            '.jar': 'application/java-archive',
            '.war': 'application/java-archive',
            '.ear': 'application/java-archive',
            '.pom': 'application/xml',
            '.xml': 'application/xml',
            '.json': 'application/json',
            '.gem': 'application/octet-stream',
            '.crate': 'application/octet-stream',
            '.nupkg': 'application/zip',
            '.tar.gz': 'application/gzip',
            '.tgz': 'application/gzip',
            '.zip': 'application/zip',
            '.deb': 'application/deb',
            '.rpm': 'application/x-rpm',
            '.pkg.tar.zst': 'application/zstd',
            '.podspec': 'text/plain',
            '.tar': 'application/x-tar',
            '.pdf': 'application/pdf',
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
        }

        return content_types.get(ext, 'application/octet-stream')

    def get_cache_stats(self) -> dict:
        """获取缓存统计"""
        cache_dir = os.path.join(self.storage_dir, '.cache')
        if not os.path.exists(cache_dir):
            return {'files': 0, 'size': 0, 'size_formatted': '0 B'}

        total_size = 0
        file_count = 0

        try:
            for root, dirs, files in os.walk(cache_dir):
                for f in files:
                    if not f.endswith('.meta'):
                        file_count += 1
                        total_size += os.path.getsize(os.path.join(root, f))
        except Exception:
            pass

        return {
            'files': file_count,
            'size': total_size,
            'size_formatted': self._format_size(total_size)
        }

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.2f} {units[i]}"
