#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
缓存预热模块
预热常用镜像缓存提高命中率
"""

import os
import sys
import json
import time
import threading
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class PrewarmPriority(Enum):
    """预热优先级"""
    CRITICAL = "critical"  # 关键，必须预热
    HIGH = "high"           # 高优先级
    MEDIUM = "medium"       # 中优先级
    LOW = "low"             # 低优先级


class ItemStatus(Enum):
    """项目状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PrewarmItem:
    """预热项目"""
    id: str
    mirror_type: str
    item_name: str
    url: str
    priority: str
    status: str = field(default=ItemStatus.PENDING.value)
    attempts: int = 0
    max_attempts: int = 3
    response_time_ms: float = 0
    error_message: str = None
    prewarmed_at: float = None
    size_bytes: int = 0

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'mirror_type': self.mirror_type,
            'item_name': self.item_name,
            'url': self.url,
            'priority': self.priority,
            'status': self.status,
            'attempts': self.attempts,
            'response_time_ms': self.response_time_ms,
            'error_message': self.error_message,
            'prewarmed_at': self.prewarmed_at,
            'size_bytes': self.size_bytes
        }


@dataclass
class PrewarmTarget:
    """预热目标配置"""
    mirror_type: str
    priority: str
    limit: int
    items: List[str] = field(default_factory=list)  # 指定的预热项目列表
    tags: List[str] = field(default_factory=list)  # 按标签筛选


