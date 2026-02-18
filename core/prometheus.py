#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Prometheus 指标导出模块
提供 /metrics 端点暴露监控数据
"""

import os
import sys
import time
from datetime import datetime
from typing import Dict, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PrometheusMetrics:
    """Prometheus 指标收集器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._metrics: Dict[str, dict] = {}

        # 初始化指标
        self._init_metrics()

    def _init_metrics(self):
        """初始化指标定义"""
        self._metrics = {
            # 服务器指标
            'hyc_server_uptime_seconds': {
                'type': 'gauge',
                'description': 'Server uptime in seconds',
                'value': 0
            },
            'hyc_server_start_time': {
                'type': 'gauge',
                'description': 'Server start timestamp',
                'value': time.time()
            },

            # 文件指标
            'hyc_files_total': {
                'type': 'gauge',
                'description': 'Total number of files in the system',
                'value': 0
            },
            'hyc_files_size_bytes': {
                'type': 'gauge',
                'description': 'Total size of all files in bytes',
                'value': 0
            },
            'hyc_downloads_total': {
                'type': 'counter',
                'description': 'Total number of downloads',
                'value': 0
            },
            'hyc_downloads_today': {
                'type': 'counter',
                'description': 'Number of downloads today',
                'value': 0
            },

            # 缓存指标
            'hyc_cache_size_bytes': {
                'type': 'gauge',
                'description': 'Current cache size in bytes',
                'value': 0
            },
            'hyc_cache_entries': {
                'type': 'gauge',
                'description': 'Number of cache entries',
                'value': 0
            },
            'hyc_cache_hits_total': {
                'type': 'counter',
                'description': 'Total number of cache hits',
                'value': 0
            },
            'hyc_cache_misses_total': {
                'type': 'counter',
                'description': 'Total number of cache misses',
                'value': 0
            },
            'hyc_cache_hit_ratio': {
                'type': 'gauge',
                'description': 'Cache hit ratio (0-1)',
                'value': 0
            },

            # 同步指标
            'hyc_sync_sources_total': {
                'type': 'gauge',
                'description': 'Total number of sync sources',
                'value': 0
            },
            'hyc_sync_running': {
                'type': 'gauge',
                'description': 'Number of currently running sync operations',
                'value': 0
            },
            'hyc_sync_files_total': {
                'type': 'counter',
                'description': 'Total number of synced files',
                'value': 0
            },
            'hyc_sync_last_timestamp': {
                'type': 'gauge',
                'description': 'Timestamp of last successful sync',
                'value': 0
            },

            # 数据库指标
            'hyc_db_files_total': {
                'type': 'gauge',
                'description': 'Number of files in database',
                'value': 0
            },
            'hyc_db_sync_records': {
                'type': 'gauge',
                'description': 'Number of sync records in database',
                'value': 0
            },
            'hyc_db_cache_records': {
                'type': 'gauge',
                'description': 'Number of cache records in database',
                'value': 0
            },

            # 系统资源指标 (从监控模块获取)
            'hyc_cpu_percent': {
                'type': 'gauge',
                'description': 'CPU usage percentage',
                'value': 0
            },
            'hyc_memory_percent': {
                'type': 'gauge',
                'description': 'Memory usage percentage',
                'value': 0
            },
            'hyc_disk_percent': {
                'type': 'gauge',
                'description': 'Disk usage percentage',
                'value': 0
            },
            'hyc_disk_free_bytes': {
                'type': 'gauge',
                'description': 'Free disk space in bytes',
                'value': 0
            },
            'hyc_disk_total_bytes': {
                'type': 'gauge',
                'description': 'Total disk space in bytes',
                'value': 0
            },
            'hyc_network_rx_bytes': {
                'type': 'counter',
                'description': 'Network receive bytes',
                'value': 0
            },
            'hyc_network_tx_bytes': {
                'type': 'counter',
                'description': 'Network transmit bytes',
                'value': 0
            },
            'hyc_active_connections': {
                'type': 'gauge',
                'description': 'Number of active connections',
                'value': 0
            },

            # 镜像源指标
            'hyc_mirror_enabled': {
                'type': 'gauge',
                'description': 'Whether a mirror is enabled (1=enabled, 0=disabled)',
                'labels': ['mirror_type'],
                'value': {}
            },
            'hyc_mirror_last_sync': {
                'type': 'gauge',
                'description': 'Timestamp of last mirror sync',
                'labels': ['mirror_type'],
                'value': {}
            },
        }

    def set_uptime(self, seconds: float):
        """设置运行时间"""
        self._metrics['hyc_server_uptime_seconds']['value'] = seconds

    def set_files(self, count: int, size_bytes: int):
        """设置文件统计"""
        self._metrics['hyc_files_total']['value'] = count
        self._metrics['hyc_files_size_bytes']['value'] = size_bytes

    def set_downloads(self, total: int, today: int):
        """设置下载统计"""
        self._metrics['hyc_downloads_total']['value'] = total
        self._metrics['hyc_downloads_today']['value'] = today

    def set_cache(self, size_bytes: int, entries: int, hits: int, misses: int):
        """设置缓存统计"""
        self._metrics['hyc_cache_size_bytes']['value'] = size_bytes
        self._metrics['hyc_cache_entries']['value'] = entries
        self._metrics['hyc_cache_hits_total']['value'] = hits
        self._metrics['hyc_cache_misses_total']['value'] = misses

        # 计算命中率
        total = hits + misses
        if total > 0:
            self._metrics['hyc_cache_hit_ratio']['value'] = hits / total
        else:
            self._metrics['hyc_cache_hit_ratio']['value'] = 0

    def set_sync(self, running: int, files_total: int, last_timestamp: float):
        """设置同步统计"""
        self._metrics['hyc_sync_running']['value'] = running
        self._metrics['hyc_sync_files_total']['value'] = files_total
        self._metrics['hyc_sync_last_timestamp']['value'] = last_timestamp

    def set_db_stats(self, files: int, sync_records: int, cache_records: int):
        """设置数据库统计"""
        self._metrics['hyc_db_files_total']['value'] = files
        self._metrics['hyc_db_sync_records']['value'] = sync_records
        self._metrics['hyc_db_cache_records']['value'] = cache_records

    def set_system(self, cpu: float, memory: float, disk: float,
                   disk_free: int, disk_total: int,
                   network_rx: int, network_tx: int):
        """设置系统资源统计"""
        self._metrics['hyc_cpu_percent']['value'] = cpu
        self._metrics['hyc_memory_percent']['value'] = memory
        self._metrics['hyc_disk_percent']['value'] = disk
        self._metrics['hyc_disk_free_bytes']['value'] = disk_free
        self._metrics['hyc_disk_total_bytes']['value'] = disk_total
        self._metrics['hyc_network_rx_bytes']['value'] = network_rx
        self._metrics['hyc_network_tx_bytes']['value'] = network_tx

    def set_connections(self, count: int):
        """设置连接数"""
        self._metrics['hyc_active_connections']['value'] = count

    def set_mirror_status(self, mirror_type: str, enabled: bool, last_sync: float):
        """设置镜像源状态"""
        key = 'hyc_mirror_enabled'
        if 'labels' not in self._metrics[key]:
            self._metrics[key]['labels'] = ['mirror_type']
        if 'value' not in self._metrics[key]:
            self._metrics[key]['value'] = {}
        self._metrics[key]['value'][mirror_type] = 1 if enabled else 0

        key = 'hyc_mirror_last_sync'
        if 'labels' not in self._metrics[key]:
            self._metrics[key]['labels'] = ['mirror_type']
        if 'value' not in self._metrics[key]:
            self._metrics[key]['value'] = {}
        self._metrics[key]['value'][mirror_type] = last_sync

    def increment_downloads(self, count: int = 1):
        """增加下载计数"""
        self._metrics['hyc_downloads_total']['value'] += count

    def increment_cache_hits(self, count: int = 1):
        """增加缓存命中计数"""
        self._metrics['hyc_cache_hits_total']['value'] += count

    def increment_cache_misses(self, count: int = 1):
        """增加缓存未命中计数"""
        self._metrics['hyc_cache_misses_total']['value'] += count

    def increment_sync_files(self, count: int = 1):
        """增加同步文件计数"""
        self._metrics['hyc_sync_files_total']['value'] += count

    def generate_metrics(self) -> str:
        """生成 Prometheus 格式的指标输出"""
        output = []
        output.append("# Prometheus metrics for HYC Mirror Server")
        output.append(f"# Generated at: {datetime.now().isoformat()}")
        output.append("")

        for name, metric in self._metrics.items():
            desc = metric.get('description', '')
            mtype = metric.get('type', 'gauge')

            output.append(f"# TYPE {name} {mtype}")
            output.append(f"# HELP {name} {desc}")

            value = metric.get('value')

            # 处理带标签的指标
            if 'labels' in metric and isinstance(value, dict):
                labels = metric['labels']
                for label_values, v in value.items():
                    if isinstance(label_values, str):
                        label_str = f'{",".join([f"{labels[0]}={label_values}"])}'
                    else:
                        label_str = ','.join([f"{l}={v}" for l, v in zip(labels, label_values)])
                    output.append(f"{name}{{{label_str}}} {v}")
            # 处理普通指标
            elif isinstance(value, dict):
                # 旧格式，可能是直接存储
                for k, v in value.items():
                    output.append(f"{name}{{type=\"{k}\"}} {v}")
            else:
                output.append(f"{name} {value}")

            output.append("")

        return '\n'.join(output)


