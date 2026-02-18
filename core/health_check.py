#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
镜像源健康检查模块
自动检测上游镜像源的可用性，支持故障切换
"""

import os
import sys
import json
import time
import threading
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    source_name: str
    status: HealthStatus
    response_time: float  # 毫秒
    http_status: Optional[int] = None
    error_message: Optional[str] = None
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    total_checks: int = 0
    success_rate: float = 100.0
    details: Dict = field(default_factory=dict)


class HealthChecker:
    """健康检查器"""

    def __init__(self, config: dict = None):
        """
        初始化健康检查器

        Args:
            config: 健康检查配置
        """
        self.config = config or {}
        self.default_timeout = self.config.get('timeout', 10)  # 秒
        self.default_interval = self.config.get('interval', 60)  # 秒
        self.max_retries = self.config.get('max_retries', 3)
        self.failure_threshold = self.config.get('failure_threshold', 3)  # 连续失败次数阈值

        # 检查结果存储
        self._results: Dict[str, HealthCheckResult] = {}
        self._lock = threading.Lock()

        # 状态变化回调
        self._on_status_change: Optional[Callable] = None

    def set_status_change_callback(self, callback: Callable):
        """设置状态变化回调"""
        self._on_status_change = callback

    def check_source(self, source_name: str, source_config: dict) -> HealthCheckResult:
        """
        检查单个镜像源的健康状态

        Args:
            source_name: 镜像源名称
            source_config: 镜像源配置

        Returns:
            HealthCheckResult: 检查结果
        """
        url = source_config.get('url', '')
        if not url:
            return HealthCheckResult(
                source_name=source_name,
                status=HealthStatus.UNHEALTHY,
                response_time=0,
                error_message="No URL configured",
                last_check=datetime.now()
            )

        start_time = time.time()
        http_status = None
        error_message = None
        details = {}

        try:
            # 发送 HEAD 请求（更轻量）
            req = urllib.request.Request(
                url.rstrip('/') + '/',
                method='HEAD',
                headers={
                    'User-Agent': 'HYC-Mirror-HealthCheck/1.0',
                    'Accept': '*/*'
                }
            )

            with urllib.request.urlopen(req, timeout=self.default_timeout) as response:
                http_status = response.status
                details['headers'] = dict(response.headers)

        except urllib.error.HTTPError as e:
            http_status = e.code
            error_message = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            error_message = f"Connection error: {str(e.reason)}"
        except Exception as e:
            error_message = str(e)

        response_time = (time.time() - start_time) * 1000  # 转换为毫秒

        # 判断健康状态
        if error_message:
            if http_status and 400 <= http_status < 500:
                status = HealthStatus.DEGRADED  # 客户端错误，可能暂时
            else:
                status = HealthStatus.UNHEALTHY
        elif http_status and 200 <= http_status < 400:
            status = HealthStatus.HEALTHY
        elif http_status:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY

        # 计算统计数据
        with self._lock:
            if source_name not in self._results:
                self._results[source_name] = HealthCheckResult(
                    source_name=source_name,
                    status=status,
                    response_time=response_time,
                    last_check=datetime.now(),
                    consecutive_failures=0,
                    total_checks=1
                )
            else:
                old_result = self._results[source_name]
                consecutive_failures = old_result.consecutive_failures + (1 if status == HealthStatus.UNHEALTHY else 0)
                total_checks = old_result.total_checks + 1
                success_rate = ((total_checks - consecutive_failures) / total_checks) * 100

                self._results[source_name] = HealthCheckResult(
                    source_name=source_name,
                    status=status,
                    response_time=response_time,
                    http_status=http_status,
                    error_message=error_message,
                    last_check=datetime.now(),
                    consecutive_failures=consecutive_failures,
                    total_checks=total_checks,
                    success_rate=success_rate,
                    details=details
                )

        # 检查状态变化，触发回调
        if self._on_status_change and source_name in self._results:
            old_status = self._results[source_name].status
            if old_status != status:
                try:
                    self._on_status_change(source_name, old_status, status)
                except Exception as e:
                    logger.error(f"状态变化回调执行失败: {e}")

        return self._results[source_name]

    def get_all_results(self) -> List[HealthCheckResult]:
        """获取所有检查结果"""
        with self._lock:
            return list(self._results.values())

    def get_result(self, source_name: str) -> Optional[HealthCheckResult]:
        """获取指定源的结果"""
        with self._lock:
            return self._results.get(source_name)

    def is_healthy(self, source_name: str) -> bool:
        """检查源是否健康"""
        result = self.get_result(source_name)
        if result is None:
            return True  # 未检查过的默认健康
        return result.status == HealthStatus.HEALTHY

    def get_unhealthy_sources(self) -> List[str]:
        """获取不健康的源列表"""
        with self._lock:
            return [name for name, result in self._results.items()
                   if result.status == HealthStatus.UNHEALTHY]

    def get_stats(self) -> dict:
        """获取健康检查统计"""
        with self._lock:
            total = len(self._results)
            healthy = sum(1 for r in self._results.values() if r.status == HealthStatus.HEALTHY)
            degraded = sum(1 for r in self._results.values() if r.status == HealthStatus.DEGRADED)
            unhealthy = sum(1 for r in self._results.values() if r.status == HealthStatus.UNHEALTHY)

            avg_response_time = 0
            if total > 0:
                avg_response_time = sum(r.response_time for r in self._results.values()) / total

            return {
                'total_sources': total,
                'healthy': healthy,
                'degraded': degraded,
                'unhealthy': unhealthy,
                'avg_response_time_ms': round(avg_response_time, 2),
                'timestamp': datetime.now().isoformat()
            }


class MirrorFailoverManager:
    """镜像源故障切换管理器"""

    def __init__(self, config: dict = None):
        """
        初始化故障切换管理器

        Args:
            config: 配置，包含镜像源列表
        """
        self.config = config or {}
        self.mirrors: Dict[str, Dict] = self.config.get('mirrors', {})

        # 启用故障切换
        self.failover_enabled = self.config.get('failover_enabled', True)
        self.failover_threshold = self.config.get('failover_threshold', 3)  # 连续失败次数

        # 健康检查器
        self.health_checker = HealthChecker(self.config.get('health_check', {}))

        # 当前活跃源
        self._active_source: Dict[str, str] = {}  # mirror_type -> source_name
        self._source_priority: Dict[str, List[str]] = {}  # mirror_type -> [优先列表]

        # 故障切换历史
        self._failover_history: List[dict] = []

        # 回调
        self._on_failover: Optional[Callable] = None

    def set_failover_callback(self, callback: Callable):
        """设置故障切换回调"""
        self._on_failover = callback

    def initialize(self):
        """初始化，确定各镜像类型的首选源"""
        for mirror_type, mirror_config in self.mirrors.items():
            if not isinstance(mirror_config, dict):
                continue

            sources = mirror_config.get('sources', [])
            if sources:
                # 使用配置的优先列表
                self._source_priority[mirror_type] = sources
            else:
                # 使用内置的默认优先列表
                self._source_priority[mirror_type] = self._get_default_priority(mirror_type)

            # 选择首选源
            if self._source_priority[mirror_type]:
                self._active_source[mirror_type] = self._source_priority[mirror_type][0]

    def _get_default_priority(self, mirror_type: str) -> List[str]:
        """获取默认的镜像源优先列表"""
        priorities = {
            'docker': ['docker.io', 'docker.mirrors.aliyun.com', 'dockerhub.azk8s.cn'],
            'apt': ['archive.ubuntu.com', 'mirrors.aliyun.com', 'security.ubuntu.com'],
            'yum': ['mirror.centos.org', 'mirrors.aliyun.com'],
            'pypi': ['pypi.org', 'pypi.mirrors.aliyun.com'],
            'npm': ['registry.npmjs.org', 'registry.npmmirror.com'],
            'go': ['proxy.golang.org', 'goproxy.cn']
        }
        return priorities.get(mirror_type, [])

    def check_all(self) -> Dict[str, HealthCheckResult]:
        """检查所有镜像源"""
        results = {}

        for mirror_type, mirror_config in self.mirrors.items():
            if not isinstance(mirror_config, dict):
                continue

            sources = mirror_config.get('sources', [])
            for source_name in sources:
                if source_name not in results:
                    result = self.health_checker.check_source(source_name, {'url': self._get_source_url(mirror_type, source_name)})
                    results[source_name] = result

        return results

    def _get_source_url(self, mirror_type: str, source_name: str) -> str:
        """获取源 URL"""
        # 从配置中获取
        sources_config = self.mirrors.get(mirror_type, {}).get('sources_config', {})
        if source_name in sources_config:
            return sources_config[source_name].get('url', '')

        # 从 URL 模板生成
        url_template = self.mirrors.get(mirror_type, {}).get('url_template', '')
        if url_template and '{mirror}' in url_template:
            return url_template.replace('{mirror}', source_name)

        return ''

    def get_active_source(self, mirror_type: str) -> Optional[str]:
        """获取当前活跃的镜像源"""
        return self._active_source.get(mirror_type)

    def get_source_for_request(self, mirror_type: str, original_url: str) -> str:
        """
        根据故障切换策略获取请求的源 URL

        Args:
            mirror_type: 镜像类型
            original_url: 原始 URL

        Returns:
            str: 实际请求的 URL
        """
        if not self.failover_enabled:
            return original_url

        active_source = self._active_source.get(mirror_type)
        if not active_source:
            return original_url

        source_url = self._get_source_url(mirror_type, active_source)
        if not source_url:
            return original_url

        # 替换 URL 中的主机部分
        try:
            from urllib.parse import urlparse
            parsed = urlparse(original_url)

            # 构建新 URL
            new_url = f"{parsed.scheme}://{source_url}{parsed.path}"
            if parsed.query:
                new_url += f"?{parsed.query}"

            return new_url
        except Exception:
            return original_url

    def perform_failover(self, mirror_type: str) -> bool:
        """
        对指定镜像类型执行故障切换

        Args:
            mirror_type: 镜像类型

        Returns:
            bool: 是否成功切换
        """
        priority_list = self._source_priority.get(mirror_type, [])
        if not priority_list:
            return False

        current_index = 0
        if mirror_type in self._active_source:
            try:
                current_index = priority_list.index(self._active_source[mirror_type])
            except ValueError:
                pass

        # 查找下一个健康的源
        old_source = self._active_source.get(mirror_type)

        for i in range(current_index + 1, len(priority_list)):
            source_name = priority_list[i]
            result = self.health_checker.get_result(source_name)

            if result and result.status == HealthStatus.HEALTHY:
                self._active_source[mirror_type] = source_name

                # 记录故障切换
                failover_record = {
                    'timestamp': datetime.now().isoformat(),
                    'mirror_type': mirror_type,
                    'old_source': old_source,
                    'new_source': source_name,
                    'reason': 'Health check failed'
                }
                self._failover_history.append(failover_record)

                # 保持历史记录在合理范围内
                if len(self._failover_history) > 100:
                    self._failover_history = self._failover_history[-50:]

                # 触发回调
                if self._on_failover:
                    try:
                        self._on_failover(mirror_type, old_source, source_name)
                    except Exception as e:
                        logger.error(f"故障切换回调执行失败: {e}")

                return True

        return False

    def get_failover_history(self, limit: int = 10) -> List[dict]:
        """获取故障切换历史"""
        return self._failover_history[-limit:]

    def get_health_summary(self) -> dict:
        """获取健康状态摘要"""
        return {
            'failover_enabled': self.failover_enabled,
            'health': self.health_checker.get_stats(),
            'active_sources': self._active_source.copy(),
            'failover_history_count': len(self._failover_history)
        }