class CachePrewarmer:
    """缓存预热管理器"""

    def __init__(self, config: Dict = None):
        """
        初始化缓存预热管理器

        Args:
            config: 预热配置
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', False)

        # 预热目标
        self.targets = self._parse_targets(self.config.get('targets', []))

        # 调度配置
        self.schedule = self.config.get('schedule', '0 3 * * *')  # 默认每天凌晨3点
        self.batch_size = self.config.get('batch_size', 10)

        # 状态管理
        self._items: Dict[str, PrewarmItem] = {}
        self._items_lock = threading.Lock()
        self._is_running = False
        self._run_lock = threading.Lock()

        # 历史记录
        self._history: List[Dict] = []
        self._history_lock = threading.Lock()

        # 回调函数
        self._on_start: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        self._on_item_complete: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        # HTTP 会话
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'HYC-Mirror-Prewarmer/1.0'
        })

        # 超时设置
        self._request_timeout = self.config.get('request_timeout', 30)

        # 常用镜像包列表
        self._popular_items = self._load_popular_items()

    def _parse_targets(self, targets_config: List[Dict]) -> List[PrewarmTarget]:
        """解析预热目标配置"""
        targets = []
        for t in targets_config:
            targets.append(PrewarmTarget(
                mirror_type=t.get('mirror_type', 'docker'),
                priority=t.get('priority', 'medium'),
                limit=t.get('limit', 100),
                items=t.get('items', []),
                tags=t.get('tags', [])
            ))
        return targets

    def _load_popular_items(self) -> Dict[str, List[str]]:
        """加载常用镜像包列表"""
        return {
            'docker': [
                'library/alpine:latest',
                'library/ubuntu:latest',
                'library/debian:latest',
                'library/centos:latest',
                'library/nginx:latest',
                'library/python:3.9',
                'library/python:3.10',
                'library/node:18',
                'library/node:20',
                'library/go:1.20',
                'library/redis:alpine',
                'library/mysql:8',
                'library/postgres:15',
            ],
            'pip': [
                'requests',
                'numpy',
                'pandas',
                'flask',
                'django',
                'scipy',
                'scikit-learn',
                'torch',
                'tensorflow',
                'celery',
                'pytest',
                'black',
            ],
            'npm': [
                'react',
                'vue',
                'angular',
                'lodash',
                'express',
                'axios',
                'typescript',
                'webpack',
                'vite',
                'eslint',
            ],
            'apt': [
                'ubuntu-desktop',
                'ubuntu-standard',
                'nginx',
                'python3-pip',
                'nodejs',
                'docker.io',
            ],
            'yum': [
                'epel-release',
                'nginx',
                'docker-ce',
                'python3-pip',
                'nodejs',
            ],
            'go': [
                'golang.org/x/tools',
                'github.com/gin-gonic/gin',
                'github.com/beego/beego',
                'github.com/gorilla/mux',
            ],
        }

    def _get_base_url(self, mirror_type: str) -> str:
        """获取镜像源基础 URL"""
        mirrors = self.config.get('mirrors', {})

        if isinstance(mirrors, dict):
            mirror_config = mirrors.get(mirror_type, {})
            if isinstance(mirror_config, dict):
                sources = mirror_config.get('sources', [])
                if sources:
                    source_config = mirror_config.get('sources_config', {}).get(sources[0], {})
                    return source_config.get('url', '')

        return ''

    def _generate_url(self, mirror_type: str, item_name: str) -> str:
        """生成预热 URL"""
        base_url = self._get_base_url(mirror_type)

        if not base_url:
            return ''

        if mirror_type == 'docker':
            return f"{base_url}/v2/{item_name}/manifests/latest"
        elif mirror_type == 'pip':
            return f"{base_url}/simple/{item_name}/"
        elif mirror_type == 'npm':
            return f"{base_url}/{item_name}"
        elif mirror_type == 'apt':
            return f"{base_url}/dists/{item_name}/InRelease"
        elif mirror_type == 'yum':
            return f"{base_url}/repodata/repomd.xml"
        elif mirror_type == 'go':
            return f"{base_url}/{item_name}?go-get=1"
        else:
            return f"{base_url}/{item_name}"

    def _create_item(
        self,
        mirror_type: str,
        item_name: str,
        priority: str = 'medium'
    ) -> PrewarmItem:
        """创建预热项目"""
        url = self._generate_url(mirror_type, item_name)

        return PrewarmItem(
            id=f"{mirror_type}_{item_name}_{int(time.time())}",
            mirror_type=mirror_type,
            item_name=item_name,
            url=url,
            priority=priority
        )

    def add_item(self, item: PrewarmItem):
        """添加预热项目"""
        with self._items_lock:
            self._items[item.id] = item

    def add_items_batch(self, mirror_type: str, items: List[str], priority: str = 'medium'):
        """批量添加预热项目"""
        for item_name in items:
            item = self._create_item(mirror_type, item_name, priority)
            self.add_item(item)

    def _prewarm_item(self, item: PrewarmItem) -> PrewarmItem:
        """
        预热单个项目

        Args:
            item: 预热项目

        Returns:
            更新后的项目
        """
        item.attempts += 1
        item.status = ItemStatus.IN_PROGRESS.value

        try:
            start_time = time.time()

            response = self._session.get(
                item.url,
                timeout=self._request_timeout,
                allow_redirects=True
            )

            response.raise_for_status()

            item.response_time_ms = round((time.time() - start_time) * 1000, 2)
            item.size_bytes = len(response.content)
            item.status = ItemStatus.SUCCESS.value
            item.prewarmed_at = time.time()

            logger.debug(f"Prewarmed {item.mirror_type}/{item.item_name}: {item.response_time_ms}ms")

        except requests.exceptions.Timeout:
            item.error_message = f"Timeout after {self._request_timeout}s"
            if item.attempts < item.max_attempts:
                item.status = ItemStatus.PENDING.value
            else:
                item.status = ItemStatus.FAILED.value

        except requests.exceptions.HTTPError as e:
            item.error_message = f"HTTP Error: {e.response.status_code}"
            if item.attempts < item.max_attempts:
                item.status = ItemStatus.PENDING.value
            else:
                item.status = ItemStatus.FAILED.value

        except Exception as e:
            item.error_message = str(e)
            item.status = ItemStatus.FAILED.value

        return item

    def run(self, targets: List[PrewarmTarget] = None) -> Dict:
        """
        执行预热

        Args:
            targets: 预热目标列表，None 表示使用配置的默认目标

        Returns:
            预热结果
        """
        with self._run_lock:
            if self._is_running:
                return {
                    'success': False,
                    'error': 'Prewarm already running'
                }

            self._is_running = True

        start_time = time.time()
        result = {
            'success': True,
            'total_items': 0,
            'success_count': 0,
            'failed_count': 0,
            'skipped_count': 0,
            'elapsed_seconds': 0,
            'errors': []
        }

        try:
            # 通知开始
            if self._on_start:
                try:
                    self._on_start()
                except Exception as e:
                    logger.error(f"Prewarm start callback failed: {e}")

            # 确定要预热的目标
            if targets is None:
                targets = self.targets

            # 如果没有指定目标，使用流行项目
            if not targets:
                for mirror_type, items in self._popular_items.items():
                    targets.append(PrewarmTarget(
                        mirror_type=mirror_type,
                        priority='medium',
                        limit=len(items),
                        items=items
                    ))

            # 添加项目到队列
            total_added = 0
            for target in targets:
                if target.items:
                    # 使用指定的预热项目
                    for item_name in target.items[:target.limit]:
                        item = self._create_item(target.mirror_type, item_name, target.priority)
                        self.add_item(item)
                        total_added += 1
                else:
                    # 使用流行项目列表
                    popular = self._popular_items.get(target.mirror_type, [])
                    for item_name in popular[:target.limit]:
                        item = self._create_item(target.mirror_type, item_name, target.priority)
                        self.add_item(item)
                        total_added += 1

            result['total_items'] = total_added

            # 按优先级排序
            priority_order = {
                'critical': 0,
                'high': 1,
                'medium': 2,
                'low': 3
            }

            with self._items_lock:
                sorted_items = sorted(
                    self._items.values(),
                    key=lambda x: (priority_order.get(x.priority, 99), x.id)
                )

            # 分批执行
            completed = 0
            with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
                futures = {
                    executor.submit(self._prewarm_item, item): item
                    for item in sorted_items
                }

                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        updated_item = future.result()

                        # 更新项目状态
                        with self._items_lock:
                            self._items[item.id] = updated_item

                        # 统计
                        if updated_item.status == ItemStatus.SUCCESS.value:
                            result['success_count'] += 1
                        elif updated_item.status == ItemStatus.FAILED.value:
                            result['failed_count'] += 1
                            result['errors'].append({
                                'item': updated_item.item_name,
                                'error': updated_item.error_message
                            })
                        else:
                            result['skipped_count'] += 1

                        completed += 1

                        # 回调
                        if self._on_item_complete:
                            try:
                                self._on_item_complete(updated_item)
                            except Exception as e:
                                logger.error(f"Item complete callback failed: {e}")

                    except Exception as e:
                        logger.error(f"Prewarm execution error: {e}")
                        result['failed_count'] += 1
                        result['errors'].append({
                            'item': item.item_name,
                            'error': str(e)
                        })

            result['elapsed_seconds'] = round(time.time() - start_time, 2)

            # 记录历史
            self._add_to_history(result)

            # 通知完成
            if self._on_complete:
                try:
                    self._on_complete(result)
                except Exception as e:
                    logger.error(f"Prewarm complete callback failed: {e}")

        except Exception as e:
            logger.error(f"Prewarm failed: {e}")
            result['success'] = False
            result['errors'].append({'error': str(e)})

        finally:
            self._is_running = False

        return result

    def _add_to_history(self, result: Dict):
        """添加历史记录"""
        record = {
            'timestamp': datetime.now().isoformat(),
            'success': result.get('success', False),
            'total_items': result.get('total_items', 0),
            'success_count': result.get('success_count', 0),
            'failed_count': result.get('failed_count', 0),
            'elapsed_seconds': result.get('elapsed_seconds', 0)
        }

        with self._history_lock:
            self._history.append(record)
            # 只保留最近 50 条记录
            self._history = self._history[-50:]

    def get_status(self) -> Dict:
        """获取预热状态"""
        with self._items_lock:
            items = list(self._items.values())

        total = len(items)
        success = sum(1 for i in items if i.status == ItemStatus.SUCCESS.value)
        failed = sum(1 for i in items if i.status == ItemStatus.FAILED.value)
        in_progress = sum(1 for i in items if i.status == ItemStatus.IN_PROGRESS.value)
        pending = sum(1 for i in items if i.status == ItemStatus.PENDING.value)

        return {
            'enabled': self.enabled,
            'is_running': self._is_running,
            'total_items': total,
            'success_count': success,
            'failed_count': failed,
            'in_progress_count': in_progress,
            'pending_count': pending,
            'success_rate': (success / total * 100) if total > 0 else 0,
            'targets_count': len(self.targets)
        }

    def get_items(
        self,
        status: str = None,
        mirror_type: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """获取预热项目列表"""
        with self._items_lock:
            items = [i.to_dict() for i in self._items.values()]

        # 过滤
        if status:
            items = [i for i in items if i['status'] == status]
        if mirror_type:
            items = [i for i in items if i['mirror_type'] == mirror_type]

        return items[-limit:]

    def get_history(self, limit: int = 20) -> List[Dict]:
        """获取预热历史"""
        with self._history_lock:
            return list(self._history[-limit:])

    def get_stats(self) -> Dict:
        """获取统计信息"""
        status = self.get_status()
        history = self.get_history(10)

        avg_duration = 0
        if history:
            durations = [h['elapsed_seconds'] for h in history if 'elapsed_seconds' in h]
            if durations:
                avg_duration = sum(durations) / len(durations)

        return {
            'enabled': self.enabled,
            'is_running': self._is_running,
            'total_prewarmed': status['success_count'],
            'total_failed': status['failed_count'],
            'success_rate': status['success_rate'],
            'avg_duration_seconds': round(avg_duration, 2),
            'recent_runs': len(history),
            'targets': [
                {
                    'mirror_type': t.mirror_type,
                    'priority': t.priority,
                    'limit': t.limit
                }
                for t in self.targets
            ]
        }

    def clear_items(self, status: str = None):
        """清除预热项目"""
        with self._items_lock:
            if status:
                self._items = {
                    k: v for k, v in self._items.items()
                    if v.status != status
                }
            else:
                self._items = {}

    def set_start_callback(self, callback: Callable):
        """设置开始回调"""
        self._on_start = callback

    def set_complete_callback(self, callback: Callable):
        """设置完成回调"""
        self._on_complete = callback

    def set_item_complete_callback(self, callback: Callable):
        """设置项目完成回调"""
        self._on_item_complete = callback

    def set_error_callback(self, callback: Callable):
        """设置错误回调"""
        self._on_error = callback

    def get_popular_items(self, mirror_type: str) -> List[str]:
        """获取指定镜像类型的流行项目列表"""
        return self._popular_items.get(mirror_type, [])

    def add_popular_items_to_queue(
        self,
        mirror_type: str,
        limit: int = None,
        priority: str = 'medium'
    ):
        """
        添加流行项目到预热队列

        Args:
            mirror_type: 镜像类型
            limit: 数量限制
            priority: 优先级
        """
        popular = self._popular_items.get(mirror_type, [])
        if limit:
            popular = popular[:limit]

        self.add_items_batch(mirror_type, popular, priority)


class PrewarmScheduler:
    """预热调度器"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self._scheduler = None
        self._running = False

    def start(self, prewarmer: CachePrewarmer):
        """启动调度器"""
        if self._running:
            return

        schedule = self.config.get('schedule', '0 3 * * *')
        logger.info(f"Starting prewarm scheduler with schedule: {schedule}")

        # 使用简单的时间间隔检查
        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._run_scheduler,
            args=(prewarmer,),
            daemon=True
        )
        self._scheduler_thread.start()

    def _run_scheduler(self, prewarmer: CachePrewarmer):
        """运行调度器"""
        import croniter

        schedule = self.config.get('schedule', '0 3 * * *')

        try:
            cron = croniter.croniter(schedule, datetime.now())
            next_run = cron.get_next(datetime)
        except Exception as e:
            logger.error(f"Invalid cron schedule: {e}")
            return

        while self._running:
            now = datetime.now()
            if now >= next_run:
                logger.info("Running scheduled prewarm")
                try:
                    prewarmer.run()
                except Exception as e:
                    logger.error(f"Scheduled prewarm failed: {e}")
                cron = croniter.croniter(schedule, datetime.now())
                next_run = cron.get_next(datetime)

            # 检查间隔
            time.sleep(60)

    def stop(self):
        """停止调度器"""
        self._running = False
