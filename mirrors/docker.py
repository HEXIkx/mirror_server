#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker镜像代理处理器
支持Docker Registry API v2
"""

import os
import json
import time
import uuid
import urllib.request
import base64
import hashlib
import hmac
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class DockerMirror:
    """Docker镜像代理"""

    def __init__(self, config: dict):
        self.config = config

        # 配置 - 使用 storage_dir（基于 base_dir）
        self.registry_url = config.get('registry_url', 'https://registry-1.docker.io')
        self.mirror_url = config.get('mirror_url', '')
        self.storage_dir = config.get('storage_dir', './downloads/docker')
        self.base_dir = config.get('base_dir', './downloads')

        # 认证（可选）
        self.username = config.get('username')
        self.password = config.get('password')

        # 确保存储目录存在
        os.makedirs(self.storage_dir, exist_ok=True)

    def handle_request(self, handler, path: str) -> bool:
        """
        处理Docker镜像请求
        路径格式: /v2/library/ubuntu/tags/list 或 /v2/library/ubuntu/manifests/latest
        """
        try:
            # 解析路径
            parts = path.strip('/').split('/')

            if len(parts) < 2 or parts[0] != 'v2':
                handler.send_error(400, "Invalid Docker API path")
                return False

            # 提取组件
            if parts[1] == 'library':
                # 官方镜像
                image = 'library/' + '/'.join(parts[2:-2]) if len(parts) > 4 else 'library/' + parts[2]
                action = parts[-2]  # tags 或 manifests
                reference = parts[-1]
            else:
                # 非官方镜像
                image = '/'.join(parts[1:-2])
                action = parts[-2]
                reference = parts[-1]

            # 根据操作类型处理
            if action == 'tags' and reference == 'list':
                return self._handle_tag_list(handler, image.rstrip('/tags'))
            elif action == 'manifests':
                return self._handle_manifest(handler, image, reference)
            elif action == 'blobs':
                return self._handle_blob(handler, image, reference)
            elif action == 'token':
                return self._handle_token(handler)
            else:
                handler.send_error(404, "Unknown action")
                return False

        except Exception as e:
            handler.send_error(500, str(e))
            return False

    def _handle_tag_list(self, handler, image: str) -> bool:
        """处理标签列表请求"""
        cache_key = f"tags:{image}"
        cached = self._get_cache(handler, cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        url = f"{self.registry_url}/v2/{image}/tags/list"

        try:
            data = self._fetch_from_upstream(url)

            # 缓存
            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(500, f"Failed to fetch tags: {str(e)}")
            return False

    def _handle_manifest(self, handler, image: str, reference: str) -> bool:
        """处理清单请求"""
        cache_key = f"manifest:{image}:{reference}"
        cached = self._get_cache(handler, cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/vnd.docker.distribution.manifest.v2+json')
            handler.send_header('Content-Length', str(len(cached)))
            handler.send_header('Docker-Content-Digest', f"sha256:{hashlib.sha256(cached).hexdigest()}")
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        url = f"{self.registry_url}/v2/{image}/manifests/{reference}"

        try:
            req = urllib.request.Request(url)
            req.add_header('Accept', 'application/vnd.docker.distribution.manifest.v2+json')

            if self.username and self.password:
                auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
                req.add_header('Authorization', f"Basic {auth}")

            with urllib.request.urlopen(req) as response:
                data = response.read()

            # 缓存
            if self.cache_enabled:
                self._set_cache(cache_key, data)

            digest = f"sha256:{hashlib.sha256(data).hexdigest()}"

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/vnd.docker.distribution.manifest.v2+json')
            handler.send_header('Content-Length', str(len(data)))
            handler.send_header('Docker-Content-Digest', digest)
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(500, f"Failed to fetch manifest: {str(e)}")
            return False

    def _handle_blob(self, handler, image: str, digest: str) -> bool:
        """处理Blob层下载"""
        # 移除 sha256: 前缀
        if digest.startswith('sha256:'):
            digest = digest[7:]

        cache_key = f"blob:{digest}"
        cached = self._get_cache(handler, cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(cached)))
            handler.send_header('Docker-Content-Digest', f"sha256:{digest}")
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        url = f"{self.registry_url}/v2/{image}/blobs/sha256:{digest}"

        try:
            req = urllib.request.Request(url)

            if self.username and self.password:
                auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
                req.add_header('Authorization', f"Basic {auth}")

            with urllib.request.urlopen(req) as response:
                data = response.read()

            # 缓存
            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(data)))
            handler.send_header('Docker-Content-Digest', f"sha256:{digest}")
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(500, f"Failed to fetch blob: {str(e)}")
            return False

    def _handle_token(self, handler) -> bool:
        """处理Token请求 - 生成真实的访问令牌"""
        # 解析认证信息
        auth_header = handler.headers.get('Authorization', '')
        username = None
        password = None

        if auth_header.startswith('Basic '):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
                username, password = decoded.split(':', 1)
            except Exception:
                pass

        # 验证凭据（如果有）
        if self.username and self.password:
            if username != self.username or password != self.password:
                handler.send_error(401, "Invalid credentials")
                return False

        # 生成唯一的访问令牌
        token_id = str(uuid.uuid4())
        issued_at = int(time.time())
        expires_in = 300  # 5分钟
        expires_at = issued_at + expires_in

        # 创建令牌信息（简化版 JWT 结构）
        token_data = {
            "iss": "hyc-mirror",
            "sub": username or "anonymous",
            "aud": self.registry_url,
            "iat": issued_at,
            "exp": expires_at,
            "access": [
                {"type": "repository", "actions": ["pull"]},
                {"type": "registry", "actions": ["catalog"]}
            ]
        }

        # 使用 HMAC-SHA256 对令牌进行简单签名
        secret_key = f"hyc-mirror-{self.registry_url}".encode()
        signature = hmac.new(
            secret_key,
            f"{token_id}:{issued_at}".encode(),
            hashlib.sha256
        ).hexdigest()[:32]

        full_token = f"{token_id}-{signature}"

        handler.send_json_response({
            "token": full_token,
            "expires_in": expires_in,
            "issued_at": issued_at
        })
        return True

    def _fetch_from_upstream(self, url: str) -> bytes:
        """从上游获取数据"""
        req = urllib.request.Request(url)

        if self.username and self.password:
            auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            req.add_header('Authorization', f"Basic {auth}")

        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()

    def _get_cache(self, handler, cache_key: str) -> Optional[bytes]:
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
            print(f"Docker缓存写入失败: {e}")

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
