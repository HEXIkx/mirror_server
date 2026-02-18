#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PyPI镜像代理处理器
支持Python包索引
"""

import os
import json
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional
from datetime import datetime


class PyPIMirror:
    """PyPI镜像代理"""

    def __init__(self, config: dict):
        self.config = config

        # 配置 - storage_dir 基于 base_dir
        self.upstream_url = config.get('upstream_url', 'https://pypi.org')
        self.base_dir = config.get('base_dir', './downloads')
        storage_subdir = config.get('storage_dir', 'pypi')
        self.storage_dir = os.path.join(self.base_dir, storage_subdir)
        self.simple_dir = os.path.join(self.storage_dir, 'simple')
        self.web_dir = os.path.join(self.storage_dir, 'web')

        # 确保存储目录存在
        os.makedirs(self.simple_dir, exist_ok=True)
        os.makedirs(self.web_dir, exist_ok=True)

    def handle_request(self, handler, path: str) -> bool:
        """
        处理PyPI请求
        路径格式: /simple/requests/ 或 /packages/xxx.tar.gz 或 /pypi/web/package 或 /pypi/packages/hash/file
        """
        try:
            import sys
            # 如果路径以 pypi/ 开头，也需要去掉
            path = path.lstrip('/')
            if path.startswith('pypi/'):
                path = path[5:]
            parts = path.strip('/').split('/')

            # 过滤空字符串
            parts = [p for p in parts if p]

            if not parts:
                return self._handle_index(handler)

            if parts[0] == 'simple':
                # Simple API
                import sys
                if len(parts) == 1:
                    # /simple/ - 返回根索引
                    return self._handle_index(handler)
                elif len(parts) == 2:
                    # /simple/package/
                    return self._handle_simple_index(handler, parts[1])
                elif len(parts) >= 3:
                    # /simple/package/version/ 或 /simple/package/version#egg=...
                    return self._handle_package_file(handler, parts[1], '/'.join(parts[2:]))
                else:
                    handler.send_error(400, "Invalid simple API path")
                    return False

            elif parts[0] == 'web':
                # /web/package/ 或 /web/package/json
                # pip sends /pypi/web/<package>/json
                package = parts[1] if len(parts) >= 2 else ''
                return self._handle_web_api(handler, package)

            elif parts[0] == 'packages':
                # 包下载
                filename = '/'.join(parts[1:])
                return self._handle_package_download(handler, filename)

            elif parts[0] == 'legacy':
                # 旧版PyPI兼容
                return self._handle_legacy(handler, '/'.join(parts[1:]))

            else:
                handler.send_error(404, "Unknown API")
                return False

        except Exception as e:
            handler.send_error(500, str(e))
            return False

    def _handle_index(self, handler) -> bool:
        """处理索引请求 - 返回所有可用包的列表"""
        # 从上游获取包列表
        url = self.upstream_url.rstrip('/')
        if url.endswith('/simple'):
            url = url  # 保持 /simple
        else:
            url = url + '/simple'

        try:
            req = urllib.request.Request(url)
            req.add_header('Accept', 'text/html')
            req.add_header('User-Agent', 'PyPI-Mirror/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read().decode('utf-8')

            # 转换相对链接
            # 清华源返回的可能是完整的HTML，需要转换链接
            data = self._convert_simple_index_html(data)
            data_bytes = data.encode('utf-8')

            handler.send_response(200)
            handler.send_header('Content-Type', 'text/html; charset=utf-8')
            handler.send_header('Content-Length', str(len(data_bytes)))
            handler.end_headers()
            handler.wfile.write(data_bytes)
            return True

        except Exception as e:
            handler.send_error(502, f"Failed to fetch package index: {str(e)}")
            return False

    def _convert_simple_index_html(self, html: str) -> str:
        """转换根索引页面的HTML"""
        import re
        # 替换上游链接
        def convert_link(match):
            href = match.group(1)
            text = match.group(2)
            if href.startswith('/simple/'):
                return match.group(0)  # 已经是相对路径
            elif href.startswith('https://pypi.tuna.tsinghua.edu.cn/simple/'):
                simple_part = href.split("/simple/")[-1]
                return f'<a href="/simple/{simple_part}">{text}</a>'
            elif href.startswith('https://'):
                # 其他上游链接，提取包名
                pkg_name = href.rstrip('/').split('/')[-1]
                return f'<a href="/simple/{pkg_name}/">{text}</a>'
            return match.group(0)

        # 匹配 <a href="...">text</a>
        return re.sub(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*)</a>', convert_link, html)

    def _handle_simple_index(self, handler, package: str) -> bool:
        """处理Simple API索引请求"""
        import json
        import time

        package = package.lower()

        # 调试 - 确保函数被调用
        debug_file = '/tmp/pypi_debug.log'
        with open(debug_file, 'a') as f:
            f.write(f"[HANDLE_SIMPLE] START package={package}\n")

        # 检查客户端Accept header
        accept = handler.headers.get('Accept', '')
        wants_json = 'application/vnd.pypi.simple.v1+json' in accept

        # 调试
        debug_file = '/tmp/pypi_debug.log'
        with open(debug_file, 'a') as f:
            f.write(f"[SIMPLE_INDEX] package={package}, wants_json={wants_json}, accept={accept[:50]}\n")

        # 根据请求格式选择正确的缓存key，统一使用 simple/ 前缀
        cache_key = f"simple/{package}"
        
        cached = self._get_cache(cache_key)

        # 调试缓存
        debug_file = '/tmp/pypi_debug.log'
        with open(debug_file, 'a') as f:
            f.write(f"[CACHE_CHECK] cache_key={cache_key}, cached={'YES' if cached else 'NO'}\n")

        if cached:
            # 返回缓存，使用正确的Content-Type
            if wants_json:
                handler.send_response(200)
                handler.send_header('Content-Type', 'application/vnd.pypi.simple.v1+json; charset=utf-8')
            else:
                handler.send_response(200)
                handler.send_header('Content-Type', 'text/html; charset=utf-8')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取HTML
        # upstream_url 已经是完整路径（如 https://pypi.tuna.tsinghua.edu.cn/simple）
        # 所以只需要添加 /package/
        url = f"{self.upstream_url}/{package}/"

        try:
            req = urllib.request.Request(url)
            req.add_header('Accept', 'text/html')
            req.add_header('User-Agent', 'PyPI-Mirror/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read().decode('utf-8')

            # 根据客户端请求返回不同格式，统一使用 simple/ 路径
            if wants_json:
                # 转换为JSON格式
                json_data = self._convert_to_json(package, data)
                proxy_data = json.dumps(json_data)
                content_type = 'application/vnd.pypi.simple.v1+json; charset=utf-8'
                cache_key = f"simple/{package}"
            else:
                # 转换为HTML格式
                debug_file = '/tmp/pypi_debug.log'
                with open(debug_file, 'a') as f:
                    f.write(f"[CONVERT_CALL] Before conversion\n")
                try:
                    proxy_data = self._convert_simple_html(package, data)
                    with open(debug_file, 'a') as f:
                        f.write(f"[CONVERT_CALL] After conversion\n")
                except Exception as e:
                    with open(debug_file, 'a') as f:
                        f.write(f"[CONVERT_ERROR] {e}\n")
                    proxy_data = data  # fallback to raw data
                content_type = 'application/vnd.pypi.simple.v1+html; charset=utf-8'

            if True:
                self._set_cache(cache_key, proxy_data.encode('utf-8'))

            proxy_bytes = proxy_data.encode('utf-8')
            handler.send_response(200)
            handler.send_header('Content-Type', content_type)
            handler.send_header('Content-Length', str(len(proxy_bytes)))
            handler.end_headers()
            handler.wfile.write(proxy_bytes)
            return True

        except urllib.error.HTTPError as e:
            if e.code == 404:
                handler.send_error(404, f"Package not found: {package}")
            else:
                handler.send_error(502, f"Failed to fetch from upstream: {str(e)}")
            return False

    def _convert_to_json(self, package: str, html: str) -> dict:
        """将HTML转换为JSON格式"""
        import re

        # 解析HTML中的链接
        links = []

        # 匹配 <a href="...">text</a>
        pattern = r'<a[^>]+href="([^"]+)"[^>]*>([^<]*)</a>'
        matches = re.findall(pattern, html)

        for href, text in matches:
            # 提取文件名（从链接文本）
            filename = text.strip() if text.strip() else ''

            # 如果没有链接文本，从URL中提取
            if not filename:
                if '#' in href:
                    filename = href.split('#')[0].split('/')[-1]
                else:
                    filename = href.split('/')[-1]

            # JSON格式中URL不应该包含fragment
            # pip从filename字段提取版本号（如 Flask-1.0.0.tar.gz -> 1.0.0）

            # 解析URL并转换为代理路径
            url = href
            if href.startswith('../'):
                # 相对路径 - 需要转换为代理路径
                # 格式: ../../packages/hash1/hash2/fullhash/filename#sha256=...
                # 或: ../../packages/hash1/hash2/filename
                # parts = ['..', '..', 'packages', 'hash1', 'hash2', 'fullhash', 'filename', ...]
                parts = href.split('/')
                try:
                    pkg_idx = parts.index('packages')
                    # 提取从 packages 后面到文件名之前的所有部分作为 hash 路径
                    # 文件名是最后一个非空部分（可能包含 #fragment）
                    # 找到文件名的位置（最后一个部分）
                    filename_idx = len(parts) - 1
                    while filename_idx > pkg_idx and not parts[filename_idx]:
                        filename_idx -= 1
                    # hash_path 是 packages 后面到文件名之前的所有部分
                    if filename_idx > pkg_idx + 1:
                        hash_path = '/'.join(parts[pkg_idx+1:filename_idx])
                    else:
                        hash_path = parts[pkg_idx+1] if pkg_idx + 1 < len(parts) else ''
                        # 文件名: 检查 pkg_idx+3 是否存在且不是哈希
                        if pkg_idx + 3 < len(parts):
                            fname_full = parts[pkg_idx+3]
                            # 如果 fname_full 看起来像哈希（包含 sha256= 或长度>=32的十六进制），则使用原始 filename
                            # 清华源格式: .../hash/filename#sha256=...
                            # 其中 hash 是 28-30 位十六进制
                            is_hash_like = ('sha256=' in fname_full or 'sha512=' in fname_full or
                                          (len(fname_full) >= 28 and all(c in '0123456789abcdef' for c in fname_full[:28].lower())))
                            if is_hash_like:
                                # 这是哈希，不是文件名
                                fname = filename if filename else ''
                            else:
                                # 这是文件名
                                fname = fname_full.split('#')[0]
                                if not filename:
                                    filename = fname
                        else:
                            fname = filename if filename else ''
                        # URL不包含fragment
                        url = f"/pypi/packages/{hash_path}/{fname}"
                except ValueError:
                    pass
            elif href.startswith('/pypi/'):
                # 绝对路径（如 /pypi/packages/hash/filename#egg=package-version）
                # 去掉fragment
                href_clean = href.split('#')[0]
                parts = href_clean.split('/')
                # parts = ['', 'pypi', 'packages', 'hash', 'filename']
                if len(parts) >= 5:
                    hash_path = parts[3]
                    fname = parts[4]
                    if not filename:
                        filename = fname
                    url = f"/pypi/packages/{hash_path}/{fname}"
            elif href.startswith('http'):
                # 绝对URL - 转换为代理路径
                if 'files.pythonhosted.org' in href or 'files.pypi.org' in href:
                    # 格式: https://files.pythonhosted.org/packages/hash1/hash2/完整哈希/filename
                    # 例如: https://files.pythonhosted.org/packages/ec/f9/7f9263c5695f4bd0023734af91bedb2ff8209e8de6ead162f35d8dc762fd/flask-3.1.2-py3-none-any.whl
                    parts = href.split('/packages/')
                    if len(parts) >= 2:
                        path_after_packages = parts[1]
                        # 完整路径: hash1/hash2/完整哈希/filename
                        url = f"/pypi/packages/{path_after_packages}"
                        fname = path_after_packages.split('/')[-1]
                        if not filename:
                            filename = fname
                elif 'pypi.tuna.tsinghua.edu.cn' in href or 'mirrors.tuna.tsinghua.edu.cn' in href:
                    parts = href.rsplit('/', 1)
                    if len(parts) == 2:
                        path_part = parts[0]
                        fname = parts[1]
                        hash_path = path_part.split('/')[-1]
                        if not filename:
                            filename = fname
                        url = f"/pypi/packages/{hash_path}/{fname}"

            link_entry = {
                "filename": filename,
                "url": url
            }

            links.append(link_entry)

        return {
            "meta": {
                "api-version": "1.0",
                "repository-version": "1.0"
            },
            "name": package,
            "files": links
        }

    def _handle_package_file(self, handler, package: str, filename: str) -> bool:
        """处理包文件请求"""
        import urllib.parse

        # 解析文件名
        # 新格式: /pypi/packages/hash/filename#pip=package-version
        # 或旧格式: /pypi/packages/filename?url=...
        parsed = urllib.parse.urlparse(f"/{filename}")
        actual_filename = parsed.path.lstrip('/')
        query_params = urllib.parse.parse_qs(parsed.query)
        fragment = urllib.parse.parse_qs(parsed.fragment) if parsed.fragment else {}

        # 从fragment中提取包信息（用于缓存键）
        actual_package = package
        if 'pip' in fragment:
            # 格式: #pip=flask-2.0.0
            pip_info = fragment['pip'][0]
            if '-' in pip_info:
                # 提取版本号
                parts = pip_info.split('-', 1)
                if len(parts) == 2:
                    actual_package = parts[0]

        cache_key = f"packages/{actual_filename}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 尝试从上游获取
        # 格式: /pypi/packages/hash/filename -> 构造上游URL
        possible_urls = []

        # 获取基础URL（去掉 /simple 后缀）
        base_url = self.upstream_url.rstrip('/')
        if base_url.endswith('/simple'):
            base_url = base_url[:-7]

        # 新格式: hash/filename -> 尝试清华源
        # 使用 actual_filename（已解析的纯文件路径）
        possible_urls.append(f"{base_url}/packages/{actual_filename}")

        # 尝试官方源
        possible_urls.append(f"https://files.pythonhosted.org/packages/{actual_filename}")

        # 如果有查询参数中的URL，也尝试
        if 'url' in query_params:
            possible_urls.insert(0, urllib.parse.unquote(query_params['url'][0]))

        data = None
        last_error = None

        for url in possible_urls:
            try:
                import sys
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'PyPI-Mirror/1.0')

                with urllib.request.urlopen(req, timeout=60) as response:
                    data = response.read()
                    break  # 成功获取，退出循环
            except Exception as e:
                import sys
                last_error = e
                continue

        if data is None:
            handler.send_error(502, f"Failed to fetch package: {last_error}")
            return False

        if True:
            self._set_cache(cache_key, data)

        handler.send_response(200)
        handler.send_header('Content-Type', 'application/octet-stream')
        handler.send_header('Content-Length', str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return True

    def _handle_web_api(self, handler, package: str) -> bool:
        """处理Web API请求"""
        import sys
        package = package.lower()
        cache_key = f"web/{package}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/vnd.pypi.simple.v1+json; charset=utf-8')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取 - 需要去掉 /simple 后缀
        base_url = self.upstream_url.rstrip('/')
        if base_url.endswith('/simple'):
            base_url = base_url[:-7]
        url = f"{base_url}/pypi/{package}/json"

        try:
            req = urllib.request.Request(url)
            req.add_header('Accept', 'application/json')
            req.add_header('User-Agent', 'PyPI-Mirror/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read().decode('utf-8')
                data_json = json.loads(data)

            # 转换URL
                data_json = self._convert_package_json(package, data_json)

            proxy_data = json.dumps(data_json)

            if True:
                self._set_cache(cache_key, proxy_data.encode('utf-8'))

            proxy_bytes = proxy_data.encode('utf-8')
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/vnd.pypi.simple.v1+json; charset=utf-8')
            handler.send_header('Content-Length', str(len(proxy_bytes)))
            handler.end_headers()
            handler.wfile.write(proxy_bytes)
            return True

        except urllib.error.HTTPError as e:
            handler.send_error(502, f"Failed to fetch package info: {str(e)}")
            return False

    def _handle_package_download(self, handler, filename: str) -> bool:
        """处理包下载请求"""
        import sys
        # 使用 packages/ 前缀，保持标准 PyPI 目录结构
        cache_key = f"packages/{filename}"

        cached = self._get_cache(cache_key)
        if cached:
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(cached)))
            handler.end_headers()
            handler.wfile.write(cached)
            return True

        # 从上游获取 - 注意去掉 /simple 后缀
        base_url = self.upstream_url.rstrip('/')
        if base_url.endswith('/simple'):
            base_url = base_url[:-7]  # 去掉 /simple
        url = f"{base_url}/packages/{filename}"

        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'PyPI-Mirror/1.0')

            with urllib.request.urlopen(req, timeout=120) as response:
                data = response.read()

            if True:
                self._set_cache(cache_key, data)

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        except Exception as e:
            handler.send_error(502, f"Failed to download: {str(e)}")
            return False

    def _handle_legacy(self, handler, path: str) -> bool:
        """处理旧版PyPI兼容"""
        handler.send_error(410, "Legacy PyPI API is deprecated")
        return False

    def _convert_simple_html(self, package: str, html: str) -> str:
        """转换Simple API HTML，替换URL为代理地址"""
        import urllib.parse
        import sys
        import os
        # 写入调试文件
        debug_file = '/tmp/pypi_debug.log'
        with open(debug_file, 'a') as f:
            f.write(f"[PyPI] Converting HTML for package: {package}\n")
        # 打印前几个链接用于调试
        import re
        test_matches = re.findall(r'href="([^"]+)"', html)[:3]
        with open(debug_file, 'a') as f:
            f.write(f"[PyPI] Sample links: {test_matches}\n")

        def convert_absolute_url(match):
            """转换绝对URL为代理链接"""
            original_url = match.group(1) if match.lastindex else match.group(0)
            # 提取文件名和完整的hash路径
            # 格式: https://pypi.tuna.tsinghua.edu.cn/packages/hash1/hash2/fullhash/filename
            # 我们将其转换为: /pypi/packages/hash1/hash2/fullhash/filename#pip=<package>
            parts = original_url.rsplit('/', 1)
            if len(parts) == 2:
                path_part = parts[0]
                filename = parts[1]
                # 提取从 packages/ 后面的完整路径（包含完整hash）
                try:
                    pkg_idx = path_part.index('/packages/')
                    hash_path = path_part[pkg_idx + 10:]  # 去掉 /packages/
                except ValueError:
                    hash_path = filename
                return f'href="/pypi/packages/{hash_path}/{filename}#pip={package}-{filename.split("-")[1] if "-" in filename else ""}"'
            return match.group(0)

        # 替换绝对URL - pypi.tuna.tsinghua.edu.cn (清华源)
        html = re.sub(
            r'(https://pypi\.tuna\.tsinghua\.edu\.cn/packages/[^"\']+)',
            convert_absolute_url,
            html
        )
        # 替换绝对URL - mirrors.tuna.tsinghua.edu.cn
        html = re.sub(
            r'(https://mirrors\.tuna\.tsinghua\.edu\.cn/pypi/packages/[^"\']+)',
            convert_absolute_url,
            html
        )
        # 替换绝对URL - files.pypi.org
        html = re.sub(
            r'(https://files\.pypi\.org/packages/[^"\']+)',
            convert_absolute_url,
            html
        )
        # 替换绝对URL - files.pythonhosted.org
        html = re.sub(
            r'(https://files\.pythonhosted\.org/packages/[^"\']+)',
            convert_absolute_url,
            html
        )

        # 替换相对路径链接 - ../../packages/hash1/hash2/fullhash/filename -> /pypi/packages/hash1/hash2/fullhash/filename#pip=...
        def convert_relative_match(match):
            """转换相对路径链接"""
            href = match.group(1)
            debug_file = '/tmp/pypi_debug.log'
            with open(debug_file, 'a') as f:
                f.write(f"[CONVERT] Input href: {href[:80]}...\n")
            # 提取文件名
            filename = href.split('/')[-1].split('#')[0]
            # 提取完整的hash路径（从 packages/ 后面的所有部分除了文件名）
            parts = href.split('/')
            with open(debug_file, 'a') as f:
                f.write(f"[CONVERT] Parts: {parts}\n")
            try:
                pkg_idx = parts.index('packages')
                # packages 后面到倒数第二个是 hash 路径，最后一个是文件名
                hash_parts = parts[pkg_idx+1:-1]  # 除了最后一个（文件名）
                with open(debug_file, 'a') as f:
                    f.write(f"[CONVERT] hash_parts: {hash_parts}\n")
                hash_path = '/'.join(hash_parts) if hash_parts else filename
                with open(debug_file, 'a') as f:
                    f.write(f"[CONVERT] hash_path: {hash_path}\n")
            except ValueError:
                hash_path = filename
                with open(debug_file, 'a') as f:
                    f.write(f"[CONVERT] ValueError, hash_path: {hash_path}\n")

            # 提取版本号 - 从文件名中提取，如 Flask-0.1.tar.gz -> 0.1
            base_name = filename
            # 去掉扩展名
            for ext in ['.tar.gz', '.whl', '.tar.bz2', '.tar.xz']:
                if base_name.endswith(ext):
                    base_name = base_name[:-len(ext)]
                    break

            # 尝试多种大小写组合来去掉包名前缀
            version = base_name
            for pkg_name in [package, package.lower(), package.upper(), package.capitalize()]:
                if base_name.lower().startswith(pkg_name.lower() + '-'):
                    version = base_name[len(pkg_name)+1:]
                    break

            return f'href="/pypi/packages/{hash_path}/{filename}#egg={package}-{version}"'

        # 匹配相对路径的链接
        html = re.sub(
            r'href="(\.\./\.\./packages/[^"]+)"',
            convert_relative_match,
            html
        )
        html = re.sub(
            r"href='(\.\./\.\./packages/[^']+)'",
            convert_relative_match,
            html
        )

        return html

    def _convert_package_json(self, package: str, data: dict) -> dict:
        """转换Package JSON，替换URL为代理地址"""
        # 转换URL函数
        def convert_url(url):
            # 处理 files.pythonhosted.org 和 files.pypi.org
            # 格式: https://files.pythonhosted.org/packages/<hash1>/<hash2>/<完整哈希>/<filename>
            # 例如: https://files.pythonhosted.org/packages/ec/f9/7f9263c5695f4bd0023734af91bedb2ff8209e8de6ead162f35d8dc762fd/flask-3.1.2-py3-none-any.whl
            if 'files.pythonhosted.org' in url or 'files.pypi.org' in url:
                path_parts = url.split('/packages/')
                if len(path_parts) >= 2:
                    # 直接使用 /packages/ 后的完整路径
                    path_after_packages = path_parts[1]
                    return f'/pypi/packages/{path_after_packages}'
            return url

        # 转换urls
        if 'urls' in data:
            for item in data['urls']:
                if 'url' in item:
                    item['url'] = convert_url(item['url'])

        return data

    def _fetch(self, url: str) -> Optional[bytes]:
        """从URL获取数据"""
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'PyPI-Mirror/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()

        except Exception:
            return None

    def _get_cache(self, cache_key: str) -> Optional[bytes]:
        """获取缓存"""
        if not True:
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
                'expires': time.time() + 86400,
                'size': len(data)
            }

            with open(meta_path, 'w') as f:
                json.dump(meta, f)

        except Exception as e:
            print(f"PyPI缓存写入失败: {e}")

    def _get_cache_path(self, cache_key: str) -> str:
        """获取缓存路径"""
        # cache_key 格式: packages/fe/df/88ccbee.../filename
        # 存储路径: downloads/pypi-cn/packages/fe/df/88ccbee.../filename
        # 确保使用正斜杠
        safe_key = cache_key.replace('\\', '/')
        return os.path.join(self.storage_dir, safe_key)

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
