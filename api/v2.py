#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""API v2 版本处理模块 - 增强版本"""

import os
import json
import re
from datetime import datetime

from .v1 import APIv1
from core.utils import format_file_size


class APIv2(APIv1):
    """API v2 - 增强版本，继承v1并添加新功能"""
    
    def __init__(self, config):
        super().__init__(config)
        self.api_version = "v2"
        
    def handle_request(self, handler, method, path, query_params):
        """处理API v2请求"""
        
        # 首先尝试v1的路径
        try:
            return super().handle_request(handler, method, path, query_params)
        except:
            pass
        
        # v2新增的增强功能
        # 增强搜索API
        if path == 'search/enhanced':
            if method == 'GET':
                self.api_search_files_enhanced(handler, query_params)
            else:
                handler.send_error(405)
        elif path == 'search/by-tag':
            if method == 'GET':
                self.api_search_by_tag(handler, query_params)
            else:
                handler.send_error(405)
        elif path == 'search/by-date':
            if method == 'GET':
                self.api_search_by_date(handler, query_params)
            else:
                handler.send_error(405)
        
        # 增强统计API
        elif path == 'stats/detailed':
            if method == 'GET':
                self.api_get_stats_detailed(handler)
            else:
                handler.send_error(405)
        elif path == 'stats/trending':
            if method == 'GET':
                self.api_get_trending_files(handler, query_params)
            else:
                handler.send_error(405)
        
        # 增强文件操作API
        elif path.startswith('file/') and path.endswith('/metadata'):
            filename = path[5:-9]  # 移除 'file/' 和 '/metadata'
            if method == 'GET':
                self.api_get_file_metadata(handler, filename)
            elif method == 'PUT':
                self.api_update_file_metadata(handler, filename)
            else:
                handler.send_error(405)
        
        # 批量元数据操作
        elif path == 'metadata/batch':
            if method == 'GET':
                self.api_get_batch_metadata(handler, query_params)
            elif method == 'PUT':
                self.api_update_batch_metadata(handler)
            else:
                handler.send_error(405)
        
        # 文件版本控制
        elif path.startswith('file/') and '/versions' in path:
            parts = path.split('/')
            if len(parts) >= 3 and parts[-1] == 'versions':
                filename = '/'.join(parts[1:-1])
                if method == 'GET':
                    self.api_get_file_versions(handler, filename)
                elif method == 'POST':
                    self.api_create_file_version(handler, filename)
                else:
                    handler.send_error(405)
        
        # 缩略图API
        elif path.startswith('file/') and path.endswith('/thumbnail'):
            filename = path[5:-10]  # 移除 'file/' 和 '/thumbnail'
            if method == 'GET':
                self.api_get_file_thumbnail(handler, filename, query_params)
            else:
                handler.send_error(405)
        
        # 服务器监控
        elif path == 'monitor/realtime':
            if method == 'GET':
                self.api_get_realtime_stats(handler)
            else:
                handler.send_error(405)
        elif path == 'monitor/history':
            if method == 'GET':
                self.api_get_monitor_history(handler, query_params)
            else:
                handler.send_error(405)
        
        # Webhook支持
        elif path == 'webhooks':
            if method == 'GET':
                self.api_list_webhooks(handler)
            elif method == 'POST':
                self.api_create_webhook(handler)
            else:
                handler.send_error(405)
        elif path.startswith('webhooks/'):
            webhook_id = path[9:]
            if method == 'GET':
                self.api_get_webhook(handler, webhook_id)
            elif method == 'DELETE':
                self.api_delete_webhook(handler, webhook_id)
            elif method == 'POST':
                self.api_test_webhook(handler, webhook_id)
            else:
                handler.send_error(405)
        
        else:
            handler.send_error(404)
    
    # ==================== 增强搜索API ====================
    
    def api_search_files_enhanced(self, handler, query_params):
        """增强的文件搜索 - 支持更多选项"""
        search_term = query_params.get('q', [''])[0].lower()
        search_type = query_params.get('type', ['all'])[0]
        search_mode = query_params.get('mode', ['fuzzy'])[0]  # fuzzy, exact, regex
        max_results = int(query_params.get('limit', ['100'])[0])
        offset = int(query_params.get('offset', ['0'])[0])
        include_content = query_params.get('include_content', ['false'])[0].lower() == 'true'
        
        if not search_term:
            handler.send_json_response({"error": "No search term provided"}, 400)
            return
        
        results = []
        search_time = 0
        import time as time_module
        start_time = time_module.time()
        
        for root, dirs, files in os.walk(self.config['base_dir']):
            if search_type in ['all', 'dir']:
                for dir_name in dirs:
                    match = False
                    if search_mode == 'exact':
                        match = search_term == dir_name.lower()
                    elif search_mode == 'regex':
                        try:
                            match = re.search(search_term, dir_name.lower()) is not None
                        except re.error:
                            match = False
                    else:  # fuzzy
                        match = search_term in dir_name.lower()
                    
                    if match:
                        full_path = os.path.join(root, dir_name)
                        rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                        try:
                            mtime = os.path.getmtime(full_path)
                            result = {
                                "name": dir_name,
                                "path": rel_path + "/",
                                "type": "directory",
                                "size": 0,
                                "modified": datetime.fromtimestamp(mtime).isoformat(),
                                "match_score": self._calculate_match_score(dir_name, search_term, search_mode)
                            }
                            if include_content:
                                result['item_count'] = len(os.listdir(full_path))
                            results.append(result)
                        except OSError:
                            continue
            
            if search_type in ['all', 'file']:
                for file_name in files:
                    match = False
                    if search_mode == 'exact':
                        match = search_term == file_name.lower()
                    elif search_mode == 'regex':
                        try:
                            match = re.search(search_term, file_name.lower()) is not None
                        except re.error:
                            match = False
                    else:  # fuzzy
                        match = search_term in file_name.lower()
                    
                    if match:
                        full_path = os.path.join(root, file_name)
                        rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                        try:
                            size = os.path.getsize(full_path)
                            mtime = os.path.getmtime(full_path)
                            mime_type, _ = os.path.splitext(file_name)
                            mime_type = mime_type[1:].lower() if mime_type else 'unknown'
                            
                            result = {
                                "name": file_name,
                                "path": rel_path,
                                "type": mime_type,
                                "size": size,
                                "size_formatted": self.format_file_size(size),
                                "modified": datetime.fromtimestamp(mtime).isoformat(),
                                "match_score": self._calculate_match_score(file_name, search_term, search_mode)
                            }
                            
                            if include_content:
                                if mime_type in ['txt', 'log', 'md', 'json', 'xml', 'html']:
                                    try:
                                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                            content = f.read(5000)
                                            result['content_preview'] = content
                                    except:
                                        pass
                            
                            results.append(result)
                        except OSError:
                            continue
            
            if len(results) >= max_results + offset:
                break
        
        search_time = time_module.time() - start_time
        
        # 按匹配分数排序
        results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        
        paginated_results = results[offset:offset + max_results]
        
        handler.send_json_response({
            "query": search_term,
            "search_type": search_type,
            "search_mode": search_mode,
            "total_count": len(results),
            "returned_count": len(paginated_results),
            "offset": offset,
            "limit": max_results,
            "search_time": round(search_time, 3),
            "results": paginated_results
        })
    
    def api_search_by_tag(self, handler, query_params):
        """按标签搜索文件"""
        tag = query_params.get('tag', [''])[0]
        if not tag:
            handler.send_json_response({"error": "No tag specified"}, 400)
            return
        
        # 这里假设有一个标签存储系统
        # 实际实现需要维护文件标签数据库
        results = []
        handler.send_json_response({
            "tag": tag,
            "total_count": 0,
            "results": results
        })
    
    def api_search_by_date(self, handler, query_params):
        """按日期范围搜索文件"""
        start_date = query_params.get('start', [''])[0]
        end_date = query_params.get('end', [''])[0]
        search_type = query_params.get('type', ['all'])[0]
        
        if not start_date:
            handler.send_json_response({"error": "Start date required"}, 400)
            return
        
        try:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date) if end_date else datetime.now()
        except ValueError:
            handler.send_json_response({"error": "Invalid date format"}, 400)
            return
        
        results = []
        
        for root, dirs, files in os.walk(self.config['base_dir']):
            if search_type in ['all', 'dir']:
                for dir_name in dirs:
                    full_path = os.path.join(root, dir_name)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
                        if start_dt <= mtime <= end_dt:
                            rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                            results.append({
                                "name": dir_name,
                                "path": rel_path + "/",
                                "type": "directory",
                                "modified": mtime.isoformat()
                            })
                    except OSError:
                        continue
            
            if search_type in ['all', 'file']:
                for file_name in files:
                    full_path = os.path.join(root, file_name)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
                        if start_dt <= mtime <= end_dt:
                            rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                            results.append({
                                "name": file_name,
                                "path": rel_path,
                                "type": "file",
                                "modified": mtime.isoformat()
                            })
                    except OSError:
                        continue
            
            if len(results) > 1000:
                break
        
        handler.send_json_response({
            "start_date": start_date,
            "end_date": end_date.isoformat(),
            "total_count": len(results),
            "results": results
        })
    
    def _calculate_match_score(self, text, search_term, mode):
        """计算匹配分数"""
        if mode == 'exact':
            return 100 if text.lower() == search_term else 0
        elif mode == 'regex':
            try:
                return 80 if re.search(search_term, text.lower()) else 0
            except:
                return 0
        else:  # fuzzy
            text_lower = text.lower()
            if search_term == text_lower:
                return 100
            elif text_lower.startswith(search_term):
                return 90
            elif text_lower.endswith(search_term):
                return 80
            elif search_term in text_lower:
                return 70
            return 0
    
    # ==================== 增强统计API ====================
    
    def api_get_stats_detailed(self, handler):
        """获取详细统计信息"""
        import mimetypes
        
        total_files = 0
        total_dirs = 0
        total_size = 0
        file_types = {}
        size_distribution = {
            "small": 0,      # < 1MB
            "medium": 0,     # 1MB - 100MB
            "large": 0,      # 100MB - 1GB
            "xlarge": 0      # > 1GB
        }
        oldest_file = None
        newest_file = None
        largest_file = None
        
        for root, dirs, files in os.walk(self.config['base_dir']):
            total_dirs += len(dirs)
            total_files += len(files)
            for filename in files:
                try:
                    file_path = os.path.join(root, filename)
                    size = os.path.getsize(file_path)
                    mtime = os.path.getmtime(file_path)
                    total_size += size
                    
                    mime_type, _ = mimetypes.guess_type(file_path)
                    if mime_type is None:
                        mime_type = "application/octet-stream"
                    file_types[mime_type] = file_types.get(mime_type, 0) + 1
                    
                    # 大小分布
                    if size < 1024 * 1024:
                        size_distribution["small"] += 1
                    elif size < 100 * 1024 * 1024:
                        size_distribution["medium"] += 1
                    elif size < 1024 * 1024 * 1024:
                        size_distribution["large"] += 1
                    else:
                        size_distribution["xlarge"] += 1
                    
                    # 最旧/最新文件
                    if oldest_file is None or mtime < oldest_file[1]:
                        oldest_file = (filename, mtime)
                    if newest_file is None or mtime > newest_file[1]:
                        newest_file = (filename, mtime)
                    
                    # 最大文件
                    if largest_file is None or size > largest_file[1]:
                        largest_file = (filename, size)
                        
                except OSError:
                    continue
        
        handler.send_json_response({
            "summary": {
                "total_files": total_files,
                "total_dirs": total_dirs,
                "total_size": total_size,
                "total_size_formatted": self.format_file_size(total_size)
            },
            "file_types": dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True)),
            "size_distribution": size_distribution,
            "extremes": {
                "oldest_file": {
                    "name": oldest_file[0] if oldest_file else None,
                    "modified": datetime.fromtimestamp(oldest_file[1]).isoformat() if oldest_file else None
                },
                "newest_file": {
                    "name": newest_file[0] if newest_file else None,
                    "modified": datetime.fromtimestamp(newest_file[1]).isoformat() if newest_file else None
                },
                "largest_file": {
                    "name": largest_file[0] if largest_file else None,
                    "size": largest_file[1] if largest_file else None,
                    "size_formatted": self.format_file_size(largest_file[1]) if largest_file else None
                }
            },
            "updated": datetime.now().isoformat()
        })
    
    def api_get_trending_files(self, handler, query_params):
        """获取热门文件（按下载次数）"""
        limit = int(query_params.get('limit', ['20'])[0])
        time_range = query_params.get('range', ['24h'])[0]  # 24h, 7d, 30d
        
        # 获取下载统计
        stats = handler.load_stats()
        
        # 转换为列表并排序
        trending = []
        for filepath, count in stats.items():
            full_path = os.path.join(self.config['base_dir'], filepath)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                try:
                    info = os.stat(full_path)
                    trending.append({
                        "path": filepath,
                        "name": os.path.basename(filepath),
                        "size": info.st_size,
                        "size_formatted": self.format_file_size(info.st_size),
                        "modified": datetime.fromtimestamp(info.st_mtime).isoformat(),
                        "downloads": count
                    })
                except OSError:
                    continue
        
        # 按下载次数排序
        trending.sort(key=lambda x: x['downloads'], reverse=True)
        trending = trending[:limit]
        
        handler.send_json_response({
            "time_range": time_range,
            "limit": limit,
            "trending": trending
        })
    
    # ==================== 文件元数据API ====================
    
    def api_get_file_metadata(self, handler, filename):
        """获取文件元数据"""
        full_path = os.path.join(self.config['base_dir'], filename)
        if not os.path.exists(full_path):
            handler.send_json_response({"error": "File not found"}, 404)
            return
        
        # 这里可以从单独的元数据文件中读取
        metadata_file = full_path + '.meta'
        metadata = {}
        
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except:
                pass
        
        # 添加基本文件信息
        import os
        stat = os.stat(full_path)
        metadata['_file_info'] = {
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
        }
        
        handler.send_json_response(metadata)
    
    def api_update_file_metadata(self, handler, filename):
        """更新文件元数据"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No metadata provided"}, 400)
            return
        
        try:
            metadata = json.loads(handler.rfile.read(content_length))
            full_path = os.path.join(self.config['base_dir'], filename)
            metadata_file = full_path + '.meta'
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            handler.send_json_response({"success": True})
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    def api_get_batch_metadata(self, handler, query_params):
        """批量获取文件元数据"""
        paths = query_params.get('paths', [])
        if not paths:
            handler.send_json_response({"error": "No file paths provided"}, 400)
            return
        
        results = {}
        for path in paths:
            full_path = os.path.join(self.config['base_dir'], path)
            if os.path.exists(full_path):
                metadata_file = full_path + '.meta'
                metadata = {}
                if os.path.exists(metadata_file):
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    except:
                        pass
                results[path] = metadata
        
        handler.send_json_response(results)
    
    def api_update_batch_metadata(self, handler):
        """批量更新文件元数据"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No data provided"}, 400)
            return
        
        try:
            data = json.loads(handler.rfile.read(content_length))
            results = {}
            
            for path, metadata in data.items():
                full_path = os.path.join(self.config['base_dir'], path)
                metadata_file = full_path + '.meta'
                try:
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, ensure_ascii=False, indent=2)
                    results[path] = {"success": True}
                except Exception as e:
                    results[path] = {"success": False, "error": str(e)}
            
            handler.send_json_response(results)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    # ==================== 文件版本控制API ====================
    
    def api_get_file_versions(self, handler, filename):
        """获取文件版本列表"""
        # 这里可以实现版本控制系统
        # 简化实现：检查备份文件
        full_path = os.path.join(self.config['base_dir'], filename)
        versions = []
        
        # 查找备份文件
        dir_path = os.path.dirname(full_path)
        base_name = os.path.basename(full_path)
        
        if os.path.exists(dir_path):
            for item in os.listdir(dir_path):
                if item.startswith(base_name) and item != base_name:
                    backup_path = os.path.join(dir_path, item)
                    try:
                        stat = os.stat(backup_path)
                        versions.append({
                            "name": item,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
                    except OSError:
                        continue
        
        handler.send_json_response({
            "filename": filename,
            "versions": versions
        })
    
    def api_create_file_version(self, handler, filename):
        """创建文件版本（备份）"""
        import time
        full_path = os.path.join(self.config['base_dir'], filename)
        if not os.path.exists(full_path):
            handler.send_json_response({"error": "File not found"}, 404)
            return
        
        # 创建备份
        timestamp = int(time.time())
        backup_path = f"{full_path}.v{timestamp}"
        
        try:
            import shutil
            shutil.copy2(full_path, backup_path)
            handler.send_json_response({
                "success": True,
                "version": backup_path
            })
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    # ==================== 缩略图API ====================
    
    def api_get_file_thumbnail(self, handler, filename, query_params):
        """获取文件缩略图"""
        import mimetypes
        
        full_path = os.path.join(self.config['base_dir'], filename)
        if not os.path.exists(full_path):
            handler.send_json_response({"error": "File not found"}, 404)
            return
        
        mime_type, _ = mimetypes.guess_type(full_path)
        if not mime_type or not mime_type.startswith('image/'):
            handler.send_json_response({"error": "Not an image file"}, 400)
            return
        
        width = int(query_params.get('width', ['200'])[0])
        height = int(query_params.get('height', ['200'])[0])
        
        try:
            from PIL import Image
            
            with Image.open(full_path) as img:
                img.thumbnail((width, height), Image.LANCZOS)
                
                import io
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                thumbnail_data = buffer.getvalue()
            
            handler.send_response(200)
            handler.send_header("Content-Type", "image/jpeg")
            handler.send_header("Content-Length", str(len(thumbnail_data)))
            handler.send_header("Cache-Control", "public, max-age=86400")
            handler.end_headers()
            handler.wfile.write(thumbnail_data)
            
        except ImportError:
            handler.send_json_response({"error": "PIL/Pillow not installed"}, 500)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    # ==================== 服务器监控API ====================
    
    def api_get_realtime_stats(self, handler):
        """获取实时服务器统计"""
        try:
            import psutil
            handler.send_json_response({
                "timestamp": datetime.now().isoformat(),
                "cpu": {
                    "percent": psutil.cpu_percent(interval=0.1),
                    "count": psutil.cpu_count(),
                    "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
                },
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent,
                    "used": psutil.virtual_memory().used,
                    "free": psutil.virtual_memory().free
                },
                "disk": {
                    "total": psutil.disk_usage(self.config['base_dir']).total,
                    "used": psutil.disk_usage(self.config['base_dir']).used,
                    "free": psutil.disk_usage(self.config['base_dir']).free,
                    "percent": psutil.disk_usage(self.config['base_dir']).percent
                },
                "network": {
                    "connections": len(psutil.net_connections()),
                    "io": psutil.net_io_counters()._asdict() if psutil.net_io_counters() else None
                }
            })
        except ImportError:
            handler.send_json_response({"error": "psutil not installed"}, 500)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    def api_get_monitor_history(self, handler, query_params):
        """获取历史监控数据"""
        # 这里可以从历史文件中读取
        hours = int(query_params.get('hours', ['24'])[0])
        handler.send_json_response({
            "hours": hours,
            "data": []
        })
    
    # ==================== Webhook API ====================
    
    def api_list_webhooks(self, handler):
        """列出所有webhook"""
        # 这里可以从配置或数据库中读取
        handler.send_json_response({
            "webhooks": []
        })
    
    def api_create_webhook(self, handler):
        """创建webhook"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No webhook data provided"}, 400)
            return
        
        try:
            webhook_data = json.loads(handler.rfile.read(content_length))
            # 这里保存webhook配置
            handler.send_json_response({
                "success": True,
                "webhook": webhook_data
            })
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    def api_get_webhook(self, handler, webhook_id):
        """获取webhook详情"""
        handler.send_json_response({
            "webhook_id": webhook_id,
            "error": "Webhook not found"
        }, 404)
    
    def api_delete_webhook(self, handler, webhook_id):
        """删除webhook"""
        handler.send_json_response({
            "success": True,
            "webhook_id": webhook_id
        })
    
    def api_test_webhook(self, handler, webhook_id):
        """测试webhook"""
        handler.send_json_response({
            "success": True,
            "webhook_id": webhook_id,
            "test_result": "Webhook test triggered"
        })
