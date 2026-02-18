#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
同步引擎模块 - 重构版镜像同步管理
支持HTTP/HTTPS/FTP/SFTP/本地同步，提供真实进度追踪和断点续传
"""

import os
import json
import time
import uuid
import shutil
import threading
import ftplib
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

try:
    import paramiko
except ImportError:
    paramiko = None


class SyncStatus(Enum):
    """同步状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPING = "stopping"


class SyncEngine:
    """同步引擎 - 管理所有镜像同步任务"""

    def __init__(self, config: dict):
        self.config = config
        self.base_dir = config.get('base_dir', './downloads')

        # 同步源配置
        self.sources: Dict[str, SyncSource] = {}

        # 活跃任务
        self.active_tasks: Dict[str, SyncTask] = {}

        # 任务锁
        self.task_lock = threading.Lock()

        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=5)

        # 状态文件
        self.state_file = 'sync_state.json'
        self.history_file = 'sync_history.json'

        # 加载配置
        self._load_sources()
        self._load_history()

    # === 同步源管理 ===

    def add_source(self, name: str, source_config: dict) -> bool:
        """添加同步源"""
        if not self._validate_source_config(source_config):
            return False

        source = SyncSource(name, source_config)
        self.sources[name] = source
        self._save_sources()

        # 更新状态
        self._init_source_status(name)

        return True

    def remove_source(self, name: str) -> bool:
        """移除同步源"""
        if name not in self.sources:
            return False

        # 停止正在运行的任务
        self.stop_all_tasks_for_source(name)

        del self.sources[name]
        self._save_sources()
        return True

    def update_source(self, name: str, source_config: dict) -> bool:
        """更新同步源配置"""
        if name not in self.sources:
            return False

        if not self._validate_source_config(source_config):
            return False

        self.sources[name].update_config(source_config)
        self._save_sources()
        return True

    def get_sources(self) -> dict:
        """获取所有同步源"""
        result = {}
        for name, source in self.sources.items():
            result[name] = source.to_dict()
        return result

    def get_source(self, name: str) -> Optional[dict]:
        """获取单个同步源"""
        if name not in self.sources:
            return None
        return self.sources[name].to_dict()

    def enable_source(self, name: str, enabled: bool = True) -> bool:
        """启用/禁用同步源"""
        if name not in self.sources:
            return False
        self.sources[name].enabled = enabled
        self._save_sources()
        return True

    # === 同步任务操作 ===

    def start_sync(self, name: str) -> Optional[str]:
        """启动同步任务，返回任务ID"""
        if name not in self.sources:
            return None

        source = self.sources[name]
        if not source.enabled:
            return None

        # 检查是否已有运行中的任务
        for task_id, task in list(self.active_tasks.items()):
            if task.source_name == name and task.status == SyncStatus.RUNNING:
                return task.task_id

        # 创建新任务
        task_id = str(uuid.uuid4())[:8]
        task = SyncTask(task_id, name)
        task.source_config = source.to_dict()

        with self.task_lock:
            self.active_tasks[task_id] = task

        # 在后台线程执行
        self.executor.submit(self._sync_worker, task_id, name)

        return task_id

    def stop_sync(self, task_id: str) -> bool:
        """停止同步任务"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        task.status = SyncStatus.STOPPING
        return True

    def pause_sync(self, task_id: str) -> bool:
        """暂停同步任务"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        if task.status != SyncStatus.RUNNING:
            return False

        task.status = SyncStatus.PAUSED
        task.paused_position = {
            'current_file': task.current_file,
            'file_progress': task.file_progress
        }
        return True

    def resume_sync(self, task_id: str) -> bool:
        """恢复同步任务"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        if task.status != SyncStatus.PAUSED:
            return False

        task.status = SyncStatus.RUNNING
        task.paused_position = None

        # 重新提交任务
        self.executor.submit(self._sync_worker, task_id, task.source_name)

        return True

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        if task_id not in self.active_tasks:
            return None
        return self.active_tasks[task_id].to_dict()

    def get_all_task_status(self) -> List[dict]:
        """获取所有任务状态"""
        with self.task_lock:
            return [task.to_dict() for task in self.active_tasks.values()]

    def get_source_status(self, name: str) -> dict:
        """获取同步源整体状态"""
        if name not in self.sources:
            return {'error': 'source_not_found'}

        source = self.sources[name]

        # 查找相关任务
        related_tasks = [
            task for task in self.active_tasks.values()
            if task.source_name == name
        ]

        active_task = None
        for task in related_tasks:
            if task.status == SyncStatus.RUNNING:
                active_task = task
                break

        # 获取最后同步信息
        history = self._get_source_history(name, limit=1)

        return {
            'name': name,
            'enabled': source.enabled,
            'type': source.type,
            'target': source.target,
            'url': source.url,
            'active_task': active_task.to_dict() if active_task else None,
            'last_sync': history[0] if history else None,
            'total_synced_files': self._get_source_total_synced(name),
            'total_size': self._get_source_total_size(name)
        }

    def get_sync_history(self, source_name: str = None, limit: int = 100) -> List[dict]:
        """获取同步历史"""
        return self._get_source_history(source_name, limit)

    # === 内部方法 ===

    def _sync_worker(self, task_id: str, source_name: str):
        """同步工作线程"""
        task = self.active_tasks.get(task_id)
        if not task:
            return

        source = self.sources.get(source_name)
        if not source:
            task.status = SyncStatus.FAILED
            task.error = f"Source not found: {source_name}"
            return

        task.status = SyncStatus.RUNNING
        task.started = datetime.now().isoformat()
        task.updated = task.started

        try:
            # 根据类型执行同步
            if source.type in ['http', 'https']:
                self._sync_http(task, source)
            elif source.type == 'ftp':
                self._sync_ftp(task, source)
            elif source.type == 'sftp':
                self._sync_sftp(task, source)
            elif source.type == 'local':
                self._sync_local(task, source)
            else:
                raise ValueError(f"Unsupported sync type: {source.type}")

            # 同步完成
            task.status = SyncStatus.COMPLETED
            task.progress = 100.0
            task.updated = datetime.now().isoformat()

            # 记录历史
            self._add_history_entry(task, success=True)

        except Exception as e:
            task.status = SyncStatus.FAILED
            task.error = str(e)
            task.updated = datetime.now().isoformat()

            # 记录历史
            self._add_history_entry(task, success=False)

        finally:
            # 清理已完成的任务（保留状态信息）
            if task.status in [SyncStatus.COMPLETED, SyncStatus.FAILED]:
                # 延迟清理，让客户端有时间获取状态
                pass

    def _sync_http(self, task: SyncTask, source: SyncSource):
        """HTTP同步实现"""
        import urllib.request
        import base64

        target_dir = os.path.join(self.base_dir, source.target)
        os.makedirs(target_dir, exist_ok=True)

        # 获取文件列表
        file_list = self._get_http_file_list(source)
        task.total_files = len(file_list)

        for i, file_info in enumerate(file_list):
            if task.status == SyncStatus.STOPPING:
                task.status = SyncStatus.CANCELLED
                return

            if task.status == SyncStatus.PAUSED:
                # 暂停
                return

            task.current_file = file_info['name']
            task.file_progress = 0

            local_path = os.path.join(target_dir, file_info['name'])

            # 检查是否需要同步
            if not self._need_sync_file(local_path, file_info):
                task.synced_files += 1
                task.synced_size += file_info.get('size', 0)
                continue

            # 下载文件
            success = self._download_http_file(source, file_info, local_path, task)

            if success:
                task.synced_files += 1
                task.synced_size += file_info.get('size', 0)

            # 更新进度
            task.progress = (task.synced_files / task.total_files) * 100 if task.total_files > 0 else 0
            task.file_progress = 100
            task.updated = datetime.now().isoformat()

    def _sync_ftp(self, task: SyncTask, source: SyncSource):
        """FTP同步实现"""
        config = source.config

        host = config.get('host', '')
        port = config.get('port', 21)
        username = config.get('username', 'anonymous')
        password = config.get('password', 'anonymous@')
        remote_path = config.get('remote_path', '/')

        target_dir = os.path.join(self.base_dir, source.target)
        os.makedirs(target_dir, exist_ok=True)

        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port)
            ftp.login(username, password)

            if remote_path:
                ftp.cwd(remote_path)

            # 获取文件列表
            file_list = self._get_ftp_file_list(ftp)
            task.total_files = len(file_list)

            for file_info in file_list:
                if task.status == SyncStatus.STOPPING:
                    task.status = SyncStatus.CANCELLED
                    ftp.quit()
                    return

                if task.status == SyncStatus.PAUSED:
                    ftp.quit()
                    return

                task.current_file = file_info['name']
                local_path = os.path.join(target_dir, file_info['name'])

                if not self._need_sync_ftp_file(local_path, file_info):
                    task.synced_files += 1
                    continue

                success = self._download_ftp_file(ftp, file_info, local_path, task)

                if success:
                    task.synced_files += 1
                    task.synced_size += file_info.get('size', 0)

                task.progress = (task.synced_files / task.total_files) * 100 if task.total_files > 0 else 0
                task.updated = datetime.now().isoformat()

            ftp.quit()

        except Exception as e:
            raise Exception(f"FTP sync failed: {str(e)}")

    def _sync_sftp(self, task: SyncTask, source: SyncSource):
        """SFTP同步实现"""
        if not paramiko:
            raise ImportError("paramiko not installed")

        config = source.config

        host = config.get('host', '')
        port = config.get('port', 22)
        username = config.get('username', 'anonymous')
        password = config.get('password')
        private_key = config.get('private_key')
        remote_path = config.get('remote_path', '/')

        target_dir = os.path.join(self.base_dir, source.target)
        os.makedirs(target_dir, exist_ok=True)

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                'hostname': host,
                'port': port,
                'username': username
            }

            if private_key:
                key = paramiko.RSAKey.from_private_key_file(private_key)
                connect_kwargs['pkey'] = key
            else:
                connect_kwargs['password'] = password

            ssh.connect(**connect_kwargs)
            sftp = ssh.open_sftp()

            # 统计文件数量
            total_files = self._count_sftp_files(sftp, remote_path)
            task.total_files = total_files

            self._sync_sftp_directory(sftp, remote_path, target_dir, task)

            sftp.close()
            ssh.close()

        except Exception as e:
            raise Exception(f"SFTP sync failed: {str(e)}")

    def _sync_sftp_directory(self, sftp, remote_path, local_path, task):
        """递归同步SFTP目录"""
        os.makedirs(local_path, exist_ok=True)

        try:
            file_list = sftp.listdir_attr(remote_path)
        except Exception as e:
            print(f"无法列出远程目录 {remote_path}: {e}")
            return 0

        synced_count = 0

        for file_attr in file_list:
            if task.status in [SyncStatus.STOPPING, SyncStatus.CANCELLED]:
                return synced_count

            if task.status == SyncStatus.PAUSED:
                return synced_count

            remote_filename = file_attr.filename
            remote_filepath = os.path.join(remote_path, remote_filename).replace('\\', '/')
            local_filepath = os.path.join(local_path, remote_filename)

            if remote_filename in ['.', '..']:
                continue

            is_dir = file_attr.st_mode & 0o40000

            if is_dir:
                sub_count = self._sync_sftp_directory(
                    sftp, remote_filepath, local_filepath, task
                )
                synced_count += sub_count
            else:
                task.current_file = remote_filename

                if self._need_sync_sftp_file(local_filepath, file_attr):
                    if self._download_sftp_file(sftp, remote_filepath, local_filepath, task):
                        synced_count += 1

            task.synced_files = synced_count
            task.progress = (task.synced_files / task.total_files) * 100 if task.total_files > 0 else 0
            task.updated = datetime.now().isoformat()

        return synced_count

    def _sync_local(self, task: SyncTask, source: SyncSource):
        """本地同步实现"""
        source_dir = source.config.get('path', '')
        target_dir = os.path.join(self.base_dir, source.target)

        if not os.path.exists(source_dir):
            raise Exception(f"Source directory not found: {source_dir}")

        os.makedirs(target_dir, exist_ok=True)

        # 统计文件
        total_files = sum([len(files) for _, _, files in os.walk(source_dir)])
        task.total_files = total_files

        for root, dirs, files in os.walk(source_dir):
            if task.status == SyncStatus.STOPPING:
                task.status = SyncStatus.CANCELLED
                return

            if task.status == SyncStatus.PAUSED:
                return

            relative_path = os.path.relpath(root, source_dir)
            target_path = os.path.join(target_dir, relative_path)
            os.makedirs(target_path, exist_ok=True)

            for filename in files:
                task.current_file = filename
                source_file = os.path.join(root, filename)
                target_file = os.path.join(target_path, filename)

                if self._need_sync_local_file(source_file, target_file):
                    shutil.copy2(source_file, target_file)
                    task.synced_size += os.path.getsize(target_file)

                task.synced_files += 1
                task.progress = (task.synced_files / task.total_files) * 100
                task.updated = datetime.now().isoformat()

    def _get_http_file_list(self, source: SyncSource) -> List[dict]:
        """获取HTTP文件列表"""
        import urllib.request
        import re
        import base64

        config = source.config
        base_url = source.url

        file_list = []

        # 如果有API URL，使用API
        if 'api_url' in config:
            try:
                req = urllib.request.Request(config['api_url'])
                if 'username' in config and 'password' in config:
                    auth_string = f"{config['username']}:{config['password']}"
                    encoded_auth = base64.b64encode(auth_string.encode()).decode()
                    req.add_header('Authorization', f'Basic {encoded_auth}')

                with urllib.request.urlopen(req, timeout=30) as response:
                    api_data = json.loads(response.read().decode())
                    if 'files' in api_data:
                        for file_info in api_data['files']:
                            file_list.append({
                                'name': file_info.get('name', ''),
                                'url': file_info.get('url', ''),
                                'size': file_info.get('size', 0)
                            })
                return file_list
            except Exception as e:
                print(f"API获取文件列表失败: {e}")

        # 否则解析HTML
        if config.get('parse_html', True):
            try:
                req = urllib.request.Request(base_url)
                with urllib.request.urlopen(req, timeout=30) as response:
                    html_content = response.read().decode('utf-8', errors='ignore')

                    link_pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>'
                    matches = re.findall(link_pattern, html_content, re.IGNORECASE)

                    for href, text in matches:
                        if href in ['../', './'] or href.startswith('?') or href.endswith('/'):
                            continue
                        file_url = href if href.startswith('http') else base_url.rstrip('/') + '/' + href.lstrip('/')
                        file_list.append({
                            'name': href.split('/')[-1],
                            'url': file_url,
                            'size': 0
                        })
            except Exception as e:
                print(f"HTML解析文件列表失败: {e}")

        return file_list

    def _get_ftp_file_list(self, ftp) -> List[dict]:
        """获取FTP文件列表"""
        file_list = []
        lines = []
        ftp.retrlines('LIST', lines.append)

        for line in lines:
            parts = line.split()
            if len(parts) < 9:
                continue

            filename = ' '.join(parts[8:])
            if filename in ['.', '..']:
                continue

            is_dir = parts[0].startswith('d')
            size = int(parts[4]) if not is_dir else 0

            file_list.append({
                'name': filename,
                'size': size,
                'is_dir': is_dir
            })

        return file_list

    def _count_sftp_files(self, sftp, remote_path) -> int:
        """统计SFTP远程目录文件数"""
        count = 0
        try:
            for entry in sftp.listdir_attr(remote_path):
                if entry.filename not in ['.', '..']:
                    if entry.st_mode & 0o40000:  # 目录
                        count += self._count_sftp_files(sftp, os.path.join(remote_path, entry.filename))
                    else:
                        count += 1
        except Exception:
            pass
        return count

    def _need_sync_file(self, local_path: str, remote_info: dict) -> bool:
        """检查HTTP文件是否需要同步"""
        if not os.path.exists(local_path):
            return True
        local_size = os.path.getsize(local_path)
        remote_size = remote_info.get('size', 0)
        return local_size != remote_size

    def _need_sync_ftp_file(self, local_path: str, remote_info: dict) -> bool:
        """检查FTP文件是否需要同步"""
        if not os.path.exists(local_path):
            return True
        local_size = os.path.getsize(local_path)
        remote_size = remote_info.get('size', 0)
        return local_size != remote_size

    def _need_sync_sftp_file(self, local_path: str, remote_attr) -> bool:
        """检查SFTP文件是否需要同步"""
        if not os.path.exists(local_path):
            return True
        local_size = os.path.getsize(local_path)
        remote_size = remote_attr.st_size
        if local_size != remote_size:
            return True
        local_mtime = os.path.getmtime(local_path)
        remote_mtime = remote_attr.st_mtime
        return abs(local_mtime - remote_mtime) > 1

    def _need_sync_local_file(self, source_path: str, target_path: str) -> bool:
        """检查本地文件是否需要同步"""
        if not os.path.exists(target_path):
            return True
        source_mtime = os.path.getmtime(source_path)
        target_mtime = os.path.getmtime(target_path)
        return source_mtime > target_mtime

    def _download_http_file(self, source: SyncSource, file_info: dict, local_path: str, task: SyncTask) -> bool:
        """下载HTTP文件"""
        import urllib.request
        import base64

        url = file_info.get('url', '')
        config = source.config

        try:
            req = urllib.request.Request(url)

            # 认证
            if 'username' in config and 'password' in config:
                auth_string = f"{config['username']}:{config['password']}"
                encoded_auth = base64.b64encode(auth_string.encode()).decode()
                req.add_header('Authorization', f'Basic {encoded_auth}')

            # 断点续传
            start_byte = 0
            if os.path.exists(local_path):
                start_byte = os.path.getsize(local_path)
                if start_byte > 0:
                    req.add_header('Range', f'bytes={start_byte}-')

            timeout = config.get('timeout', 30)
            temp_path = local_path + '.tmp'
            mode = 'ab' if start_byte > 0 else 'wb'

            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.getcode() not in [200, 206]:
                    raise Exception(f"HTTP错误: {response.getcode()}")

                total_size = int(response.headers.get('Content-Length', 0)) + start_byte
                task.total_size = total_size

                with open(temp_path, mode) as f:
                    downloaded = start_byte
                    while True:
                        if task.status in [SyncStatus.STOPPING, SyncStatus.CANCELLED]:
                            os.remove(temp_path) if os.path.exists(temp_path) else None
                            return False

                        chunk = response.read(8192)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        task.synced_size = downloaded
                        task.file_progress = (downloaded / total_size * 100) if total_size > 0 else 0

            # 重命名文件
            if os.path.exists(local_path):
                os.remove(local_path)
            os.rename(temp_path, local_path)

            return True

        except Exception as e:
            print(f"下载HTTP文件失败 {url}: {e}")
            return False

    def _download_ftp_file(self, ftp, file_info: dict, local_path: str, task: SyncTask) -> bool:
        """下载FTP文件"""
        try:
            start_pos = 0
            if os.path.exists(local_path):
                start_pos = os.path.getsize(local_path)
                if start_pos >= file_info['size']:
                    return True

            mode = 'ab' if start_pos > 0 else 'wb'

            with open(local_path, mode) as f:
                if start_pos > 0:
                    ftp.voidcmd('TYPE I')
                    ftp.retrbinary(f'RETR {file_info["name"]}', f.write, rest=start_pos)
                else:
                    ftp.retrbinary(f'RETR {file_info["name"]}', f.write)

            return True

        except Exception as e:
            print(f"下载FTP文件失败 {file_info['name']}: {e}")
            return False

    def _download_sftp_file(self, sftp, remote_path: str, local_path: str, task: SyncTask) -> bool:
        """下载SFTP文件"""
        try:
            file_attr = sftp.stat(remote_path)
            remote_size = file_attr.st_size

            start_pos = 0
            if os.path.exists(local_path):
                start_pos = os.path.getsize(local_path)

            if start_pos >= remote_size:
                return True

            task.total_size = remote_size

            with sftp.open(remote_path, 'rb') as remote_file:
                if start_pos > 0:
                    remote_file.seek(start_pos)

                with open(local_path, 'ab' if start_pos > 0 else 'wb') as local_file:
                    while True:
                        if task.status in [SyncStatus.STOPPING, SyncStatus.CANCELLED]:
                            return False

                        chunk = remote_file.read(8192)
                        if not chunk:
                            break

                        local_file.write(chunk)
                        task.synced_size += len(chunk)
                        task.file_progress = (task.synced_size / remote_size * 100) if remote_size > 0 else 0

            os.utime(local_path, (file_attr.st_atime, file_attr.st_mtime))
            return True

        except Exception as e:
            print(f"下载SFTP文件失败 {remote_path}: {e}")
            return False

    def _validate_source_config(self, config: dict) -> bool:
        """验证同步源配置"""
        sync_type = config.get('type', 'http')
        if sync_type not in ['http', 'https', 'ftp', 'sftp', 'local']:
            return False

        if sync_type in ['http', 'https']:
            if not config.get('url'):
                return False
        elif sync_type == 'ftp':
            if not config.get('host'):
                return False
        elif sync_type == 'sftp':
            if not config.get('host'):
                return False
        elif sync_type == 'local':
            if not config.get('path'):
                return False

        return True

    def _init_source_status(self, name: str):
        """初始化同步源状态"""
        pass  # 状态由任务管理

    def _add_history_entry(self, task: SyncTask, success: bool):
        """添加历史记录"""
        entry = {
            'task_id': task.task_id,
            'source_name': task.source_name,
            'status': task.status.value,
            'success': success,
            'started': task.started,
            'completed': datetime.now().isoformat(),
            'synced_files': task.synced_files,
            'synced_size': task.synced_size,
            'error': task.error
        }

        self.sync_history.append(entry)

        # 限制历史数量
        max_history = 1000
        if len(self.sync_history) > max_history:
            self.sync_history = self.sync_history[-max_history:]

        self._save_history()

    def _get_source_history(self, source_name: str = None, limit: int = 100) -> List[dict]:
        """获取同步历史"""
        if source_name:
            return [
                entry for entry in self.sync_history
                if entry.get('source_name') == source_name
            ][:limit]
        return self.sync_history[-limit:]

    def _get_source_total_synced(self, name: str) -> int:
        """获取源已同步文件数"""
        return sum(
            entry.get('synced_files', 0)
            for entry in self.sync_history
            if entry.get('source_name') == name
        )

    def _get_source_total_size(self, name: str) -> int:
        """获取源已同步大小"""
        return sum(
            entry.get('synced_size', 0)
            for entry in self.sync_history
            if entry.get('source_name') == name
        )

    def _save_sources(self):
        """保存同步源配置"""
        data = {
            name: source.to_dict()
            for name, source in self.sources.items()
        }

        try:
            with open(self.state_file.replace('state', 'sources'), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存同步源配置失败: {e}")

    def _load_sources(self):
        """加载同步源配置"""
        filename = self.state_file.replace('state', 'sources')

        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for name, config in data.items():
                        self.sources[name] = SyncSource(name, config)
            except Exception as e:
                print(f"加载同步源配置失败: {e}")

    def _save_history(self):
        """保存同步历史"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.sync_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存同步历史失败: {e}")

    def _load_history(self):
        """加载同步历史"""
        self.sync_history = []

        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.sync_history = json.load(f)
            except Exception as e:
                print(f"加载同步历史失败: {e}")

    def stop_all_tasks_for_source(self, source_name: str):
        """停止源的所有任务"""
        for task_id, task in list(self.active_tasks.items()):
            if task.source_name == source_name:
                self.stop_sync(task_id)

    def cleanup_completed_tasks(self, keep_count: int = 10):
        """清理已完成的任务"""
        with self.task_lock:
            completed_ids = [
                task_id for task_id, task in self.active_tasks.items()
                if task.status in [SyncStatus.COMPLETED, SyncStatus.FAILED, SyncStatus.CANCELLED]
            ]

            for task_id in completed_ids[-keep_count:]:
                del self.active_tasks[task_id]


