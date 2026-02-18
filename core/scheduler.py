#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
定时任务调度器
支持 cron 表达式和简单间隔的定时任务
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


class ScheduledTask:
    """定时任务"""

    def __init__(self, name: str, task_type: str, config: dict,
                 callback: Callable, logger=None):
        """
        初始化定时任务

        Args:
            name: 任务名称
            task_type: 任务类型 ('cron' 或 'interval')
            config: 任务配置
            callback: 回调函数
            logger: 日志器
        """
        self.name = name
        self.task_type = task_type  # 'cron' 或 'interval'
        self.config = config or {}
        self.callback = callback
        self.logger = logger or logging.getLogger(__name__)

        # 状态
        self.status = TaskStatus.IDLE
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.run_count = 0

        # 配置解析
        self._parse_config()

    def _parse_config(self):
        """解析任务配置"""
        if self.task_type == 'cron':
            # Cron 表达式: "minute hour day month weekday"
            # 例如: "0 3 * * *" 每天凌晨3点
            cron = self.config.get('cron', '0 0 * * *')
            parts = cron.split()
            if len(parts) == 5:
                self.cron_parts = {
                    'minute': self._parse_cron_part(parts[0], 0, 59),
                    'hour': self._parse_cron_part(parts[1], 0, 23),
                    'day': self._parse_cron_part(parts[2], 1, 31),
                    'month': self._parse_cron_part(parts[3], 1, 12),
                    'weekday': self._parse_cron_part(parts[4], 0, 6)
                }
            else:
                self.logger.warning(f"无效的 cron 表达式: {cron}")
                self.cron_parts = None

        elif self.task_type == 'interval':
            # 间隔: seconds, minutes, hours
            interval = self.config.get('interval', {})
            self.interval_seconds = (
                interval.get('seconds', 0) +
                interval.get('minutes', 0) * 60 +
                interval.get('hours', 0) * 3600 +
                interval.get('days', 0) * 86400
            )
            if self.interval_seconds <= 0:
                self.interval_seconds = 3600  # 默认1小时

        # 是否启用
        self.enabled = self.config.get('enabled', True)

    def _parse_cron_part(self, part: str, min_val: int, max_val: int) -> List[int]:
        """解析 cron 表达式的一部分"""
        result = []
        if part == '*':
            return list(range(min_val, max_val + 1))

        # 处理列表: "1,2,3"
        if ',' in part:
            return self._parse_cron_part(part.replace(',', ' '), min_val, max_val)

        # 处理范围: "1-5"
        if '-' in part:
            start, end = part.split('-')
            return list(range(int(start), int(end) + 1))

        # 处理步进: "*/5"
        if '/' in part:
            base, step = part.split('/')
            base_list = self._parse_cron_part(base or '*', min_val, max_val)
            step = int(step)
            return base_list[::step]

        # 单个值
        try:
            val = int(part)
            if min_val <= val <= max_val:
                return [val]
        except ValueError:
            pass

        return []

    def should_run_now(self) -> bool:
        """检查是否应该在当前时刻运行"""
        if not self.enabled:
            return False

        now = datetime.now()

        if self.task_type == 'cron' and self.cron_parts:
            return self._matches_cron(now)
        elif self.task_type == 'interval':
            if self.last_run is None:
                return True
            elapsed = (now - self.last_run).total_seconds()
            return elapsed >= self.interval_seconds

        return False

    def _matches_cron(self, dt: datetime) -> bool:
        """检查时间是否匹配 cron 表达式"""
        if not self.cron_parts:
            return False

        return (
            dt.minute in self.cron_parts['minute'] and
            dt.hour in self.cron_parts['hour'] and
            dt.day in self.cron_parts['day'] and
            dt.month in self.cron_parts['month'] and
            dt.weekday() in self.cron_parts['weekday']
        )

    def get_next_run_time(self) -> Optional[datetime]:
        """计算下次运行时间"""
        if not self.enabled:
            return None

        now = datetime.now()

        if self.task_type == 'cron' and self.cron_parts:
            # 找到下一个匹配的时间点
            for i in range(365 * 24 * 60):  # 最多查找1年
                candidate = now + timedelta(minutes=i)
                if self._matches_cron(candidate):
                    return candidate
        elif self.task_type == 'interval':
            if self.last_run:
                return self.last_run + timedelta(seconds=self.interval_seconds)
            return now

        return None

    def run(self) -> bool:
        """执行任务"""
        if self.status == TaskStatus.RUNNING:
            self.logger.warning(f"任务 {self.name} 已在运行中")
            return False

        self.status = TaskStatus.RUNNING
        self.last_run = datetime.now()
        self.last_error = None

        try:
            self.logger.info(f"开始执行定时任务: {self.name}")
            result = self.callback(self.name, self.config)
            self.run_count += 1
            self.logger.info(f"定时任务 {self.name} 执行完成")
            return True
        except Exception as e:
            self.last_error = str(e)
            self.status = TaskStatus.ERROR
            self.logger.error(f"定时任务 {self.name} 执行失败: {e}")
            return False
        finally:
            if self.status != TaskStatus.ERROR:
                self.status = TaskStatus.IDLE

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'name': self.name,
            'type': self.task_type,
            'enabled': self.enabled,
            'status': self.status.value,
            'config': self.config,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'run_count': self.run_count,
            'last_error': self.last_error
        }


