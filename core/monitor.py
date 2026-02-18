#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
系统监控模块 - 提供实时系统监控功能
支持CPU、内存、磁盘、网络等指标的实时采集和历史记录
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any


class SystemMonitor:
    """系统监控器 - 采集和提供系统运行指标"""

    def __init__(self, config: dict):
        self.config = config
        self.base_dir = config.get('base_dir', './downloads')

        # 历史数据配置
        self.history_file = config.get('monitor_history_file', 'monitor_history.json')
        self.history_hours = config.get('monitor_history_hours', 168)  # 默认7天
        self.history = []
        self.history_lock = threading.Lock()

        # SSE客户端管理
        self.sse_clients = {}
        self.sse_lock = threading.Lock()

        # 监控配置
        self.collection_interval = config.get('monitor_interval', 5)  # 采集间隔(秒)
        self.enabled = True

        # 负载历史（用于计算趋势）
        self.load_history = []

        # 加载历史数据
        self._load_history()

    def get_realtime_stats(self) -> dict:
        """获取实时系统状态"""
        import psutil
        import traceback

        stats = {
            "timestamp": datetime.now().isoformat(),
            "errors": []
        }

        try:
            # CPU信息
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            stats["cpu"] = {
                "percent": cpu_percent,
                "count": cpu_count,
                "freq_current": round(cpu_freq.current, 0) if cpu_freq else None,
                "freq_max": round(cpu_freq.max, 0) if cpu_freq else None,
                "freq_min": round(cpu_freq.min, 0) if cpu_freq else None,
                "per_core": psutil.cpu_percent(interval=None, percpu=True)
            }
        except Exception as e:
            stats["cpu"] = {"error": str(e)}
            stats["errors"].append(f"CPU: {str(e)}")

        try:
            # 内存信息
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            stats["memory"] = {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent,
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": swap.percent
            }
        except Exception as e:
            stats["memory"] = {"error": str(e)}
            stats["errors"].append(f"内存: {str(e)}")

        try:
            # 负载平均值（可能在 Termux 中不可用）
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
            if "cpu" in stats:
                stats["cpu"]["load_avg_1m"] = round(load_avg[0], 2)
                stats["cpu"]["load_avg_5m"] = round(load_avg[1], 2)
                stats["cpu"]["load_avg_15m"] = round(load_avg[2], 2)
        except Exception:
            pass

        try:
            # 磁盘信息
            disk_usage = psutil.disk_usage(self.base_dir)
            disk_io = psutil.disk_io_counters()
            stats["disk"] = {
                "total": disk_usage.total,
                "used": disk_usage.used,
                "free": disk_usage.free,
                "percent": disk_usage.percent,
                "read_bytes": disk_io.read_bytes if disk_io else 0,
                "write_bytes": disk_io.write_bytes if disk_io else 0,
                "read_count": disk_io.read_count if disk_io else 0,
                "write_count": disk_io.write_count if disk_io else 0
            }
        except Exception as e:
            stats["disk"] = {"error": str(e)}
            stats["errors"].append(f"磁盘: {str(e)}")

        try:
            # 网络信息（可能在受限环境中失败）
            net_io = psutil.net_io_counters()
            connections = psutil.net_connections()
            stats["network"] = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "connections_count": len(connections),
                "connections_established": len([c for c in connections if c.status == 'ESTABLISHED'])
            }
        except PermissionError as e:
            stats["network"] = {
                "note": "权限不足，无法访问网络信息",
                "error": str(e)
            }
        except Exception as e:
            stats["network"] = {"error": str(e)}
            stats["errors"].append(f"网络: {str(e)}")

        try:
            # 进程信息
            process = psutil.Process()
            proc_mem = process.memory_info()
            proc_cpu = process.cpu_percent(interval=0.1)
            stats["process"] = {
                "memory_rss": proc_mem.rss,
                "memory_vms": proc_mem.vms,
                "cpu_percent": proc_cpu,
                "thread_count": process.num_threads(),
                "open_files": process.num_fds() if hasattr(process, 'num_fds') else 0
            }
        except Exception as e:
            stats["process"] = {"error": str(e)}
            stats["errors"].append(f"进程: {str(e)}")

        # 计算运行时间
        try:
            uptime = time.time() - self.config.get('start_time', time.time())
            stats["uptime"] = round(uptime, 2)
        except Exception:
            stats["uptime"] = None

        return stats

    def get_monitor_history(self, hours: int = 24) -> dict:
        """获取历史监控数据"""
        cutoff_time = time.time() - (hours * 3600)

        with self.history_lock:
            filtered_history = [
                point for point in self.history
                if point.get('timestamp_unix', 0) >= cutoff_time
            ]

            return {
                "hours": hours,
                "total_points": len(filtered_history),
                "data": filtered_history
            }

    def get_stats_summary(self) -> dict:
        """获取统计摘要"""
        history = self.get_monitor_history(24).get('data', [])

        if not history:
            return {
                "status": "no_data",
                "message": "暂无监控数据"
            }

        # 计算各项指标的平均值和最大值
        cpu_values = [p.get('cpu', {}).get('percent', 0) for p in history]
        memory_values = [p.get('memory', {}).get('percent', 0) for p in history]
        disk_values = [p.get('disk', {}).get('percent', 0) for p in history]

        return {
            "status": "ok",
            "period_hours": 24,
            "cpu": {
                "avg": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else 0,
                "max": max(cpu_values) if cpu_values else 0,
                "min": min(cpu_values) if cpu_values else 0
            },
            "memory": {
                "avg": round(sum(memory_values) / len(memory_values), 1) if memory_values else 0,
                "max": max(memory_values) if memory_values else 0,
                "min": min(memory_values) if memory_values else 0
            },
            "disk": {
                "avg": round(sum(disk_values) / len(disk_values), 1) if disk_values else 0,
                "max": max(disk_values) if disk_values else 0,
                "min": min(disk_values) if disk_values else 0
            },
            "total_downloads": history[-1].get('downloads', {}).get('total', 0) if history else 0,
            "total_connections": sum(p.get('network', {}).get('connections_count', 0) for p in history)
        }

    def start_monitoring(self, callback=None):
        """启动监控循环（后台线程）"""
        def monitor_loop():
            while self.enabled:
                try:
                    stats = self.get_realtime_stats()

                    # 添加时间戳
                    stats['timestamp_unix'] = time.time()

                    # 保存历史
                    self._add_history_point(stats)

                    # SSE广播
                    if callback:
                        callback(stats)
                    self._broadcast_sse('stats', stats)

                except Exception as e:
                    print(f"监控采集错误: {e}")

                time.sleep(self.collection_interval)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        return thread

    def stop_monitoring(self):
        """停止监控"""
        self.enabled = False

    def register_sse_client(self, client_id: str, topics: List[str] = None) -> None:
        """注册SSE客户端"""
        with self.sse_lock:
            self.sse_clients[client_id] = {
                'topics': set(topics) if topics else {'*'},
                'last_ping': time.time()
            }

    def unregister_sse_client(self, client_id: str) -> None:
        """注销SSE客户端"""
        with self.sse_lock:
            self.sse_clients.pop(client_id, None)

    def get_sse_clients_count(self) -> int:
        """获取SSE客户端数量"""
        with self.sse_lock:
            return len(self.sse_clients)

    def broadcast_event(self, event_type: str, data: dict) -> None:
        """广播事件到所有SSE客户端"""
        self._broadcast_sse(event_type, data)

    def _broadcast_sse(self, event_type: str, data: dict) -> None:
        """SSE广播（内部方法）"""
        message = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        with self.sse_lock:
            disconnected = []
            for client_id, client in self.sse_clients.items():
                try:
                    if client['topics'] == {'*'} or event_type in client['topics']:
                        # 实际发送需要在request handler中处理
                        # 这里只记录消息
                        pass
                except Exception:
                    disconnected.append(client_id)

            # 清理断开的客户端
            for client_id in disconnected:
                self.sse_clients.pop(client_id, None)

    def _add_history_point(self, stats: dict) -> None:
        """添加历史数据点"""
        # 精简数据以减少存储
        point = {
            "timestamp": stats.get('timestamp'),
            "timestamp_unix": stats.get('timestamp_unix'),
            "cpu_percent": stats.get('cpu', {}).get('percent', 0),
            "memory_percent": stats.get('memory', {}).get('percent', 0),
            "disk_percent": stats.get('disk', {}).get('percent', 0),
            "network_bytes_sent": stats.get('network', {}).get('bytes_sent', 0),
            "network_bytes_recv": stats.get('network', {}).get('bytes_recv', 0),
            "connections_count": stats.get('network', {}).get('connections_count', 0),
            "load_avg_1m": stats.get('cpu', {}).get('load_avg_1m', 0)
        }

        with self.history_lock:
            self.history.append(point)

            # 清理过期数据
            cutoff_time = time.time() - (self.history_hours * 3600)
            self.history = [
                p for p in self.history
                if p.get('timestamp_unix', 0) >= cutoff_time
            ]

            # 保存到文件
            self._save_history()

    def _save_history(self) -> None:
        """保存历史数据到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存监控历史失败: {e}")

    def _load_history(self) -> None:
        """从文件加载历史数据"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.history = data[-10000:]  # 限制历史数量
        except Exception as e:
            print(f"加载监控历史失败: {e}")
            self.history = []

    def get_health_status(self) -> dict:
        """获取健康状态"""
        stats = self.get_realtime_stats()

        if 'error' in stats:
            return {
                "status": "unhealthy",
                "error": stats['error']
            }

        # 检查各项指标
        warnings = []

        cpu_percent = stats.get('cpu', {}).get('percent', 0)
        if cpu_percent > 90:
            warnings.append(f"CPU使用率过高: {cpu_percent}%")
        elif cpu_percent > 70:
            warnings.append(f"CPU使用率较高: {cpu_percent}%")

        memory_percent = stats.get('memory', {}).get('percent', 0)
        if memory_percent > 90:
            warnings.append(f"内存使用率过高: {memory_percent}%")
        elif memory_percent > 80:
            warnings.append(f"内存使用率较高: {memory_percent}%")

        disk_percent = stats.get('disk', {}).get('percent', 0)
        if disk_percent > 90:
            warnings.append(f"磁盘使用率过高: {disk_percent}%")
        elif disk_percent > 80:
            warnings.append(f"磁盘使用率较高: {disk_percent}%")

        if warnings:
            return {
                "status": "degraded",
                "warnings": warnings,
                "timestamp": stats.get('timestamp')
            }

        return {
            "status": "healthy",
            "timestamp": stats.get('timestamp')
        }