# ==================== 指标中间件 ====================

class MetricsMiddleware:
    """HTTP 请求指标中间件"""

    def __init__(self, metrics: PrometheusMetrics = None):
        self.metrics = metrics or PrometheusMetrics()
        self._request_count = 0
        self._request_duration_total = 0
        self._errors_4xx = 0
        self._errors_5xx = 0

    def record_request(self, duration: float, status_code: int):
        """记录请求"""
        self._request_count += 1
        self._request_duration_total += duration

        if 400 <= status_code < 500:
            self._errors_4xx += 1
        elif status_code >= 500:
            self._errors_5xx += 1

    def get_request_count(self) -> int:
        return self._request_count

    def get_request_duration_total(self) -> float:
        return self._request_duration_total

    def get_errors_4xx(self) -> int:
        return self._errors_4xx

    def get_errors_5xx(self) -> int:
        return self._errors_5xx

    def update_metrics(self):
        """更新 Prometheus 指标"""
        # 添加请求相关指标
        if 'hyc_http_requests_total' not in self.metrics._metrics:
            self.metrics._metrics['hyc_http_requests_total'] = {
                'type': 'counter',
                'description': 'Total HTTP requests',
                'value': self._request_count
            }
        else:
            self.metrics._metrics['hyc_http_requests_total']['value'] = self._request_count

        if 'hyc_http_request_duration_seconds_total' not in self.metrics._metrics:
            self.metrics._metrics['hyc_http_request_duration_seconds_total'] = {
                'type': 'counter',
                'description': 'Total HTTP request duration in seconds',
                'value': self._request_duration_total
            }
        else:
            self.metrics._metrics['hyc_http_request_duration_seconds_total']['value'] = self._request_duration_total

        if 'hyc_http_requests_4xx_total' not in self.metrics._metrics:
            self.metrics._metrics['hyc_http_requests_4xx_total'] = {
                'type': 'counter',
                'description': 'Total HTTP 4xx errors',
                'value': self._errors_4xx
            }
        else:
            self.metrics._metrics['hyc_http_requests_4xx_total']['value'] = self._errors_4xx

        if 'hyc_http_requests_5xx_total' not in self.metrics._metrics:
            self.metrics._metrics['hyc_http_requests_5xx_total'] = {
                'type': 'counter',
                'description': 'Total HTTP 5xx errors',
                'value': self._errors_5xx
            }
        else:
            self.metrics._metrics['hyc_http_requests_5xx_total']['value'] = self._errors_5xx
