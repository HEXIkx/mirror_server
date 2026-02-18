#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YUM/DNF镜像代理处理器
支持RHEL/CentOS/Rocky/AlmaLinux软件源
"""

import os
import json
import time
import gzip
import xml.etree.ElementTree as ET
import urllib.request
from typing import Dict, List, Optional
from datetime import datetime


class YUMMirror:
    """YUM/DNF镜像代理"""

    def __init__(self, config: dict):
        self.config = config

        # 配置 - 使用 storage_dir（基于 base_dir）
        self.base_url = config.get('base_url', 'http://mirror.centos.org/centos')
        self.storage_dir = config.get('storage_dir', './downloads/yum')
        self.base_dir = config.get('base_dir', './downloads')
        self.repo_id = config.get('repo_id', 'baseos')
        self.arch = config.get('arch', 'x86_64')

        # 确保存储目录存在
        os.makedirs(self.storage_dir, exist_ok=True)

    def handle_request(self, handler, path: str) -> bool:
        """
        处理YUM请求
        路径格式: /centos/7/updates/x86_64/repodata/repomd.xml
        """
        try:
            parts = path.strip('/').split('/')

            if len(parts) < 3:
                return self._handle_index(handler)

            distro = parts[0]  # centos, rocky, alma
            version = parts[1]  # 7, 8, 9
            repo = parts[2]  # baseos, appstream, updates
            rest = '/'.join(parts[3:])

            # 确定文件类型
            if 'repomd.xml' in rest:
                return self._handle_repomd(handler, distro, version, repo)
            elif 'primary.xml.gz' in rest:
                return self._handle_primary(handler, distro, version, repo, 'primary')
            elif 'filelists.xml.gz' in rest:
                return self._handle_filelists(handler, distro, version, repo, 'filelists')
            elif 'other.xml.gz' in rest:
                return self._handle_other(handler, distro, version, repo, 'other')
            else:
                return self._handle_repo_file(handler, distro, version, repo, rest)

        except Exception as e:
            handler.send_error(500, str(e))
            return False

    def _handle_index(self, handler) -> bool:
        """处理索引请求"""
        handler.send_json_response({
            'base_url': self.base_url,
            'repo_id': self.repo_id,
            'arch': self.arch,
            'cache_stats': self.get_cache_stats()
        })
        return True

    def _handle_repomd(self, handler, distro: str, version: str, repo: str) -> bool:
        """处理repomd.xml请求"""
        cache_key = f"repomd:{distro}:{version}:{repo}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/xml')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取
        url = f"{self.base_url}/{version}/{repo}/{self.arch}/repodata/repomd.xml"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/xml')
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(502, f"Failed to fetch repomd: {str(e)}")
            return False

    def _handle_primary(self, handler, distro: str, version: str, repo: str, db_type: str) -> bool:
        """处理primary.xml.gz"""
        cache_key = f"primary:{distro}:{version}:{repo}:{self.arch}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/x-gzip')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 先获取repomd.xml找到对应的数据库文件
        repomd_url = f"{self.base_url}/{version}/{repo}/{self.arch}/repodata/repomd.xml"

        try:
            repomd_data = self._fetch(repomd_url)

            # 解析repomd.xml找到primary文件
            root = ET.fromstring(repomd_data)
            ns = {'repomd': 'http://linux.duke.edu/metadata/repo'}

            data_location = None
            for elem in root.findall('.//repomd:data', ns):
                if elem.get('type') == 'primary':
                    data_location = elem.find('repomd:location', ns).get('href')
                    break

            if data_location:
                db_url = f"{self.base_url}/{version}/{repo}/{self.arch}/repodata/{data_location}"
                data = self._fetch(db_url)

                if self.cache_enabled:
                    self._set_cache(cache_key, data)

                handler.send_response(200)
                handler.send_header('Content-Type', 'application/x-gzip')
                handler.send_header('Content-Length', str(len(data)))
                handler.end_headers()
                handler.wfile.write(data)
                return True

        except Exception as e:
            pass

        handler.send_error(502, "Failed to fetch primary database")
        return False

    def _handle_filelists(self, handler, distro: str, version: str, repo: str, db_type: str) -> bool:
        """处理filelists.xml.gz"""
        cache_key = f"filelists:{distro}:{version}:{repo}:{self.arch}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/x-gzip')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 先获取repomd.xml找到对应的数据库文件
        repomd_url = f"{self.base_url}/{version}/{repo}/{self.arch}/repodata/repomd.xml"

        try:
            repomd_data = self._fetch(repomd_url)

            # 解析repomd.xml找到filelists文件
            root = ET.fromstring(repomd_data)
            ns = {'repomd': 'http://linux.duke.edu/metadata/repo'}

            data_location = None
            for elem in root.findall('.//repomd:data', ns):
                if elem.get('type') == 'filelists':
                    data_location = elem.find('repomd:location', ns).get('href')
                    break

            if data_location:
                db_url = f"{self.base_url}/{version}/{repo}/{self.arch}/repodata/{data_location}"
                data = self._fetch(db_url)

                if self.cache_enabled:
                    self._set_cache(cache_key, data)

                handler.send_response(200)
                handler.send_header('Content-Type', 'application/x-gzip')
                handler.send_header('Content-Length', str(len(data)))
                handler.end_headers()
                handler.wfile.write(data)
                return True

        except Exception as e:
            pass

        handler.send_error(502, "Failed to fetch filelists database")
        return False

    def _handle_other(self, handler, distro: str, version: str, repo: str, db_type: str) -> bool:
        """处理other.xml.gz"""
        cache_key = f"other:{distro}:{version}:{repo}:{self.arch}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/x-gzip')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 先获取repomd.xml找到对应的数据库文件
        repomd_url = f"{self.base_url}/{version}/{repo}/{self.arch}/repodata/repomd.xml"

        try:
            repomd_data = self._fetch(repomd_url)

            # 解析repomd.xml找到other文件
            root = ET.fromstring(repomd_data)
            ns = {'repomd': 'http://linux.duke.edu/metadata/repo'}

            data_location = None
            for elem in root.findall('.//repomd:data', ns):
                if elem.get('type') == 'other':
                    data_location = elem.find('repomd:location', ns).get('href')
                    break

            if data_location:
                db_url = f"{self.base_url}/{version}/{repo}/{self.arch}/repodata/{data_location}"
                data = self._fetch(db_url)

                if self.cache_enabled:
                    self._set_cache(cache_key, data)

                handler.send_response(200)
                handler.send_header('Content-Type', 'application/x-gzip')
                handler.send_header('Content-Length', str(len(data)))
                handler.end_headers()
                handler.wfile.write(data)
                return True

        except Exception as e:
            pass

        handler.send_error(502, "Failed to fetch other database")
        return False

    def _handle_repo_file(self, handler, distro: str, version: str, repo: str, path: str) -> bool:
        """处理仓库中的其他文件"""
        cache_key = f"file:{distro}:{version}:{repo}:{path.replace('/', ':')}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        url = f"{self.base_url}/{version}/{repo}/{self.arch}/{path}"

        try:
            data = self._fetch(url)

            if self.cache_enabled:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(404, f"File not found: {str(e)}")
            return False

    def _fetch(self, url: str) -> Optional[bytes]:
        """从URL获取数据"""
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'YUM-Mirror/1.0')

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
            print(f"YUM缓存写入失败: {e}")

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