class Scheduler:
    """定时任务调度器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 默认检查间隔
        self.check_interval = self.config.get('check_interval', 10)

        # 事件回调
        self.on_task_start: Optional[Callable] = None
        self.on_task_complete: Optional[Callable] = None
        self.on_task_error: Optional[Callable] = None

    def add_task(self, name: str, task_type: str, config: dict,
                 callback: Callable) -> bool:
        """
        添加定时任务

        Args:
            name: 任务名称
            task_type: 任务类型 ('cron' 或 'interval')
            config: 任务配置
            callback: 回调函数

        Returns:
            是否成功
        """
        with self._lock:
            if name in self.tasks:
                logger.warning(f"任务 {name} 已存在，将被替换")
            self.tasks[name] = ScheduledTask(name, task_type, config, callback, logger)
            return True

    def remove_task(self, name: str) -> bool:
        """移除任务"""
        with self._lock:
            if name in self.tasks:
                del self.tasks[name]
                return True
            return False

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        """获取任务"""
        return self.tasks.get(name)

    def get_all_tasks(self) -> List[dict]:
        """获取所有任务状态"""
        with self._lock:
            for task in self.tasks.values():
                task.next_run = task.get_next_run_time()
            return [task.to_dict() for task in self.tasks.values()]

    def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("调度器已在运行中")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("定时任务调度器已启动")

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("定时任务调度器已停止")

    def _run_loop(self):
        """运行循环"""
        while self._running:
            try:
                now = datetime.now()

                with self._lock:
                    for name, task in self.tasks.items():
                        if task.should_run_now():
                            # 使用线程池执行任务
                            from concurrent.futures import ThreadPoolExecutor
                            with ThreadPoolExecutor(max_workers=1) as executor:
                                executor.submit(task.run)

                time.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"调度器循环错误: {e}")
                time.sleep(5)

    def run_task_now(self, name: str) -> bool:
        """立即运行指定任务"""
        task = self.get_task(name)
        if task:
            return task.run()
        return False

    def enable_task(self, name: str, enabled: bool = True) -> bool:
        """启用/禁用任务"""
        task = self.get_task(name)
        if task:
            task.enabled = enabled
            return True
        return False

    def update_task_config(self, name: str, config: dict) -> bool:
        """更新任务配置"""
        task = self.get_task(name)
        if task:
            task.config.update(config)
            task._parse_config()
            return True
        return False


# ==================== 同步任务工厂 ====================

# def create_sync_task_callback(sync_manager):
#     """创建同步任务的回调函数"""
#     def sync_task_callback(task_name: str, config: dict):
#         """同步任务回调"""
#         sync_manager.start_sync(task_name)
#         return True
#     return sync_task_callback


# ==================== 默认任务配置 ====================
# DEFAULT_SCHEDULED_TASKS = { ... }

DEFAULT_SCHEDULED_TASKS = {
    # 数据库清理 - 每天凌晨2点
    'cleanup_db': {
        'type': 'cron',
        'config': {
            'cron': '0 2 * * *',
            'enabled': True
        }
    },
    # 缓存清理 - 每6小时
    'cleanup_cache': {
        'type': 'interval',
        'config': {
            'interval': {'hours': 6},
            'enabled': True
        }
    },
    # 健康检查 - 每5分钟
    'health_check': {
        'type': 'interval',
        'config': {
            'interval': {'minutes': 5},
            'enabled': True
        }
    }
}
