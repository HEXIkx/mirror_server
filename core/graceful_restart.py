#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
平滑重启模块
支持优雅停止、零停机重启、滚动更新
"""

import os
import sys
import signal
import time
import threading
import logging
import subprocess
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RestartStrategy(Enum):
    """重启策略"""
    GRACEFUL = "graceful"  # 优雅停止，等待请求完成
    ROLLING = "rolling"     # 滚动更新，零停机
    IMMEDIATE = "immediate" # 立即重启


class ServerState(Enum):
    """服务器状态"""
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    STARTING = "starting"
    RESTARTING = "restarting"


@dataclass
class PendingRequest:
    """待处理的请求"""
    request_id: str
    start_time: float
    endpoint: str
    method: str
    client_address: tuple


class GracefulRestartManager:
    """平滑重启管理器"""

    def __init__(self, config: Dict = None):
        """
        初始化平滑重启管理器

        Args:
            config: 重启配置
        """
        self.config = config or {}
        self.state = ServerState.STOPPED

        # 等待超时时间
        self.graceful_timeout = self.config.get('graceful_timeout', 30)  # 秒
        self.shutdown_timeout = self.config.get('shutdown_timeout', 10)  # 秒

        # 待处理请求追踪
        self._pending_requests: Dict[str, PendingRequest] = {}
        self._requests_lock = threading.Lock()

        # 请求计数器
        self._request_counter = 0
        self._counter_lock = threading.Lock()

        # 回调函数
        self._on_prepare_restart: Optional[Callable] = None
        self._on_start_restart: Optional[Callable] = None
        self._on_complete_restart: Optional[Callable] = None
        self._on_restart_failed: Optional[Callable] = None

        # 状态锁
        self._state_lock = threading.Lock()

        # 重启历史
        self._restart_history: List[Dict] = []
        self._history_lock = threading.Lock()

        # 信号处理器
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGHUP, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """处理退出信号"""
        signal_names = {
            signal.SIGTERM: 'SIGTERM',
            signal.SIGINT: 'SIGINT',
            signal.SIGHUP: 'SIGHUP'
        }
        sig_name = signal_names.get(signum, str(signum))
        logger.info(f"收到信号 {sig_name}，准备优雅关闭")

        # 设置状态为停止中
        self.state = ServerState.STOPPING

    def register_request(self, endpoint: str, method: str, client: tuple) -> str:
        """
        注册一个待处理的请求

        Args:
            endpoint: 请求端点
            method: 请求方法
            client: 客户端地址

        Returns:
            请求 ID
        """
        with self._counter_lock:
            self._request_counter += 1
            request_id = f"req_{self._request_counter}_{int(time.time())}"

        request = PendingRequest(
            request_id=request_id,
            start_time=time.time(),
            endpoint=endpoint,
            method=method,
            client_address=client
        )

        with self._requests_lock:
            self._pending_requests[request_id] = request

        return request_id

    def complete_request(self, request_id: str):
        """标记请求完成"""
        with self._requests_lock:
            self._pending_requests.pop(request_id, None)

    def get_pending_count(self) -> int:
        """获取待处理请求数量"""
        with self._requests_lock:
            return len(self._pending_requests)

    def get_pending_requests(self) -> List[Dict]:
        """获取待处理请求详情"""
        with self._requests_lock:
            return [
                {
                    'request_id': r.request_id,
                    'endpoint': r.endpoint,
                    'method': r.method,
                    'duration': round(time.time() - r.start_time, 2),
                    'client': str(r.client_address[0]) if r.client_address else 'unknown'
                }
                for r in self._pending_requests.values()
            ]

    def is_safe_to_restart(self) -> bool:
        """检查是否安全重启（没有待处理请求）"""
        return self.get_pending_count() == 0

    def wait_for_requests(
        self,
        timeout: int = None,
        progress_callback: Callable[[int, int], None] = None
    ) -> bool:
        """
        等待所有请求完成

        Args:
            timeout: 超时时间（秒）
            progress_callback: 进度回调函数(remaining, total)

        Returns:
            是否在超时前完成所有请求
        """
        timeout = timeout or self.graceful_timeout
        start_time = time.time()

        while time.time() - start_time < timeout:
            pending = self.get_pending_count()

            if progress_callback:
                progress_callback(pending, 0)

            if pending == 0:
                return True

            time.sleep(0.5)

        return False

    def set_prepare_restart_callback(self, callback: Callable):
        """设置准备重启回调"""
        self._on_prepare_restart = callback

    def set_start_restart_callback(self, callback: Callable):
        """设置开始重启回调"""
        self._on_start_restart = callback

    def set_complete_restart_callback(self, callback: Callable):
        """设置完成重启回调"""
        self._on_complete_restart = callback

    def set_restart_failed_callback(self, callback: Callable):
        """设置重启失败回调"""
        self._on_restart_failed = callback

    def prepare_restart(self) -> Dict:
        """
        准备重启（通知各模块准备）

        Returns:
            准备结果
        """
        with self._state_lock:
            self.state = ServerState.STOPPING

        result = {
            'success': True,
            'pending_requests': self.get_pending_count(),
            'message': ''
        }

        # 通知回调
        if self._on_prepare_restart:
            try:
                self._on_prepare_restart()
            except Exception as e:
                logger.error(f"Prepare restart callback failed: {e}")
                result['success'] = False
                result['message'] = str(e)

        return result

    def perform_restart(
        self,
        strategy: RestartStrategy = RestartStrategy.GRACEFUL,
        new_config: Dict = None,
        script_path: str = None
    ) -> Dict:
        """
        执行重启

        Args:
            strategy: 重启策略
            new_config: 新配置（用于配置热更新）
            script_path: 服务器脚本路径

        Returns:
            重启结果
        """
        with self._state_lock:
            if self.state == ServerState.RESTARTING:
                return {
                    'success': False,
                    'error': 'Restart already in progress'
                }
            self.state = ServerState.RESTARTING

        start_time = time.time()
        result = {
            'success': False,
            'strategy': strategy.value,
            'elapsed_seconds': 0,
            'message': ''
        }

        try:
            # 准备阶段
            prepare_result = self.prepare_restart()
            if not prepare_result['success']:
                result['message'] = f"Prepare failed: {prepare_result['message']}"
                self.state = ServerState.RUNNING
                return result

            # 根据策略执行重启
            if strategy == RestartStrategy.GRACEFUL:
                result = self._graceful_restart(prepare_result)
            elif strategy == RestartStrategy.ROLLING:
                result = self._rolling_restart(script_path, new_config)
            elif strategy == RestartStrategy.IMMEDIATE:
                result = self._immediate_restart(script_path)

            result['elapsed_seconds'] = round(time.time() - start_time, 2)

            # 记录重启历史
            self._add_to_history(result)

        except Exception as e:
            logger.error(f"Restart failed: {e}")
            result['success'] = False
            result['message'] = str(e)
            self.state = ServerState.RUNNING

            if self._on_restart_failed:
                try:
                    self._on_restart_failed(str(e))
                except Exception:
                    pass

        return result

    def _graceful_restart(self, prepare_result: Dict) -> Dict:
        """优雅重启（等待请求完成）"""
        result = {
            'success': True,
            'strategy': 'graceful',
            'pending_requests': prepare_result['pending_requests'],
            'message': ''
        }

        # 等待请求完成
        pending = prepare_result['pending_requests']
        if pending > 0:
            logger.info(f"等待 {pending} 个请求完成，超时 {self.graceful_timeout} 秒")

            def progress_callback(remaining, total):
                if remaining % 5 == 0:
                    logger.info(f"还有 {remaining} 个请求待处理")

            success = self.wait_for_requests(
                timeout=self.graceful_timeout,
                progress_callback=progress_callback
            )

            if not success:
                remaining = self.get_pending_count()
                result['success'] = False
                result['message'] = f"{remaining} 个请求未在 {self.graceful_timeout} 秒内完成"
                logger.warning(result['message'])
                self.state = ServerState.RUNNING
                return result

            result['message'] = '所有请求已完成'
            logger.info('所有请求已完成')

        # 通知开始重启
        if self._on_start_restart:
            try:
                self._on_start_restart()
            except Exception as e:
                logger.error(f"Start restart callback failed: {e}")

        result['success'] = True
        result['message'] = 'Graceful restart prepared'
        self.state = ServerState.STOPPED

        return result

    def _rolling_restart(self, script_path: str, new_config: Dict = None) -> Dict:
        """滚动重启（零停机）"""
        result = {
            'success': True,
            'strategy': 'rolling',
            'message': ''
        }

        if not script_path:
            script_path = os.path.join(os.path.dirname(__file__), '..', 'main.py')

        script_path = os.path.abspath(script_path)

        # 检查是否有新配置需要应用
        if new_config:
            result['config_updated'] = True
            logger.info("配置将在重启后应用")
        else:
            result['config_updated'] = False

        # 通知开始重启
        if self._on_start_restart:
            try:
                self._on_start_restart()
            except Exception as e:
                logger.error(f"Start restart callback failed: {e}")

        # 启动新进程（在同一端口，但使用不同进程ID）
        # 注意：实际实现需要在负载均衡器层面处理
        logger.info("滚动重启：建议在负载均衡器层面处理零停机")

        self.state = ServerState.STOPPED
        result['message'] = 'Rolling restart prepared - use load balancer for zero-downtime'

        return result

    def _immediate_restart(self, script_path: str = None) -> Dict:
        """立即重启"""
        result = {
            'success': True,
            'strategy': 'immediate',
            'message': ''
        }

        if not script_path:
            script_path = os.path.join(os.path.dirname(__file__), '..', 'main.py')

        script_path = os.path.abspath(script_path)

        # 通知开始重启
        if self._on_start_restart:
            try:
                self._on_start_restart()
            except Exception as e:
                logger.error(f"Start restart callback failed: {e}")

        # 发送重启信号给主进程
        logger.info("立即重启服务器")

        # 在子进程中重启
        try:
            # 启动新进程
            cmd = [sys.executable, script_path]
            env = os.environ.copy()
            env['HYC_RESTARTED'] = '1'

            subprocess.Popen(cmd, env=env)

            self.state = ServerState.STOPPED
            result['message'] = 'Immediate restart initiated'

        except Exception as e:
            result['success'] = False
            result['message'] = f"Failed to restart: {str(e)}"
            self.state = ServerState.RUNNING

        return result

    def _add_to_history(self, result: Dict):
        """添加重启历史记录"""
        record = {
            'timestamp': datetime.now().isoformat(),
            'strategy': result.get('strategy', 'unknown'),
            'success': result.get('success', False),
            'elapsed_seconds': result.get('elapsed_seconds', 0),
            'message': result.get('message', '')
        }

        with self._history_lock:
            self._restart_history.append(record)
            # 只保留最近 20 条记录
            self._restart_history = self._restart_history[-20:]

    def get_restart_history(self) -> List[Dict]:
        """获取重启历史"""
        with self._history_lock:
            return list(self._restart_history)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'state': self.state.value,
            'pending_requests': self.get_pending_count(),
            'graceful_timeout': self.graceful_timeout,
            'shutdown_timeout': self.shutdown_timeout,
            'restart_count': len(self._restart_history),
            'recent_restarts': self.get_restart_history()[-5:]
        }

    def update_config(self, new_config: Dict):
        """更新配置（热更新）"""
        if 'graceful_timeout' in new_config:
            self.graceful_timeout = new_config['graceful_timeout']
        if 'shutdown_timeout' in new_config:
            self.shutdown_timeout = new_config['shutdown_timeout']

        logger.info(f"重启配置已更新: timeout={self.graceful_timeout}s")


class ServerHealthChecker:
    """服务器健康检查器"""

    def __init__(self, host: str = 'localhost', port: int = 8080):
        self.host = host
        self.port = port
        self._last_check = None
        self._is_healthy = False

    def check(self) -> Dict:
        """
        检查服务器健康状态

        Returns:
            健康检查结果
        """
        import socket

        result = {
            'healthy': False,
            'latency_ms': 0,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }

        try:
            start_time = time.time()

            # 尝试连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.host, self.port))
            sock.close()

            result['latency_ms'] = round((time.time() - start_time) * 1000, 2)
            result['healthy'] = True

        except Exception as e:
            result['error'] = str(e)

        self._last_check = result
        return result

    def get_latency(self) -> float:
        """获取延迟（毫秒）"""
        if self._last_check:
            return self._last_check.get('latency_ms', 0)
        return 0


class RollingRestartManager:
    """滚动重启管理器（支持多实例）"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.instances: Dict[str, Dict] = {}  # instance_id -> info
        self.current_instance_id = None
        self._lock = threading.Lock()

    def register_instance(self, instance_id: str, info: Dict):
        """注册实例"""
        with self._lock:
            self.instances[instance_id] = {
                **info,
                'registered_at': datetime.now().isoformat(),
                'status': 'active'
            }

    def unregister_instance(self, instance_id: str):
        """注销实例"""
        with self._lock:
            if instance_id in self.instances:
                self.instances[instance_id]['status'] = 'draining'

    def get_active_instances(self) -> List[str]:
        """获取活跃实例列表"""
        with self._lock:
            return [
                i for i, info in self.instances.items()
                if info['status'] == 'active'
            ]

    def perform_rolling_restart(
        self,
        instance_id: str,
        restart_func: Callable
    ) -> Dict:
        """
        对单个实例执行滚动重启

        Args:
            instance_id: 实例 ID
            restart_func: 重启函数

        Returns:
            重启结果
        """
        with self._lock:
            if instance_id not in self.instances:
                return {
                    'success': False,
                    'error': f'Instance {instance_id} not found'
                }

        # 标记为排水中
        self.instances[instance_id]['status'] = 'draining'

        # 等待连接耗尽
        time.sleep(5)

        # 执行重启
        try:
            restart_func(instance_id)

            self.instances[instance_id]['status'] = 'active'
            self.instances[instance_id]['restarted_at'] = datetime.now().isoformat()

            return {
                'success': True,
                'instance_id': instance_id
            }

        except Exception as e:
            self.instances[instance_id]['status'] = 'error'
            return {
                'success': False,
                'instance_id': instance_id,
                'error': str(e)
            }