class SyncSource:
    """同步源配置"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config.copy()
        self.type = config.get('type', 'http')
        self.url = config.get('url', '')
        self.target = config.get('target', name)
        self.enabled = config.get('enabled', True)
        self.auto_sync = config.get('auto_sync', False)
        self.schedule = config.get('schedule', '')
        self.filters = config.get('filters', {})
        self.auth = config.get('auth', {})
        self.options = config.get('options', {})

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'name': self.name,
            'type': self.type,
            'url': self.url,
            'target': self.target,
            'enabled': self.enabled,
            'auto_sync': self.auto_sync,
            'schedule': self.schedule,
            'filters': self.filters.copy(),
            'auth': self.auth.copy(),
            'options': self.options.copy()
        }

    def update_config(self, new_config: dict):
        """更新配置"""
        self.config.update(new_config)
        self.type = self.config.get('type', self.type)
        self.url = self.config.get('url', self.url)
        self.target = self.config.get('target', self.target)
        self.enabled = self.config.get('enabled', self.enabled)


class SyncTask:
    """同步任务"""

    def __init__(self, task_id: str, source_name: str):
        self.task_id = task_id
        self.source_name = source_name
        self.source_config = {}

        self.status = SyncStatus.PENDING
        self.progress = 0.0

        self.total_files = 0
        self.synced_files = 0
        self.total_size = 0
        self.synced_size = 0

        self.speed = 0
        self.eta = 0

        self.started = None
        self.updated = None
        self.completed = None

        self.error = None
        self.logs = []

        self.current_file = ''
        self.file_progress = 0
        self.paused_position = None

    def add_log(self, message: str, level: str = 'info'):
        """添加日志"""
        self.logs.append({
            'time': datetime.now().isoformat(),
            'level': level,
            'message': message
        })

        # 只保留最近100条日志
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'source_name': self.source_name,
            'status': self.status.value,
            'progress': round(self.progress, 2),
            'total_files': self.total_files,
            'synced_files': self.synced_files,
            'total_size': self.total_size,
            'synced_size': self.synced_size,
            'speed': self.speed,
            'eta': self.eta,
            'started': self.started,
            'updated': self.updated,
            'completed': self.completed,
            'error': self.error,
            'current_file': self.current_file,
            'file_progress': self.file_progress,
            'logs_count': len(self.logs)
        }
