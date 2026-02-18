#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""API v1 版本处理模块"""

import os
import json
import re
import time
import mimetypes
import hashlib
import shutil
import cgi
import zipfile
import base64
from datetime import datetime, timedelta
from urllib.parse import parse_qs

from core.utils import format_file_size, get_file_hash, sanitize_filename, is_safe_path
from core.api_auth import check_endpoint_auth
from core.database import get_db
from core.sync_scheduler import get_sync_scheduler, init_database_sync

# 添加常见图片类型的 MIME 映射（解决某些系统缺少映射的问题）
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('image/bmp', '.bmp')
mimetypes.add_type('image/tiff', '.tiff')
mimetypes.add_type('image/x-icon', '.ico')
mimetypes.add_type('image/jpeg', '.jpg')


class APIv1:
    """API v1 - 基础功能实现"""

    def __init__(self, config):
        self.config = config

        # 初始化数据库
        self.db_enabled = config.get('database', {}).get('enabled', True)
        if self.db_enabled:
            # 优先使用已初始化的数据库实例
            self.db = config.get('_db_instance')
            if not self.db:
                self.db = get_db(config)

            # 初始化同步调度器
            self.scheduler = get_sync_scheduler(config)
            self.file_ops = init_database_sync(config, self.db)[2]
        else:
            self.db = None
            self.scheduler = None
            self.file_ops = None
        
    def handle_request(self, handler, method, path, query_params):
        """处理API v1请求"""

        # 认证检查 - 只对需要认证的端点进行
        auth_manager = getattr(handler, 'auth_manager', None)

        # 构建完整的API路径
        full_path = f"api/v1/{path}"

        # 获取认证要求（只对需要认证的端点检查）
        auth_check = check_endpoint_auth(method, full_path, auth_manager) if auth_manager else {'required': False}

        if auth_check['required']:
            if auth_manager:
                auth_result = auth_manager.validate_request(handler, 'admin')
                if not auth_result.get('authenticated'):
                    handler.send_response(401)
                    handler.send_header('WWW-Authenticate', 'Bearer')
                    handler.send_header('Access-Control-Allow-Origin', '*')
                    handler.send_json_response({
                        "error": "认证Required",
                        "code": "UNAUTHORIZED",
                        "required_permission": auth_check.get('permission')
                    })
                    return

        # 文件管理API (GET /api/v1/files 不需要认证)
        if path == 'files':
            if method == 'GET':
                self.api_list_files(handler, query_params)
            else:
                handler.send_error(405)
        
        elif path.startswith('file/'):
            filename = path[5:]  # 移除 'file/' 前缀
            if method == 'GET':
                if filename.endswith('/preview'):
                    self.api_file_preview(handler, filename[:-8])
                else:
                    self.api_get_file_info(handler, filename)
            elif method == 'DELETE':
                self.api_delete_file(handler, filename)
            else:
                handler.send_error(405)
        
        # 同步API
        elif path.startswith('sync/'):
            sync_action = path[5:]
            if method == 'GET':
                if sync_action == 'sources':
                    self.api_get_sync_sources(handler)
                elif sync_action == 'status':
                    self.api_get_sync_status(handler)
                else:
                    handler.send_error(404)
            elif method == 'POST':
                if sync_action == 'sources':
                    self.api_add_sync_source(handler)
                elif sync_action == 'start':
                    self.api_start_sync(handler)
                elif sync_action == 'stop':
                    self.api_stop_sync(handler)
                else:
                    handler.send_error(404)
            elif method == 'DELETE':
                if sync_action.startswith('sources/'):
                    self.api_remove_sync_source(handler, sync_action[8:])
                else:
                    handler.send_error(404)
            elif method == 'PUT':
                if sync_action.startswith('sources/'):
                    self.api_update_sync_source(handler, sync_action[8:])
                else:
                    handler.send_error(404)
            else:
                handler.send_error(405)
        
        # 其他API
        elif path == 'upload':
            if method == 'POST':
                self.handle_upload(handler)
            else:
                handler.send_error(405)
        
        elif path == 'mkdir':
            if method == 'PUT':
                self.api_create_directory(handler)
            else:
                handler.send_error(405)
        
        elif path == 'batch':
            if method == 'POST':
                self.api_batch_operations(handler)
            else:
                handler.send_error(405)
        
        elif path == 'archive':
            if method == 'POST':
                self.api_archive_operations(handler)
            else:
                handler.send_error(405)
        
        elif path == 'search':
            if method == 'GET':
                self.api_search_files(handler, query_params)
            else:
                handler.send_error(405)
        
        elif path == 'stats':
            if method == 'GET':
                self.api_get_stats(handler)
            else:
                handler.send_error(405)
        
        elif path == 'health':
            if method == 'GET':
                self.api_health_check(handler)
            else:
                handler.send_error(405)
        
        elif path == 'config':
            if method == 'GET':
                self.api_get_config(handler)
            else:
                handler.send_error(405)
        
        # MC API
        elif path.startswith('mc/'):
            mc_path = path[3:]
            self.handle_mc_api(handler, method, mc_path)
        
        # Mirror API
        elif path.startswith('mirror/'):
            mirror_path = path[7:]
            self.handle_mirror_api(handler, method, mirror_path)
        
        else:
            handler.send_error(404)
    
    # ==================== 文件管理API ====================
    
    def api_list_files(self, handler, query_params):
        """API: 列出文件"""
        recursive = query_params.get('recursive', ['false'])[0].lower() == 'true'

        # 获取请求的路径
        path_param = query_params.get('path', [''])[0]

        # 处理根路径和空路径
        if path_param in ['', '/', '\\']:
            target_dir = self.config['base_dir']
        else:
            base_dir = self.config['base_dir']
            # 去掉前导斜杠，避免 os.path.join 忽略 base_dir
            path_param = path_param.lstrip('/')
            target_dir = os.path.join(base_dir, path_param)

            # 安全检查
            if not is_safe_path(base_dir, target_dir):
                handler.send_json_response({"error": "Invalid path"}, 403)
                return

            if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
                handler.send_json_response({"error": "Directory not found"}, 404)
                return

        files = []
        dirs = []

        try:
            items = os.listdir(target_dir)

            for item in items:
                item_path = os.path.join(target_dir, item)
                rel_path = os.path.relpath(item_path, self.config['base_dir']).replace("\\", "/")

                # 隐藏文件检查
                if self.config.get('ignore_hidden', True) and item.startswith('.'):
                    continue

                if os.path.isdir(item_path):
                    dirs.append({
                        "name": item,
                        "path": rel_path + "/",
                        "is_dir": True,
                        "modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat()
                    })
                else:
                    try:
                        size = os.path.getsize(item_path)
                        mtime = os.path.getmtime(item_path)
                        mime_type, _ = mimetypes.guess_type(item_path)
                        if mime_type is None:
                            mime_type = "application/octet-stream"

                        download_count = 0
                        if self.config.get('enable_stats', True):
                            download_count = handler.get_download_count(rel_path)

                        files.append({
                            "name": item,
                            "path": rel_path,
                            "size": size,
                            "size_formatted": format_file_size(size),
                            "type": mime_type,
                            "modified": datetime.fromtimestamp(mtime).isoformat(),
                            "download_count": download_count,
                            "sha256": get_file_hash(item_path) if self.config.get('calculate_hash', False) else None
                        })
                    except OSError:
                        continue
        except PermissionError:
            handler.send_json_response({"error": "Permission denied"}, 403)
            return
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
            return

        # 排序（目录在前，文件在后）
        sort_by = handler.headers.get('X-Sort-By', self.config.get('sort_by', 'name'))
        reverse = handler.headers.get('X-Sort-Reverse', str(self.config.get('sort_reverse', False))).lower() == 'true'

        if sort_by == 'name':
            dirs.sort(key=lambda x: x['name'].lower(), reverse=reverse)
            files.sort(key=lambda x: x['name'].lower(), reverse=reverse)
        elif sort_by == 'size':
            files.sort(key=lambda x: x['size'], reverse=reverse)
        elif sort_by == 'modified':
            dirs.sort(key=lambda x: x['modified'], reverse=reverse)
            files.sort(key=lambda x: x['modified'], reverse=reverse)

        # 合并目录和文件
        all_items = dirs + files

        # 分页
        try:
            page = int(handler.headers.get('X-Page', 1))
            per_page = int(handler.headers.get('X-Per-Page', 50))
        except ValueError:
            page = 1
            per_page = 50

        total = len(all_items)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_items = all_items[start:end]

        handler.send_json_response({
            "files": paginated_items,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 0
            },
            "path": path_param,
            "has_parent": bool(path_param)
        })
    
    def api_get_file_info(self, handler, filename):
        """API: 获取特定文件信息"""
        full_path = os.path.join(self.config['base_dir'], filename)
        if not is_safe_path(self.config['base_dir'], full_path):
            handler.send_json_response({"error": "Access denied"}, 403)
            return
        if not os.path.exists(full_path):
            handler.send_json_response({"error": "File not found"}, 404)
            return

        try:
            stat = os.stat(full_path)
            size = stat.st_size
            mime_type, encoding = mimetypes.guess_type(full_path)
            if mime_type is None:
                mime_type = "application/octet-stream"

            download_count = 0
            if self.config.get('enable_stats', True):
                download_count = handler.get_download_count(filename)

            file_info = {
                "name": os.path.basename(full_path),
                "path": filename,
                "size": size,
                "size_formatted": format_file_size(size),
                "type": mime_type,
                "encoding": encoding,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
                "download_count": download_count,
                "sha256": get_file_hash(full_path) if self.config.get('calculate_hash', False) else None,
                "permissions": oct(stat.st_mode)[-3:],
                "inode": stat.st_ino
            }
            handler.send_json_response(file_info)
        except OSError as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    def api_file_preview(self, handler, file_path):
        """API: 文件预览"""
        import html as html_escape

        full_path = os.path.join(self.config['base_dir'], file_path)

        if not is_safe_path(self.config['base_dir'], full_path) or not os.path.isfile(full_path):
            handler.send_json_response({"error": "File not found or access denied"}, 404)
            return

        max_preview_size = self.config.get('max_preview_size', 10 * 1024 * 1024)
        file_size = os.path.getsize(full_path)

        # 图片文件不限制预览大小（允许任意大小的图片）
        mime_type_check, _ = mimetypes.guess_type(full_path)
        file_ext_check = file_path.lower().split('.')[-1] if '.' in file_path else ''
        image_exts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tif', 'tiff']
        is_image_file = (mime_type_check and mime_type_check.startswith('image/')) or (file_ext_check in image_exts)

        if file_size > max_preview_size and not is_image_file:
            handler.send_json_response({
                "error": f"File too large for preview (max {format_file_size(max_preview_size)})",
                "file_size": file_size,
                "max_preview_size": max_preview_size
            }, 413)
            return

        mime_type, _ = mimetypes.guess_type(full_path)
        file_ext = file_path.lower().split('.')[-1] if '.' in file_path else ''

        preview_data = {
            "path": file_path,
            "name": os.path.basename(file_path),
            "size": file_size,
            "type": mime_type or "application/octet-stream",
            "preview_available": False
        }

        try:
            # 图片文件（PNG、JPG、GIF、BMP、WebP、SVG 等）
            # 常见图片扩展名列表（不区分大小写）
            image_exts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tif', 'tiff']
            is_image = (mime_type and mime_type.startswith('image/')) or (file_ext.lower() in image_exts)

            if is_image and file_ext.lower() != 'svg':
                # 确定 MIME 类型
                img_mime = mime_type
                if not img_mime:
                    # 根据扩展名推断 MIME
                    ext_mime_map = {
                        'png': 'image/png',
                        'jpg': 'image/jpeg',
                        'jpeg': 'image/jpeg',
                        'gif': 'image/gif',
                        'bmp': 'image/bmp',
                        'webp': 'image/webp',
                        'ico': 'image/x-icon',
                        'tif': 'image/tiff',
                        'tiff': 'image/tiff',
                    }
                    img_mime = ext_mime_map.get(file_ext.lower(), 'image/png')

                # 普通图片（非 SVG）- 直接作为图片预览
                # 图片预览最大 20MB
                max_read = 5 * 1024 * 1024 if img_mime == 'image/gif' else 20 * 1024 * 1024
                with open(full_path, 'rb') as f:
                    image_data = f.read(max_read)
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "image",
                        "data_url": f"data:{img_mime};base64,{base64_data}",
                        "truncated": file_size > max_read
                    })

            # SVG 文件 - 作为图片预览，同时保存源代码
            elif file_ext == 'svg':
                # 先尝试作为图片预览
                try:
                    with open(full_path, 'rb') as f:
                        image_data = f.read(1024 * 1024)
                        base64_data = base64.b64encode(image_data).decode('utf-8')
                        preview_data.update({
                            "preview_available": True,
                            "preview_type": "image",
                            "data_url": f"data:image/svg+xml;base64,{base64_data}",
                            "truncated": file_size > 1024 * 1024
                        })
                except Exception:
                    pass

                # 同时保存源代码用于查看
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(10000)
                        preview_data.update({
                            "svg_content": content,
                            "svg_truncated": len(content) == 10000
                        })
                except Exception:
                    pass

            # JSON 文件
            elif mime_type == 'application/json' or file_ext == 'json':
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read(10000)
                    try:
                        json_data = json.loads(content)
                        preview_data.update({
                            "preview_available": True,
                            "preview_type": "json",
                            "content": json_data,
                            "truncated": len(content) == 10000
                        })
                    except json.JSONDecodeError:
                        preview_data.update({
                            "preview_available": True,
                            "preview_type": "text",
                            "content": content,
                            "truncated": len(content) == 10000
                        })

            # Markdown 文件
            elif mime_type == 'text/markdown' or file_ext in ['md', 'markdown']:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "markdown",
                        "content": content,
                        "truncated": len(content) == 10000
                    })

            # XML 文件（排除 SVG）
            elif mime_type in ['application/xml'] or (file_ext == 'xml' and not mime_type.startswith('image/')):
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "xml",
                        "content": content,
                        "truncated": len(content) == 10000
                    })

            # CSV 文件
            elif mime_type == 'text/csv' or file_ext == 'csv':
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(5000)
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "csv",
                        "content": content,
                        "truncated": len(content) == 5000
                    })

            # YAML 文件
            elif mime_type in ['application/x-yaml', 'text/yaml'] or file_ext in ['yaml', 'yml']:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "yaml",
                        "content": content,
                        "truncated": len(content) == 10000
                    })

            # 音频文件
            elif mime_type and mime_type.startswith('audio/'):
                with open(full_path, 'rb') as f:
                    audio_data = f.read(128 * 1024)
                    base64_data = base64.b64encode(audio_data).decode('utf-8')
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "audio",
                        "data_url": f"data:{mime_type};base64,{base64_data}",
                        "truncated": file_size > 128 * 1024
                    })

            # PDF 文件
            elif mime_type == 'application/pdf':
                with open(full_path, 'rb') as f:
                    pdf_data = f.read(1024 * 1024)
                    base64_data = base64.b64encode(pdf_data).decode('utf-8')
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "pdf",
                        "data_url": f"data:{mime_type};base64,{base64_data}",
                        "truncated": file_size > 1024 * 1024
                    })

            # 特殊扩展名的文本文件
            elif file_ext in ['js', 'ts', 'jsx', 'tsx', 'py', 'rb', 'go', 'rs', 'java', 'c', 'cpp', 'h', 'cs', 'swift', 'kt', 'php', 'sh', 'bat', 'ps1', 'lua', 'r', 'scala', 'yaml', 'yml', 'ini', 'conf', 'config', 'env', 'toml', 'log', 'properties', 'gradle', 'makefile', 'dockerfile', 'nginx', 'apache', 'toml', 'sql', 'prql', 'vcl', 'hlsl', 'glsl', 'asm', 's', 'S']:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "text",
                        "content": content,
                        "truncated": len(content) == 10000
                    })

            # 文本文件
            elif mime_type and mime_type.startswith('text/'):
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "text",
                        "content": content,
                        "truncated": len(content) == 10000
                    })

        except Exception as e:
            preview_data["preview_error"] = str(e)

        handler.send_json_response(preview_data)
    
    def api_delete_file(self, handler, rel_path):
        """API: 删除文件或目录"""
        if not rel_path:
            handler.send_json_response({"error": "No file specified"}, 400)
            return
        if self.delete_file(handler, rel_path):
            handler.send_json_response({"success": True})
        else:
            handler.send_json_response({"error": "File not found or access denied"}, 404)
    
    def delete_file(self, handler, rel_path):
        """删除文件或目录"""
        full_path = os.path.join(self.config['base_dir'], rel_path)
        if not is_safe_path(self.config['base_dir'], full_path):
            return False
        if not os.path.exists(full_path):
            return False

        # 获取文件ID用于数据库（在会话中立即提取数据）
        file_id = None
        if self.db:
            try:
                with self.db.session() as session:
                    record = session.query(FileRecord.file_id).filter(
                        FileRecord.path == rel_path,
                        FileRecord.is_deleted == False
                    ).first()
                    if record:
                        file_id = record.file_id
            except Exception:
                pass

        try:
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.unlink(full_path)

            # 同步删除到数据库
            if self.db and file_id:
                self.db.delete_file(file_id)

            if self.config.get('enable_stats', True):
                stats = handler.load_stats()
                if rel_path in stats:
                    del stats[rel_path]
                handler.save_stats(stats)
            return True
        except Exception:
            return False
    
    def api_create_directory(self, handler):
        """API: 创建目录"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length:
            try:
                data = json.loads(handler.rfile.read(content_length))
                dir_path = data.get('path', '')
                if not dir_path:
                    handler.send_json_response({"error": "No directory path specified"}, 400)
                    return

                full_path = os.path.join(self.config['base_dir'], dir_path)
                if not is_safe_path(self.config['base_dir'], full_path):
                    handler.send_json_response({"error": "Invalid path"}, 403)
                    return

                os.makedirs(full_path, exist_ok=True)

                # 同步到数据库
                if self.db:
                    self.db.add_file(
                        file_id=hashlib.md5(dir_path.encode()).hexdigest(),
                        path=dir_path.rstrip('/') + '/',
                        name=os.path.basename(dir_path.rstrip('/')),
                        is_dir=True,
                        created_at=time.time()
                    )

                handler.send_json_response({"success": True, "path": dir_path})
            except json.JSONDecodeError:
                handler.send_json_response({"error": "Invalid JSON data"}, 400)
            except Exception as e:
                handler.send_json_response({"success": False, "error": str(e)}, 500)
        else:
            handler.send_json_response({"error": "No data provided"}, 400)
    
    def api_search_files(self, handler, query_params):
        """文件搜索"""
        search_term = query_params.get('q', [''])[0].lower()
        search_type = query_params.get('type', ['all'])[0]
        max_results = int(query_params.get('limit', ['100'])[0])
        offset = int(query_params.get('offset', ['0'])[0])
        
        if not search_term:
            handler.send_json_response({"error": "No search term provided"}, 400)
            return
    
        results = []
        
        for root, dirs, files in os.walk(self.config['base_dir']):
            if search_type in ['all', 'dir']:
                for dir_name in dirs:
                    if search_term in dir_name.lower():
                        full_path = os.path.join(root, dir_name)
                        rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                        try:
                            mtime = os.path.getmtime(full_path)
                            results.append({
                                "name": dir_name,
                                "path": rel_path + "/",
                                "type": "directory",
                                "size": 0,
                                "modified": datetime.fromtimestamp(mtime).isoformat(),
                                "match_type": "directory_name"
                            })
                        except OSError:
                            continue
            
            if search_type in ['all', 'file']:
                for file_name in files:
                    if search_term in file_name.lower():
                        full_path = os.path.join(root, file_name)
                        rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                        try:
                            size = os.path.getsize(full_path)
                            mtime = os.path.getmtime(full_path)
                            mime_type, _ = mimetypes.guess_type(full_path)
                            results.append({
                                "name": file_name,
                                "path": rel_path,
                                "type": mime_type or "application/octet-stream",
                                "size": size,
                                "size_formatted": format_file_size(size),
                                "modified": datetime.fromtimestamp(mtime).isoformat(),
                                "match_type": "file_name"
                            })
                        except OSError:
                            continue
            
            if len(results) >= max_results + offset:
                break
    
        paginated_results = results[offset:offset + max_results]
        
        handler.send_json_response({
            "query": search_term,
            "search_type": search_type,
            "total_count": len(results),
            "returned_count": len(paginated_results),
            "offset": offset,
            "limit": max_results,
            "results": paginated_results
        })
    
    # ==================== 同步API ====================

    def api_get_sync_sources(self, handler):
        """获取所有同步源"""
        # 检查 sync_manager 是否存在
        if not hasattr(handler, 'sync_manager') or handler.sync_manager is None:
            handler.send_json_response({"sources": [], "count": 0, "error": "同步管理器未初始化"})
            return

        sources = handler.sync_manager.sync_sources
        # 转换为数组格式
        sources_list = []
        for name, config in sources.items():
            item = {"name": name}
            item.update(config)
            # 获取同步状态中的额外信息
            if name in handler.sync_manager.sync_status:
                status = handler.sync_manager.sync_status[name]
                item['next_sync'] = status.get('next_sync')
                item['last_sync'] = status.get('last_sync')
            sources_list.append(item)
        handler.send_json_response({"sources": sources_list, "count": len(sources_list)})

    def api_get_sync_status(self, handler):
        """获取同步状态"""
        # 检查 sync_manager 是否存在
        if not hasattr(handler, 'sync_manager') or handler.sync_manager is None:
            handler.send_json_response({"running": False, "progress": 0, "sources": {}, "error": "同步管理器未初始化"})
            return

        status = handler.sync_manager.get_sync_status()
        handler.send_json_response(status)

    def api_add_sync_source(self, handler):
        """添加同步源"""
        # 检查 sync_manager 是否存在
        if not hasattr(handler, 'sync_manager') or handler.sync_manager is None:
            handler.send_json_response({"error": "同步管理器未初始化", "success": False}, 500)
            return

        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "没有提供数据"}, 400)
            return

        try:
            data = json.loads(handler.rfile.read(content_length))
            name = data.get('name')
            config = data.get('config')

            if not name or not config:
                handler.send_json_response({"error": "缺少名称或配置"}, 400)
                return

            print(f"[API] 添加同步源: {name}")
            handler.sync_manager.add_sync_source(name, config)
            print(f"[API] 添加同步源完成: {name}")
            handler.send_json_response({"success": True, "name": name})

        except Exception as e:
            handler.send_json_response({"error": str(e)}, 400)

    def api_remove_sync_source(self, handler, name):
        """移除同步源"""
        # 检查 sync_manager 是否存在
        if not hasattr(handler, 'sync_manager') or handler.sync_manager is None:
            handler.send_json_response({"error": "同步管理器未初始化", "success": False}, 500)
            return

        if not name:
            handler.send_json_response({"error": "未指定同步源名称"}, 400)
            return
        handler.sync_manager.remove_sync_source(name)
        handler.send_json_response({"success": True})

    def api_update_sync_source(self, handler, name):
        """更新同步源配置（包括定时同步）"""
        # 检查 sync_manager 是否存在
        if not hasattr(handler, 'sync_manager') or handler.sync_manager is None:
            handler.send_json_response({"error": "同步管理器未初始化", "success": False}, 500)
            return

        if not name:
            handler.send_json_response({"error": "未指定同步源名称"}, 400)
            return

        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "没有提供数据"}, 400)
            return

        try:
            data = json.loads(handler.rfile.read(content_length))
            config = data.get('config', {})

            with handler.sync_manager.sync_lock:
                if name not in handler.sync_manager.sync_sources:
                    handler.send_json_response({"error": "同步源不存在"}, 404)
                    return

                # 更新配置
                handler.sync_manager.sync_sources[name].update(config)

                # 更新同步状态中的定时配置
                if name in handler.sync_manager.sync_status:
                    if 'schedule' in config:
                        handler.sync_manager.sync_status[name]['schedule'] = config['schedule']
                    if hasattr(handler.sync_manager, '_calculate_next_sync'):
                        handler.sync_manager._calculate_next_sync(name)

            handler.sync_manager.save_sync_state()
            handler.send_json_response({"success": True, "name": name})

        except Exception as e:
            handler.send_json_response({"error": str(e)}, 400)

    def api_start_sync(self, handler):
        """开始同步"""
        # 检查 sync_manager 是否存在
        if not hasattr(handler, 'sync_manager') or handler.sync_manager is None:
            handler.send_json_response({"error": "同步管理器未初始化", "success": False}, 500)
            return

        # 简化实现 - 需要从请求体获取参数
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length:
            try:
                data = json.loads(handler.rfile.read(content_length))
                name = data.get('name')
                if name:
                    if handler.sync_manager.start_sync(name):
                        handler.send_json_response({"success": True, "name": name})
                    else:
                        handler.send_json_response({"error": "同步源不存在"}, 404)
                else:
                    handler.sync_manager.start_all_sync()
                    handler.send_json_response({"success": True, "action": "start_all"})
            except Exception as e:
                handler.send_json_response({"error": str(e)}, 400)
        else:
            handler.sync_manager.start_all_sync()
            handler.send_json_response({"success": True, "action": "start_all"})

    def api_stop_sync(self, handler):
        """停止同步"""
        # 检查 sync_manager 是否存在
        if not hasattr(handler, 'sync_manager') or handler.sync_manager is None:
            handler.send_json_response({"error": "同步管理器未初始化", "success": False}, 500)
            return

        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length:
            try:
                data = json.loads(handler.rfile.read(content_length))
                name = data.get('name')
                if name:
                    handler.sync_manager.stop_sync(name)
                    handler.send_json_response({"success": True, "name": name})
                else:
                    handler.sync_manager.stop_all_sync()
                    handler.send_json_response({"success": True, "action": "stop_all"})
            except Exception as e:
                handler.send_json_response({"error": str(e)}, 400)
        else:
            handler.sync_manager.stop_all_sync()
            handler.send_json_response({"success": True, "action": "stop_all"})
    
    # ==================== 上传API ====================
    
    def handle_upload(self, handler):
        """处理文件上传 - 完整实现"""
        content_type = handler.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            handler.send_error(400, "Invalid content type")
            return
    
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            max_upload = self.config.get('max_upload_size', 1024 * 1024 * 1024)
            
            if content_length > max_upload:
                handler.send_json_response({
                    "success": False,
                    "error": f"文件太大。最大允许 {format_file_size(max_upload)}"
                }, 413)
                return
                
            try:
                disk_usage = shutil.disk_usage(self.config['base_dir'])
                if content_length > disk_usage.free:
                    handler.send_json_response({
                        "success": False, 
                        "error": f"磁盘空间不足。需要: {format_file_size(content_length)}, 可用: {format_file_size(disk_usage.free)}"
                    }, 507)
                    return
            except Exception as e:
                print(f"检查磁盘空间失败: {e}")
    
        except ValueError:
            handler.send_json_response({"success": False, "error": "无效的内容长度"}, 400)
            return
    
        try:
            fs = cgi.FieldStorage(
                fp=handler.rfile,
                headers=handler.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': content_type,
                    'CONTENT_LENGTH': str(content_length)
                },
                keep_blank_values=True
            )
    
            uploaded_files = []
            target_dir = ""
    
            if 'path' in fs:
                target_dir = fs['path'].value.strip().rstrip("/")
                if target_dir and not is_safe_path(self.config['base_dir'], os.path.join(self.config['base_dir'], target_dir)):
                    handler.send_json_response({"success": False, "error": "无效的目标路径"}, 403)
                    return
    
            for field in fs.list:
                if field.filename:
                    filename = sanitize_filename(field.filename)
    
                    if target_dir:
                        full_path = os.path.join(self.config['base_dir'], target_dir, filename)
                    else:
                        full_path = os.path.join(self.config['base_dir'], filename)
    
                    if not is_safe_path(self.config['base_dir'], full_path):
                        handler.send_json_response({"success": False, "error": "禁止访问此路径"}, 403)
                        return
    
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
                    if os.path.exists(full_path):
                        if not self.config.get('overwrite_existing', False):
                            handler.send_json_response({
                                "success": False,
                                "error": f"文件已存在: {filename}",
                                "existing_file": filename
                            }, 409)
                            return
                        else:
                            backup_path = f"{full_path}.backup.{int(time.time())}"
                            try:
                                shutil.move(full_path, backup_path)
                            except Exception as e:
                                print(f"备份原文件失败: {e}")
    
                    file_size = 0
                    temp_path = f"{full_path}.tmp.{int(time.time())}"
                    
                    try:
                        with open(temp_path, 'wb') as f:
                            chunk_size = 64 * 1024
                            total_written = 0
                            
                            while True:
                                chunk = field.file.read(chunk_size)
                                if not chunk:
                                    break
                                f.write(chunk)
                                total_written += len(chunk)
                                file_size = total_written
                        
                        if content_length > 0 and file_size != content_length:
                            raise IOError(f"文件大小不匹配。期望: {content_length}, 实际: {file_size}")
                        
                        if os.path.exists(full_path):
                            os.remove(full_path)
                        os.rename(temp_path, full_path)
                        
                        if self.config.get('file_mode'):
                            try:
                                os.chmod(full_path, int(self.config['file_mode'], 8))
                            except Exception as e:
                                print(f"设置文件权限失败: {e}")
                        
                        rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")

                        # 同步到数据库
                        if self.db:
                            file_hash = get_file_hash(full_path) if self.config.get('calculate_hash', False) else None
                            self.db.add_file(
                                file_id=hashlib.md5(rel_path.encode()).hexdigest(),
                                path=rel_path,
                                name=filename,
                                size=file_size,
                                hash=file_hash,
                                is_dir=False,
                                created_at=time.time()
                            )

                        uploaded_files.append({
                            "filename": filename,
                            "path": rel_path,
                            "size": file_size,
                            "size_formatted": format_file_size(file_size),
                            "sha256": get_file_hash(full_path) if self.config.get('calculate_hash', False) else None
                        })
    
                    except IOError as e:
                        if os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                            except:
                                pass
                        
                        error_msg = str(e)
                        if "No space left on device" in error_msg:
                            error_msg = "磁盘空间不足，无法完成上传"
                        elif "Permission denied" in error_msg:
                            error_msg = "没有写入权限"
                        
                        handler.send_json_response({
                            "success": False,
                            "error": f"文件写入失败: {error_msg}"
                        }, 500)
                        return
                        
                    except Exception as e:
                        if os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                            except:
                                pass
                        
                        handler.send_json_response({
                            "success": False,
                            "error": f"上传处理失败: {str(e)}"
                        }, 500)
                        return
    
            if not uploaded_files:
                handler.send_json_response({"success": False, "error": "没有上传文件或文件数据无效"}, 400)
                return
    
            handler.send_json_response({
                "success": True,
                "message": f"成功上传 {len(uploaded_files)} 个文件",
                "files": uploaded_files
            })
    
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            if self.config.get('verbose', 0) > 0:
                print(f"上传错误: {e}")
                print(f"详细跟踪: {error_details}")
            
            handler.send_json_response({
                "success": False,
                "error": f"上传失败: {str(e)}"
            }, 500)
    
    # ==================== 批量操作API ====================
    
    def api_batch_operations(self, handler):
        """API: 批量操作"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No data provided"}, 400)
            return
            
        try:
            data = json.loads(handler.rfile.read(content_length))
            operation = data.get('operation')
            files = data.get('files', [])
            target_dir = data.get('target_dir', '')
            
            if not operation or not files:
                handler.send_json_response({"error": "Missing operation or files"}, 400)
                return
                
            results = []
            success_count = 0
            error_count = 0
            
            for file_path in files:
                try:
                    full_path = os.path.join(self.config['base_dir'], file_path)
                    
                    if not is_safe_path(self.config['base_dir'], full_path):
                        results.append({"file": file_path, "status": "error", "error": "Access denied"})
                        error_count += 1
                        continue
                    
                    if operation == "delete":
                        if self.delete_file(handler, file_path):
                            results.append({"file": file_path, "status": "success"})
                            success_count += 1
                        else:
                            results.append({"file": file_path, "status": "error", "error": "File not found"})
                            error_count += 1
                    
                    elif operation in ["move", "copy"]:
                        if not target_dir:
                            results.append({"file": file_path, "status": "error", "error": "Target directory required"})
                            error_count += 1
                            continue
                            
                        target_path = os.path.join(self.config['base_dir'], target_dir, os.path.basename(file_path))
                        
                        if not is_safe_path(self.config['base_dir'], target_path):
                            results.append({"file": file_path, "status": "error", "error": "Invalid target path"})
                            error_count += 1
                            continue
                            
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        if operation == "move":
                            shutil.move(full_path, target_path)

                            # 同步移动到数据库 (删除旧记录，创建新记录)
                            if self.db:
                                old_record = self.db.get_file_by_path(file_path)
                                if old_record:
                                    self.db.delete_file(old_record.file_id)

                                rel_path = os.path.relpath(target_path, self.config['base_dir']).replace("\\", "/")
                                self.db.add_file(
                                    file_id=hashlib.md5(rel_path.encode()).hexdigest(),
                                    path=rel_path,
                                    name=os.path.basename(target_path),
                                    size=old_record.size if old_record else 0,
                                    hash=old_record.hash if old_record else None,
                                    created_at=time.time()
                                )
                        else:
                            shutil.copy2(full_path, target_path)

                            # 同步复制到数据库
                            if self.db:
                                rel_path = os.path.relpath(target_path, self.config['base_dir']).replace("\\", "/")
                                self.db.add_file(
                                    file_id=hashlib.md5(rel_path.encode()).hexdigest(),
                                    path=rel_path,
                                    name=os.path.basename(target_path),
                                    size=os.path.getsize(target_path),
                                    created_at=time.time()
                                )

                        results.append({
                            "file": file_path,
                            "status": "success",
                            "new_path": os.path.join(target_dir, os.path.basename(file_path)).replace("\\", "/")
                        })
                        success_count += 1
                    
                    else:
                        results.append({"file": file_path, "status": "error", "error": "Invalid operation"})
                        error_count += 1
                    
                except Exception as e:
                    results.append({"file": file_path, "status": "error", "error": str(e)})
                    error_count += 1
            
            handler.send_json_response({
                "operation": operation,
                "total_files": len(files),
                "success_count": success_count,
                "error_count": error_count,
                "results": results
            })
            
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    # ==================== 压缩API ====================
    
    def api_archive_operations(self, handler):
        """API: 压缩和解压缩操作"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No data provided"}, 400)
            return
            
        try:
            data = json.loads(handler.rfile.read(content_length))
            operation = data.get('operation')
            files = data.get('files', [])
            archive_name = data.get('archive_name', 'archive.zip')
            target_dir = data.get('target_dir', '')
            
            if not operation or not files:
                handler.send_json_response({"error": "Missing operation or files"}, 400)
                return
                
            archive_path = os.path.join(self.config['base_dir'], target_dir, archive_name)
            if not is_safe_path(self.config['base_dir'], archive_path):
                handler.send_json_response({"error": "Invalid archive path"}, 403)
                return
                
            if operation == "compress":
                self._compress_files(handler, files, archive_path)
            elif operation == "extract":
                self._extract_archive(handler, archive_path, target_dir)
            else:
                handler.send_json_response({"error": "Invalid operation"}, 400)
                
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    def _compress_files(self, handler, files, archive_path):
        """压缩文件"""
        try:
            os.makedirs(os.path.dirname(archive_path), exist_ok=True)
            
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in files:
                    full_path = os.path.join(self.config['base_dir'], file_path)
                    if is_safe_path(self.config['base_dir'], full_path) and os.path.exists(full_path):
                        arcname = os.path.relpath(full_path, self.config['base_dir'])
                        zipf.write(full_path, arcname)
            
            rel_path = os.path.relpath(archive_path, self.config['base_dir']).replace("\\", "/")

            # 同步到数据库
            if self.db:
                self.db.add_file(
                    file_id=hashlib.md5(rel_path.encode()).hexdigest(),
                    path=rel_path,
                    name=os.path.basename(archive_path),
                    size=os.path.getsize(archive_path),
                    is_dir=False,
                    created_at=time.time()
                )

            handler.send_json_response({
                "operation": "compress",
                "archive_path": rel_path,
                "compressed_files": len(files),
                "archive_size": os.path.getsize(archive_path)
            })
            
        except Exception as e:
            handler.send_json_response({"error": f"Compression failed: {str(e)}"}, 500)
    
    def _extract_archive(self, handler, archive_path, target_dir):
        """解压缩文件"""
        try:
            if not os.path.exists(archive_path):
                handler.send_json_response({"error": "Archive not found"}, 404)
                return
                
            extract_dir = os.path.join(self.config['base_dir'], target_dir)
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                for member in zipf.namelist():
                    member_path = os.path.join(extract_dir, member)
                    if not is_safe_path(self.config['base_dir'], member_path):
                        handler.send_json_response({"error": "Unsafe archive contents"}, 403)
                        return
                zipf.extractall(extract_dir)

            # 同步提取的文件到数据库
            if self.db:
                extracted_files = []
                for member in zipf.namelist():
                    member_path = os.path.join(extract_dir, member)
                    if os.path.isfile(member_path):
                        rel_member_path = os.path.relpath(member_path, self.config['base_dir']).replace("\\", "/")
                        self.db.add_file(
                            file_id=hashlib.md5(rel_member_path.encode()).hexdigest(),
                            path=rel_member_path,
                            name=os.path.basename(member),
                            size=os.path.getsize(member_path),
                            is_dir=False,
                            created_at=time.time()
                        )
                        extracted_files.append(rel_member_path)

            handler.send_json_response({
                "operation": "extract",
                "extract_dir": target_dir,
                "extracted_files": len(zipf.namelist())
            })
            
        except Exception as e:
            handler.send_json_response({"error": f"Extraction failed: {str(e)}"}, 500)
    
    # ==================== 统计和健康检查API ====================
    
    def api_get_stats(self, handler):
        """API: 获取统计信息"""
        total_files = 0
        total_dirs = 0
        total_size = 0
        file_types = {}
        total_downloads = 0

        # 获取 base_dir，添加默认值处理
        base_dir = self.config.get('base_dir', './downloads')
        for root, dirs, files in os.walk(base_dir):
            total_dirs += len(dirs)
            total_files += len(files)
            for filename in files:
                try:
                    file_path = os.path.join(root, filename)
                    size = os.path.getsize(file_path)
                    total_size += size
                    mime_type, _ = mimetypes.guess_type(file_path)
                    if mime_type is None:
                        mime_type = "application/octet-stream"
                    file_types[mime_type] = file_types.get(mime_type, 0) + 1
                except OSError:
                    continue

        if self.config.get('enable_stats', True):
            stats = handler.load_stats()
            file_stats_downloads = sum(stats.values())

            # 计算今日和本周下载 - 从数据库获取准确数据
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

            downloads_today = 0
            downloads_week = 0
            total_downloads = 0

            # 尝试从数据库获取准确统计 - 使用 self.db
            try:
                from core.database import DownloadRecord
                db = self.db
                if db and db.engine:
                    with db.session() as session:
                        from sqlalchemy import func
                        # 累计下载次数
                        total_downloads = session.query(func.count(DownloadRecord.id)).filter(
                            DownloadRecord.success == True
                        ).scalar() or 0

                        # 今日下载次数
                        downloads_today = session.query(func.count(DownloadRecord.id)).filter(
                            DownloadRecord.download_time >= today_start,
                            DownloadRecord.success == True
                        ).scalar() or 0

                        # 本周下载次数
                        downloads_week = session.query(func.count(DownloadRecord.id)).filter(
                            DownloadRecord.download_time >= week_start,
                            DownloadRecord.success == True
                        ).scalar() or 0
                else:
                    # 回退到使用文件统计
                    total_downloads = file_stats_downloads
                    downloads_today = file_stats_downloads
                    downloads_week = file_stats_downloads
            except Exception:
                # 回退到使用文件统计
                total_downloads = file_stats_downloads
                downloads_today = file_stats_downloads
                downloads_week = file_stats_downloads

        sorted_file_types = dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True))

        handler.send_json_response({
            "total_files": total_files,
            "total_dirs": total_dirs,
            "total_size": total_size,
            "total_size_formatted": format_file_size(total_size),
            "file_types": sorted_file_types,
            "total_downloads": total_downloads,
            "downloads_today": downloads_today,
            "downloads_week": downloads_week,
            "updated": datetime.now().isoformat()
        })
    
    def api_health_check(self, handler):
        """API: 健康检查"""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(self.config['base_dir'])

            uptime = time.time() - self.config.get('start_time', time.time())

            total_files = 0
            total_size = 0
            for root, dirs, files in os.walk(self.config['base_dir']):
                total_files += len(files)
                for f in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass

            health_info = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "server": {
                    "uptime": round(uptime, 2),
                    "base_dir": self.config['base_dir'],
                    "port": self.config.get('port', 8080)
                },
                "system": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available": format_file_size(memory.available),
                    "disk_percent": disk.percent,
                    "disk_free": format_file_size(disk.free)
                },
                "files": {
                    "total": total_files,
                    "total_size": format_file_size(total_size),
                    "downloads": handler.get_total_downloads()
                }
            }
            handler.send_json_response(health_info)
        except ImportError:
            handler.send_json_response({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "message": "psutil not installed, limited system info"
            })
    
    def api_get_config(self, handler):
        """API: 获取配置信息"""
        handler.send_json_response({
            "server_name": self.config.get("server_name", "Mirror Server"),
            "version": "2.2",
            "base_dir": self.config['base_dir'],
            "directory_listing": self.config.get('directory_listing', True),
            "max_upload_size": self.config.get('max_upload_size'),
            "enable_stats": self.config.get('enable_stats', True),
            "auth_type": self.config.get('auth_type', 'none'),
            "sort_by": self.config.get('sort_by', 'name'),
            "sort_reverse": self.config.get('sort_reverse', False),
            "ignore_hidden": self.config.get('ignore_hidden', True),
            "enable_range": self.config.get('enable_range', True),
            "show_hash": self.config.get('show_hash', False),
            "calculate_hash": self.config.get('calculate_hash', False),
            "max_search_results": self.config.get('max_search_results', 100),
            "api_version": "v1"
        })
    
    # ==================== MC API ====================
    
    def handle_mc_api(self, handler, method, mc_path):
        """处理MC相关的API请求"""

        if mc_path == 'corelist':
            if method == 'GET':
                self.api_mc_corelist(handler)
            else:
                handler.send_error(405)

        elif mc_path.startswith('corelist/'):
            core_name = mc_path[9:]
            if method == 'GET':
                self.api_mc_corelist_single(handler, core_name)
            else:
                handler.send_error(405)

        elif mc_path.startswith('download/'):
            params = mc_path[9:].split('/')
            if method == 'GET':
                self.api_mc_download(handler, params)
            else:
                handler.send_error(405)

        elif mc_path == 'versions':
            if method == 'GET':
                self.api_mc_versions(handler, [])
            else:
                handler.send_error(405)

        elif mc_path.startswith('versions/'):
            core_name = mc_path[9:]
            if method == 'GET':
                self.api_mc_versions(handler, [core_name])
            else:
                handler.send_error(405)

        elif mc_path.startswith('info/'):
            params = mc_path[5:].split('/')
            if method == 'GET':
                self.api_mc_info(handler, params)
            else:
                handler.send_error(405)

        else:
            handler.send_error(404)

    def api_mc_corelist(self, handler):
        """API: 获取所有MC核心的版本列表"""
        mc_dir = os.path.join(self.config['base_dir'], 'MCServerCore')

        if not os.path.exists(mc_dir):
            handler.send_json_response({"corelist": []})
            return

        corelist_data = []

        for core_name in os.listdir(mc_dir):
            core_path = os.path.join(mc_dir, core_name)
            if os.path.isdir(core_path):
                core_info = self.get_mc_core_info(core_name)
                if core_info:
                    corelist_data.append(core_info)

        handler.send_json_response({"corelist": corelist_data})

    def api_mc_corelist_single(self, handler, core_name):
        """API: 获取特定MC核心的版本列表"""
        mc_dir = os.path.join(self.config['base_dir'], 'MCServerCore')
        core_path = os.path.join(mc_dir, core_name)

        if not os.path.exists(core_path) or not os.path.isdir(core_path):
            handler.send_json_response({"error": f"未找到核心: {core_name}"}, 404)
            return

        core_info = self.get_mc_core_info(core_name)
        if core_info:
            handler.send_json_response(core_info)
        else:
            handler.send_json_response({"error": f"无法获取核心信息: {core_name}"}, 500)

    def get_mc_core_info(self, core_name):
        """获取MC核心的详细信息"""
        mc_dir = os.path.join(self.config['base_dir'], 'MCServerCore')
        core_path = os.path.join(mc_dir, core_name)

        if not os.path.exists(core_path):
            return None

        versions = []

        for item in os.listdir(core_path):
            item_path = os.path.join(core_path, item)

            if os.path.isdir(item_path):
                for filename in os.listdir(item_path):
                    if filename.endswith('.jar') and core_name in filename:
                        version = self.extract_version_from_filename(filename, core_name)
                        if version:
                            versions.append(version)
            elif item.endswith('.jar') and core_name in item:
                version = self.extract_version_from_filename(item, core_name)
                if version:
                    versions.append(version)

        versions.sort(key=lambda v: [int(part) if part.isdigit() else part for part in v.split('.')], reverse=True)
        current_version = versions[0] if versions else None

        return {
            "project": core_name,
            "metadata": {
                "current": current_version
            },
            "versions": versions
        }

    def extract_major_version(self, full_version):
        """从完整版本号中提取大版本（如从1.21.1提取1.21）"""
        version_parts = full_version.split('.')
        if len(version_parts) >= 2:
            return '.'.join(version_parts[:2])
        return full_version

    def extract_version_from_filename(self, filename, core_name):
        """从文件名中提取版本号"""
        pattern = f"{core_name}-(.+)\\.jar"
        match = re.search(pattern, filename)
        if match:
            version = match.group(1)
            version = re.sub(r'-[a-zA-Z0-9]+$', '', version)
            return version
        return None

    def api_mc_download(self, handler, params):
        """API: 处理MC核心下载请求"""
        if len(params) < 2:
            handler.send_json_response({"error": "需要提供核心名和版本号"}, 400)
            return

        core_name = params[0]
        full_version = params[1]
        major_version = self.extract_major_version(full_version)

        possible_paths = [
            f"MCServerCore/{core_name}/{major_version}/{core_name}-{full_version}.jar",
            f"MCServerCore/{core_name}/{core_name}-{full_version}.jar",
            f"mc/{core_name}/{major_version}/{core_name}-{full_version}.jar",
            f"mc/{core_name}/{core_name}-{full_version}.jar"
        ]

        file_path = None
        for rel_path in possible_paths:
            full_path = os.path.join(self.config['base_dir'], rel_path)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                file_path = full_path
                break

        if not file_path:
            handler.send_json_response({"error": f"未找到 {core_name} {full_version}"}, 404)
            return

        # 提供文件下载
        handler.serve_file(file_path, f"mc/{core_name}/{core_name}-{full_version}.jar")

    def api_mc_versions(self, handler, params):
        """API: 获取MC核心的所有版本"""
        core_name = params[0] if params else None
        mc_dir = os.path.join(self.config['base_dir'], 'MCServerCore')

        if not os.path.exists(mc_dir):
            handler.send_json_response({"error": "MC核心目录不存在"}, 404)
            return

        versions_data = {}

        for core_item in os.listdir(mc_dir):
            core_path = os.path.join(mc_dir, core_item)
            if not os.path.isdir(core_path):
                continue

            if core_name and core_item != core_name:
                continue

            versions_data[core_item] = {}

            for version_item in os.listdir(core_path):
                version_path = os.path.join(core_path, version_item)
                if os.path.isdir(version_path):
                    versions_data[core_item][version_item] = self.get_mc_versions_in_dir(version_path, core_item)
                elif version_item.endswith('.jar'):
                    version = self.extract_version_from_filename(version_item, core_item)
                    if version:
                        if 'direct' not in versions_data[core_item]:
                            versions_data[core_item]['direct'] = []
                        versions_data[core_item]['direct'].append(version)

        if core_name and core_name not in versions_data:
            handler.send_json_response({"error": f"未找到核心: {core_name}"}, 404)
            return

        handler.send_json_response({
            "core": core_name or "all",
            "versions": versions_data
        })

    def get_mc_versions_in_dir(self, directory, core_name):
        """获取目录中的所有MC版本"""
        versions = []
        for filename in os.listdir(directory):
            if filename.endswith('.jar'):
                version = self.extract_version_from_filename(filename, core_name)
                if version:
                    file_path = os.path.join(directory, filename)
                    versions.append({
                        "version": version,
                        "file_name": filename,
                        "size": os.path.getsize(file_path),
                        "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                    })

        versions.sort(key=lambda x: [int(part) for part in x['version'].split('.')], reverse=True)
        return versions

    def api_mc_info(self, handler, params):
        """API: 获取MC核心的详细信息"""
        if len(params) < 2:
            handler.send_json_response({"error": "需要提供核心名和版本号"}, 400)
            return

        core_name = params[0]
        full_version = params[1]
        major_version = self.extract_major_version(full_version)

        possible_paths = [
            f"MCServerCore/{core_name}/{major_version}/{core_name}-{full_version}.jar",
            f"MCServerCore/{core_name}/{core_name}-{full_version}.jar"
        ]

        file_path = None
        for rel_path in possible_paths:
            full_path = os.path.join(self.config['base_dir'], rel_path)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                file_path = full_path
                break

        if not file_path:
            handler.send_json_response({"error": f"未找到 {core_name} {full_version}"}, 404)
            return

        file_info = {
            "core_name": core_name,
            "version": full_version,
            "major_version": major_version,
            "file_name": os.path.basename(file_path),
            "size": os.path.getsize(file_path),
            "size_formatted": format_file_size(os.path.getsize(file_path)),
            "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
            "sha256": get_file_hash(file_path) if self.config.get('calculate_hash', False) else None,
            "download_url": f"/api/v1/mc/download/{core_name}/{full_version}"
        }

        handler.send_json_response(file_info)

    def _get_dir_size(self, path):
        """递归计算目录大小"""
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.isfile(filepath):
                        total += os.path.getsize(filepath)
        except Exception:
            pass
        return total
    
    # ==================== Mirror API ====================

    def handle_mirror_api(self, handler, method, mirror_path):
        """处理镜像特定的API请求"""

        if mirror_path == 'info':
            if method == 'GET':
                self.api_mirror_info(handler)
            else:
                handler.send_error(405)

        elif mirror_path == 'sources':
            if method == 'GET':
                self.api_get_sync_sources(handler)
            else:
                handler.send_error(405)

        elif mirror_path == 'refresh':
            if method == 'POST':
                self.api_mirror_refresh(handler)
            else:
                handler.send_error(405)

        elif mirror_path == 'status':
            if method == 'GET':
                self.api_mirror_status(handler)
            else:
                handler.send_error(405)

        elif mirror_path == 'speed':
            if method == 'GET':
                self.api_mirror_speed(handler)
            else:
                handler.send_error(405)

        elif mirror_path == 'bandwidth':
            if method == 'GET':
                self.api_mirror_bandwidth(handler)
            else:
                handler.send_error(405)

        else:
            handler.send_error(404)

    def api_mirror_info(self, handler):
        """API: 获取镜像站信息"""
        info = {
            "server_name": self.config.get("server_name", "Mirror Server"),
            "version": "2.1",
            "uptime": time.time() - self.config.get('start_time', time.time()),
            "total_files": sum(1 for _, _, files in os.walk(self.config['base_dir']) for _ in files),
            "total_size": self._get_dir_size(self.config['base_dir']),
            "api_version": "v1"
        }
        handler.send_json_response(info)

    def api_mirror_refresh(self, handler):
        """API: 刷新镜像源"""
        result = {
            "success": True,
            "message": "Mirror refresh initiated"
        }
        handler.send_json_response(result)

    def api_mirror_status(self, handler):
        """API: 获取镜像状态"""
        status = {
            "running": True,
            "active_syncs": 0,
            "completed_syncs": 0,
            "failed_syncs": 0,
            "last_sync": None
        }
        handler.send_json_response(status)

    def api_mirror_speed(self, handler):
        """API: 获取当前同步速度"""
        speed = {
            "upload": 0,
            "download": 0,
            "unit": "KB/s"
        }
        handler.send_json_response(speed)

    def api_mirror_bandwidth(self, handler):
        """API: 获取带宽使用情况"""
        bandwidth = {
            "total": 0,
            "used": 0,
            "percentage": 0
        }
        handler.send_json_response(bandwidth)
