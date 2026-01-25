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
from datetime import datetime
from urllib.parse import parse_qs

from core.utils import format_file_size, get_file_hash, sanitize_filename, is_safe_path


class APIv1:
    """API v1 - 基础功能实现"""
    
    def __init__(self, config):
        self.config = config
        
    def handle_request(self, handler, method, path, query_params):
        """处理API v1请求"""
        
        # 文件管理API
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
        """API: 列出所有文件"""
        recursive = query_params.get('recursive', ['false'])[0].lower() == 'true'
        
        files = []
    
        for root, dirs, filenames in os.walk(self.config['base_dir']):
            for filename in filenames:
                file_path = os.path.relpath(os.path.join(root, filename), self.config['base_dir']).replace("\\", "/")
                full_path = os.path.join(self.config['base_dir'], file_path)
    
                if self.config.get('ignore_hidden', True) and any(part.startswith('.') for part in file_path.split(os.sep)):
                    continue
    
                try:
                    size = os.path.getsize(full_path)
                    mtime = os.path.getmtime(full_path)
                    mime_type, _ = mimetypes.guess_type(full_path)
                    if mime_type is None:
                        mime_type = "application/octet-stream"
    
                    download_count = 0
                    if self.config.get('enable_stats', True):
                        download_count = handler.get_download_count(file_path)
    
                    files.append({
                        "name": filename,
                        "path": file_path,
                        "size": size,
                        "size_formatted": format_file_size(size),
                        "type": mime_type,
                        "modified": datetime.fromtimestamp(mtime).isoformat(),
                        "download_count": download_count,
                        "sha256": get_file_hash(full_path) if self.config.get('calculate_hash', False) else None
                    })
                except OSError:
                    continue
    
            if not recursive:
                break

        # 排序
        sort_by = handler.headers.get('X-Sort-By', self.config.get('sort_by', 'name'))
        reverse = handler.headers.get('X-Sort-Reverse', str(self.config.get('sort_reverse', False))).lower() == 'true'

        if sort_by == 'name':
            files.sort(key=lambda x: x['name'].lower(), reverse=reverse)
        elif sort_by == 'size':
            files.sort(key=lambda x: x['size'], reverse=reverse)
        elif sort_by == 'modified':
            files.sort(key=lambda x: x['modified'], reverse=reverse)
        elif sort_by == 'downloads':
            files.sort(key=lambda x: x.get('download_count', 0), reverse=reverse)

        # 分页
        try:
            page = int(handler.headers.get('X-Page', 1))
            per_page = int(handler.headers.get('X-Per-Page', 50))
        except ValueError:
            page = 1
            per_page = 50

        total = len(files)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_files = files[start:end]

        handler.send_json_response({
            "files": paginated_files,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
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
        full_path = os.path.join(self.config['base_dir'], file_path)
        
        if not is_safe_path(self.config['base_dir'], full_path) or not os.path.isfile(full_path):
            handler.send_json_response({"error": "File not found or access denied"}, 404)
            return
            
        max_preview_size = self.config.get('max_preview_size', 10 * 1024 * 1024)
        file_size = os.path.getsize(full_path)
        
        if file_size > max_preview_size:
            handler.send_json_response({
                "error": f"File too large for preview (max {format_file_size(max_preview_size)})",
                "file_size": file_size,
                "max_preview_size": max_preview_size
            }, 413)
            return
            
        mime_type, _ = mimetypes.guess_type(full_path)
        
        preview_data = {
            "path": file_path,
            "name": os.path.basename(file_path),
            "size": file_size,
            "type": mime_type or "application/octet-stream",
            "preview_available": False
        }
    
        try:
            if mime_type and mime_type.startswith('text/'):
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(5000)
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "text",
                        "content": content,
                        "truncated": len(content) == 5000
                    })
                    
            elif mime_type and mime_type.startswith('image/'):
                with open(full_path, 'rb') as f:
                    image_data = f.read(1024 * 1024)
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                    preview_data.update({
                        "preview_available": True,
                        "preview_type": "image",
                        "data_url": f"data:{mime_type};base64,{base64_data}",
                        "truncated": file_size > 1024 * 1024
                    })
                    
            elif mime_type == 'application/json' or file_path.endswith('.json'):
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
        try:
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.unlink(full_path)
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
        sources = handler.sync_manager.sync_sources
        handler.send_json_response({"sources": sources, "count": len(sources)})

    def api_get_sync_status(self, handler):
        """获取同步状态"""
        status = handler.sync_manager.get_sync_status()
        handler.send_json_response(status)

    def api_add_sync_source(self, handler):
        """添加同步源"""
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
                
            handler.sync_manager.add_sync_source(name, config)
            handler.send_json_response({"success": True, "name": name})
            
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 400)

    def api_remove_sync_source(self, handler, name):
        """移除同步源"""
        if not name:
            handler.send_json_response({"error": "未指定同步源名称"}, 400)
            return
        handler.sync_manager.remove_sync_source(name)
        handler.send_json_response({"success": True})

    def api_start_sync(self, handler):
        """开始同步"""
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
                        else:
                            shutil.copy2(full_path, target_path)
                        
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

        for root, dirs, files in os.walk(self.config['base_dir']):
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
            for count in stats.values():
                total_downloads += count

        sorted_file_types = dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True))

        handler.send_json_response({
            "total_files": total_files,
            "total_dirs": total_dirs,
            "total_size": total_size,
            "total_size_formatted": format_file_size(total_size),
            "file_types": sorted_file_types,
            "total_downloads": total_downloads,
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
            "version": "2.0",
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

        elif mc_path == 'server':
            if method == 'GET':
                self.api_mc_server_info(handler)
            elif method == 'POST':
                self.api_mc_server_action(handler)
            else:
                handler.send_error(405)

        elif mc_path == 'players':
            if method == 'GET':
                self.api_mc_players(handler)
            else:
                handler.send_error(405)

        elif mc_path.startswith('player/'):
            player_name = mc_path[7:]
            if method == 'GET':
                self.api_mc_player_info(handler, player_name)
            elif method == 'DELETE':
                self.api_mc_kick_player(handler, player_name)
            else:
                handler.send_error(405)

        elif mc_path == 'mods':
            if method == 'GET':
                self.api_mc_mods(handler)
            elif method == 'POST':
                self.api_mc_upload_mod(handler)
            else:
                handler.send_error(405)

        elif mc_path.startswith('mod/'):
            mod_path = mc_path[4:]
            if method == 'DELETE':
                self.api_mc_delete_mod(handler, mod_path)
            else:
                handler.send_error(405)

        elif mc_path == 'world':
            if method == 'GET':
                self.api_mc_world_info(handler)
            elif method == 'POST':
                self.api_mc_world_backup(handler)
            else:
                handler.send_error(405)

        elif mc_path == 'config':
            if method == 'GET':
                self.api_mc_config(handler)
            elif method == 'PUT':
                self.api_mc_update_config(handler)
            else:
                handler.send_error(405)

        elif mc_path == 'logs':
            if method == 'GET':
                self.api_mc_logs(handler)
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

    def api_mc_server_info(self, handler):
        """API: 获取MC服务器信息"""
        mc_dir = os.path.join(self.config['base_dir'], 'minecraft')
        servers = []

        if os.path.exists(mc_dir):
            for item in os.listdir(mc_dir):
                server_path = os.path.join(mc_dir, item)
                if os.path.isdir(server_path):
                    # 检查是否有 server.properties
                    props_file = os.path.join(server_path, 'server.properties')
                    server_name = item
                    version = "Unknown"

                    if os.path.exists(props_file):
                        try:
                            with open(props_file, 'r', encoding='utf-8', errors='ignore') as f:
                                for line in f:
                                    line = line.strip()
                                    if line.startswith('server-name='):
                                        server_name = line.split('=', 1)[1].strip()
                                    elif line.startswith('version='):
                                        version = line.split('=', 1)[1].strip()
                        except Exception:
                            pass

                    servers.append({
                        "name": server_name,
                        "path": item,
                        "version": version,
                        "size": self._get_dir_size(server_path),
                        "status": "offline"
                    })

        handler.send_json_response({
            "count": len(servers),
            "servers": servers
        })

    def api_mc_server_action(self, handler):
        """API: 执行MC服务器操作（启动/停止/重启）"""
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            data = json.loads(handler.rfile.read(content_length).decode('utf-8'))
            action = data.get('action', 'start')

            result = {
                "success": True,
                "action": action,
                "message": f"Server {action} command sent"
            }
            handler.send_json_response(result)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def api_mc_players(self, handler):
        """API: 获取在线玩家列表"""
        players = {
            "online": [],
            "max": 20,
            "count": 0
        }
        handler.send_json_response(players)

    def api_mc_player_info(self, handler, player_name):
        """API: 获取玩家信息"""
        player_info = {
            "name": player_name,
            "online": False,
            "first_seen": None,
            "last_seen": None,
            "play_time": 0
        }
        handler.send_json_response(player_info)

    def api_mc_kick_player(self, handler, player_name):
        """API: 踢出玩家"""
        result = {
            "success": True,
            "message": f"Player {player_name} kicked"
        }
        handler.send_json_response(result)

    def api_mc_mods(self, handler):
        """API: 获取已安装的模组列表"""
        mc_dir = os.path.join(self.config['base_dir'], 'minecraft')
        all_mods = {}

        if os.path.exists(mc_dir):
            for server_name in os.listdir(mc_dir):
                server_path = os.path.join(mc_dir, server_name)
                if os.path.isdir(server_path):
                    mods_dir = os.path.join(server_path, 'mods')
                    if os.path.exists(mods_dir):
                        mods = []
                        for file in os.listdir(mods_dir):
                            if file.endswith('.jar'):
                                mod_path = os.path.join(mods_dir, file)
                                mods.append({
                                    "name": file,
                                    "size": os.path.getsize(mod_path),
                                    "enabled": True
                                })
                        all_mods[server_name] = mods

        handler.send_json_response(all_mods)

    def api_mc_upload_mod(self, handler):
        """API: 上传模组到指定服务器"""
        content_type = handler.headers.get('Content-Type', '')
        if 'multipart/form-data' in content_type:
            content_length = int(handler.headers.get('Content-Length', 0))
            form_data = cgi.FieldStorage(
                fp=handler.rfile,
                headers=handler.headers,
                environ={'REQUEST_METHOD': 'POST',
                         'CONTENT_TYPE': content_type}
            )

            # 获取服务器名称
            server_name = form_data.getvalue('server', 'default')
            mc_dir = os.path.join(self.config['base_dir'], 'minecraft')
            mods_dir = os.path.join(mc_dir, server_name, 'mods')

            if not os.path.exists(mods_dir):
                os.makedirs(mods_dir, exist_ok=True)

            for key in form_data.keys():
                item = form_data[key]
                if key == 'file' and item.filename:
                    filename = sanitize_filename(item.filename)
                    filepath = os.path.join(mods_dir, filename)
                    with open(filepath, 'wb') as f:
                        f.write(item.file.read())

                    handler.send_json_response({
                        "success": True,
                        "server": server_name,
                        "filename": filename,
                        "size": os.path.getsize(filepath)
                    })
                    return

        handler.send_json_response({"error": "No file uploaded"}, 400)

    def api_mc_delete_mod(self, handler, mod_path):
        """API: 删除模组 (路径格式: server_name/mod_name)"""
        parts = mod_path.split('/', 1)
        if len(parts) != 2:
            handler.send_json_response({"error": "Invalid path format. Use: server_name/mod_name"}, 400)
            return

        server_name, mod_name = parts
        mc_dir = os.path.join(self.config['base_dir'], 'minecraft')
        mods_dir = os.path.join(mc_dir, server_name, 'mods')
        mod_file = os.path.join(mods_dir, mod_name)

        if os.path.exists(mod_file) and is_safe_path(self.config['base_dir'], mod_file):
            os.remove(mod_file)
            handler.send_json_response({
                "success": True,
                "server": server_name,
                "mod": mod_name,
                "message": f"Mod {mod_name} deleted from {server_name}"
            })
        else:
            handler.send_json_response({"error": "Mod not found"}, 404)

    def api_mc_world_info(self, handler):
        """API: 获取世界信息"""
        mc_dir = os.path.join(self.config['base_dir'], 'minecraft')
        all_worlds = {}

        if os.path.exists(mc_dir):
            for server_name in os.listdir(mc_dir):
                server_path = os.path.join(mc_dir, server_name)
                if os.path.isdir(server_path):
                    worlds = []
                    for item in os.listdir(server_path):
                        item_path = os.path.join(server_path, item)
                        if os.path.isdir(item_path) and 'world' in item:
                            worlds.append({
                                "name": item,
                                "size": self._get_dir_size(item_path),
                                "last_modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat()
                            })
                    all_worlds[server_name] = worlds

        handler.send_json_response(all_worlds)

    def api_mc_world_backup(self, handler):
        """API: 创建世界备份"""
        backup_dir = os.path.join(self.config['base_dir'], 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"world_backup_{timestamp}"

        handler.send_json_response({
            "success": True,
            "backup_name": backup_name,
            "message": "World backup initiated"
        })

    def api_mc_config(self, handler):
        """API: 获取服务器配置"""
        mc_dir = os.path.join(self.config['base_dir'], 'minecraft')
        all_configs = {}

        if os.path.exists(mc_dir):
            for server_name in os.listdir(mc_dir):
                server_path = os.path.join(mc_dir, server_name)
                if os.path.isdir(server_path):
                    config_file = os.path.join(server_path, 'server.properties')
                    config = {}

                    if os.path.exists(config_file):
                        with open(config_file, 'r', encoding='utf-8', errors='ignore') as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    if '=' in line:
                                        key, value = line.split('=', 1)
                                        config[key.strip()] = value.strip()

                    all_configs[server_name] = config

        handler.send_json_response(all_configs)

    def api_mc_update_config(self, handler):
        """API: 更新服务器配置"""
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            data = json.loads(handler.rfile.read(content_length).decode('utf-8'))

            config_file = os.path.join(self.config['base_dir'], 'server.properties')
            lines = []

            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

            with open(config_file, 'w', encoding='utf-8') as f:
                for key, value in data.items():
                    lines.append(f"{key}={value}\n")
                f.writelines(lines)

            handler.send_json_response({
                "success": True,
                "message": "Config updated"
            })
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def api_mc_logs(self, handler):
        """API: 获取服务器日志"""
        mc_dir = os.path.join(self.config['base_dir'], 'minecraft')
        all_logs = {}

        if os.path.exists(mc_dir):
            for server_name in os.listdir(mc_dir):
                server_path = os.path.join(mc_dir, server_name)
                if os.path.isdir(server_path):
                    logs_dir = os.path.join(server_path, 'logs')
                    logs = []

                    if os.path.exists(logs_dir):
                        log_file = os.path.join(logs_dir, 'latest.log')
                        if os.path.exists(log_file):
                            try:
                                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                                    lines = f.readlines()
                                    logs = [line.strip() for line in lines[-100:]]  # 最后100行
                            except Exception:
                                pass

                    all_logs[server_name] = logs

        handler.send_json_response(all_logs)

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
