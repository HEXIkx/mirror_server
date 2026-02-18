#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
定时同步调度器
负责本地数据和数据库之间的定时同步
"""

import os
import sys
import time
import json
import hashlib
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import DatabaseManager, get_db
from core.scheduler import Scheduler, ScheduledTask

logger = logging.getLogger(__name__)


class SyncScheduler:
    """同步调度器"""

    def __init__(self, config: dict, db: DatabaseManager = None):
        self.config = config
        self.db = db
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=4)

        # 同步配置
        self.sync_interval = config.get('database', {}).get('sync_interval', 60)
        self.auto_scan = config.get('auto_scan', True)
        self.scan_interval = config.get('scan_interval', 300)  # 5分钟扫描一次

        # 同步状态
        self.last_sync_time = 0
        self.last_scan_time = 0
        self.sync_in_progress = False
        self.scan_in_progress = False

        # 回调函数
        self.on_file_added: Optional[Callable] = None
        self.on_file_deleted: Optional[Callable] = None
        self.on_file_updated: Optional[Callable] = None
        self.on_sync_complete: Optional[Callable] = None

        # 待同步队列
        self._pending_add = []  # 待添加的文件
        self._pending_update = []  # 待更新的文件
        self._pending_delete = []  # 待删除的文件

        # 定时任务调度器
        self.task_scheduler = None
        self.scheduled_syncs: Dict[str, dict] = {}

    def _init_scheduled_syncs(self):
        """初始化定时同步任务"""
        if not self.config.get('enable_sync', True):
            return

        # 从配置加载定时同步设置
        sync_sources = self.config.get('sync_sources', {})
        scheduled_sources = {}

        for name, source_config in sync_sources.items():
            schedule = source_config.get('schedule', {})
            if schedule.get('enabled', False):
                scheduled_sources[name] = {
                    'type': schedule.get('type', 'interval'),  # 'cron' 或 'interval'
                    'config': {
                        'cron': schedule.get('cron'),
                        'interval': schedule.get('interval', {}),
                        'enabled': True
                    }
                }

        if scheduled_sources:
            self.task_scheduler = Scheduler()
            for name, sched_config in scheduled_sources.items():
                self.task_scheduler.add_task(
                    name=f"sync_{name}",
                    task_type=sched_config['type'],
                    config=sched_config['config'],
                    callback=self._create_sync_callback(name)
                )
            self.scheduled_syncs = scheduled_sources

    def _create_sync_callback(self, source_name: str):
        """创建同步回调函数"""
        def sync_callback(task_name: str, config: dict):
            logger.info(f"定时同步任务触发: {source_name}")
            self.start_sync(source_name)
            return True
        return sync_callback

    def start(self):
        """启动同步调度器"""
        if self._running:
            logger.warning("SyncScheduler 已经运行中")
            return

        self._running = True
        self._executor.submit(self._sync_loop)
        self._executor.submit(self._scan_loop)

        # 初始化并启动定时同步
        self._init_scheduled_syncs()
        if self.task_scheduler:
            self.task_scheduler.start()

        logger.info(f"同步调度器已启动，间隔: {self.sync_interval}秒")

    def stop(self):
        """停止同步调度器"""
        self._running = False

        # 停止定时任务调度器
        if self.task_scheduler:
            self.task_scheduler.stop()
            self.task_scheduler = None

        self._executor.shutdown(wait=True)
        logger.info("同步调度器已停止")

    def _sync_loop(self):
        """同步循环"""
        while self._running:
            try:
                if time.time() - self.last_sync_time >= self.sync_interval:
                    self.perform_sync()
                time.sleep(1)
            except Exception as e:
                logger.error(f"同步循环错误: {e}")
                time.sleep(5)

    def _scan_loop(self):
        """扫描循环 - 检测本地文件变化"""
        while self._running:
            try:
                if self.auto_scan and time.time() - self.last_scan_time >= self.scan_interval:
                    self.scan_local_files()
                time.sleep(5)
            except Exception as e:
                logger.error(f"扫描循环错误: {e}")
                time.sleep(10)

    def queue_add(self, file_info: dict):
        """队列添加文件"""
        self._pending_add.append(file_info)

    def queue_update(self, file_info: dict):
        """队列更新文件"""
        self._pending_update.append(file_info)

    def queue_delete(self, file_id: str):
        """队列删除文件"""
        self._pending_delete.append(file_id)

    def perform_sync(self):
        """执行同步"""
        if self.sync_in_progress:
            logger.warning("同步已在进行中，跳过")
            return

        self.sync_in_progress = True
        start_time = time.time()

        try:
            logger.info("开始执行数据库同步...")

            # 同步待添加的文件
            added = 0
            for file_info in self._pending_add[:]:
                try:
                    self._sync_add_file(file_info)
                    self._pending_add.remove(file_info)
                    added += 1
                except Exception as e:
                    logger.error(f"同步添加文件失败: {e}")

            # 同步待更新的文件
            updated = 0
            for file_info in self._pending_update[:]:
                try:
                    self._sync_update_file(file_info)
                    self._pending_update.remove(file_info)
                    updated += 1
                except Exception as e:
                    logger.error(f"同步更新文件失败: {e}")

            # 同步待删除的文件
            deleted = 0
            for file_id in self._pending_delete[:]:
                try:
                    self._sync_delete_file(file_id)
                    self._pending_delete.remove(file_id)
                    deleted += 1
                except Exception as e:
                    logger.error(f"同步删除文件失败: {e}")

            # 同步统计
            self.db.reset_pending_count()

            self.last_sync_time = time.time()
            duration = time.time() - start_time

            logger.info(f"同步完成: 添加{added}, 更新{updated}, 删除{deleted}, 耗时{duration:.2f}秒")

            # 回调
            if self.on_sync_complete:
                self.on_sync_complete({
                    'added': added,
                    'updated': updated,
                    'deleted': deleted,
                    'duration': duration
                })

        except Exception as e:
            logger.error(f"同步过程错误: {e}")
        finally:
            self.sync_in_progress = False

    def scan_local_files(self):
        """扫描本地文件"""
        if self.scan_in_progress:
            return

        self.scan_in_progress = True

        try:
            base_dir = self.config.get('base_dir', './downloads')
            if not os.path.exists(base_dir):
                self.last_scan_time = time.time()
                return

            # 扫描文件
            scanned_files = []
            for root, dirs, files in os.walk(base_dir):
                for filename in files:
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")

                    stat = os.stat(full_path)
                    file_info = {
                        'path': rel_path,
                        'name': filename,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'ctime': stat.st_ctime
                    }
                    scanned_files.append(file_info)

            # 与数据库对比
            db_files = self.db.list_files(limit=100000)
            db_paths = {f.path for f in db_files if not f.is_dir}

            # 检测新增
            local_paths = {f['path'] for f in scanned_files}
            new_paths = local_paths - db_paths

            for path in new_paths:
                file_info = next((f for f in scanned_files if f['path'] == path), None)
                if file_info:
                    file_id = hashlib.md5(path.encode()).hexdigest()
                    self._sync_add_file({
                        'file_id': file_id,
                        'path': path,
                        'name': file_info['name'],
                        'size': file_info['size'],
                        'updated_at': file_info['mtime']
                    })

            # 检测删除
            deleted_paths = db_paths - local_paths
            for path in deleted_paths:
                record = self.db.get_file_by_path(path)
                if record:
                    self.db.delete_file(record.file_id)

            self.last_scan_time = time.time()

        except Exception as e:
            logger.error(f"扫描本地文件错误: {e}")
        finally:
            self.scan_in_progress = False

    def _sync_add_file(self, file_info: dict):
        """同步添加文件"""
        existing = self.db.get_file_by_path(file_info['path'])
        if existing:
            # 已存在，更新
            self.db.update_file(
                existing.file_id,
                size=file_info.get('size', 0),
                updated_at=file_info.get('updated_at', time.time()),
                hash=file_info.get('hash'),
                sync_status='synced'
            )
        else:
            # 新增
            file_id = file_info.get('file_id') or hashlib.md5(
                file_info['path'].encode()
            ).hexdigest()

            self.db.add_file(
                file_id=file_id,
                path=file_info['path'],
                name=file_info['name'],
                size=file_info.get('size', 0),
                hash=file_info.get('hash'),
                is_dir=False,
                created_at=file_info.get('created_at'),
                updated_at=file_info.get('updated_at', time.time())
            )

        if self.on_file_added:
            self.on_file_added(file_info)

    def _sync_update_file(self, file_info: dict):
        """同步更新文件"""
        file_id = file_info.get('file_id')
        if file_id:
            self.db.update_file(
                file_id,
                size=file_info.get('size'),
                updated_at=file_info.get('updated_at', time.time()),
                hash=file_info.get('hash'),
                sync_status='synced'
            )

        if self.on_file_updated:
            self.on_file_updated(file_info)

    def _sync_delete_file(self, file_id: str):
        """同步删除文件"""
        self.db.delete_file(file_id)

        if self.on_file_deleted:
            self.on_file_deleted({'file_id': file_id})

    def get_status(self) -> dict:
        """获取同步状态"""
        return {
            'running': self._running,
            'last_sync_time': self.last_sync_time,
            'last_scan_time': self.last_scan_time,
            'sync_in_progress': self.sync_in_progress,
            'scan_in_progress': self.scan_in_progress,
            'pending_add': len(self._pending_add),
            'pending_update': len(self._pending_update),
            'pending_delete': len(self._pending_delete),
            'pending_operations': self.db.get_pending_operations() if self.db else 0
        }

    def force_sync(self):
        """强制立即同步"""
        self.last_sync_time = 0
        self.perform_sync()


# ==================== 文件操作包装器 ====================

class DatabaseBackedFileOperations:
    """数据库支持的文件操作"""

    def __init__(self, config: dict, db: DatabaseManager, scheduler: SyncScheduler = None):
        self.config = config
        self.db = db
        self.scheduler = scheduler
        self.base_dir = config.get('base_dir', './downloads')

    def add_file_record(self, path: str, name: str, size: int = 0,
                       hash: str = None, is_dir: bool = False) -> dict:
        """添加文件记录到数据库"""
        import hashlib

        file_id = hashlib.md5(path.encode()).hexdigest()

        file_info = {
            'file_id': file_id,
            'path': path,
            'name': name,
            'size': size,
            'hash': hash,
            'is_dir': is_dir,
            'created_at': time.time(),
            'updated_at': time.time()
        }

        if self.scheduler:
            self.scheduler.queue_add(file_info)
        else:
            self.db.add_file(
                file_id=file_id,
                path=path,
                name=name,
                size=size,
                hash=hash,
                is_dir=is_dir,
                created_at=time.time(),
                updated_at=time.time()
            )

        return file_info

    def update_file_record(self, file_id: str, **kwargs):
        """更新文件记录"""
        if self.scheduler:
            self.scheduler.queue_update({'file_id': file_id, **kwargs})
        else:
            self.db.update_file(file_id, **kwargs)

    def delete_file_record(self, file_id: str, hard: bool = False):
        """删除文件记录"""
        if self.scheduler:
            self.scheduler.queue_delete(file_id)
        else:
            self.db.delete_file(file_id, hard=hard)

    def record_download(self, file_path: str, file_size: int = 0,
                       client_ip: str = None, duration: float = 0,
                       success: bool = True, error_message: str = None):
        """记录下载"""
        self.db.add_download_record(
            file_path=file_path,
            file_size=file_size,
            client_ip=client_ip,
            duration=duration,
            success=success,
            error_message=error_message
        )

        # 更新下载计数
        record = self.db.get_file_by_path(file_path)
        if record:
            self.db.increment_download_count(record.file_id)

    def record_cache_hit(self, cache_key: str, cache_type: str):
        """记录缓存命中"""
        record = self.db.get_cache_record(cache_key)
        if record:
            self.db.increment_cache_hits(cache_key)
        else:
            self.db.add_cache_record(
                cache_key=cache_key,
                cache_type=cache_type,
                hits=1,
                last_hit=time.time()
            )


# ==================== 便捷函数 ====================

def get_sync_scheduler(config: dict) -> SyncScheduler:
    """获取同步调度器"""
    db = get_db(config)
    return SyncScheduler(config, db)


def init_database_sync(config: dict, db=None) -> tuple:
    """初始化数据库和同步"""
    if db is None:
        db = get_db(config)
    scheduler = SyncScheduler(config, db)
    file_ops = DatabaseBackedFileOperations(config, db, scheduler)

    return db, scheduler, file_ops
