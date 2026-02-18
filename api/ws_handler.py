#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WebSocket处理器模块
提供双向实时通信功能
"""

import json
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Set, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class WebSocketClient:
    """WebSocket客户端"""
    client_id: str
    connection: any  # WebSocket连接对象
    topics: Set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class WebSocketManager:
    """WebSocket连接管理器"""

    # 预定义主题
    TOPIC_MONITOR_CPU = 'monitor:cpu'
    TOPIC_MONITOR_MEMORY = 'monitor:memory'
    TOPIC_MONITOR_DISK = 'monitor:disk'
    TOPIC_MONITOR_NETWORK = 'monitor:network'
    TOPIC_MONITOR_ALL = 'monitor:*'
    TOPIC_SYNC_PROGRESS = 'sync:progress'
    TOPIC_SYNC_STATUS = 'sync:status'
    TOPIC_SYNC_ALL = 'sync:*'
    TOPIC_DOWNLOAD_PROGRESS = 'download:progress'
    TOPIC_DOWNLOAD_STATUS = 'download:status'
    TOPIC_DOWNLOAD_ALL = 'download:*'
    TOPIC_SERVER_STATUS = 'server:status'
    TOPIC_ALL = '*'

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.clients: Dict[str, WebSocketClient] = {}
        self.lock = threading.Lock()
        self._running = False

        # 消息队列（用于批量发送）
        self.message_queues: Dict[str, list] = {}

        # 心跳间隔（秒）
        self.heartbeat_interval = 30

        # 统计
        self.stats = {
            'total_connections': 0,
            'total_messages_sent': 0,
            'total_messages_received': 0
        }

    def register_client(self, client_id: str, connection, metadata: dict = None) -> WebSocketClient:
        """注册新客户端"""
        with self.lock:
            client = WebSocketClient(
                client_id=client_id,
                connection=connection,
                topics={self.TOPIC_ALL},  # 默认订阅所有
                metadata=metadata or {}
            )
            self.clients[client_id] = client
            self.stats['total_connections'] += 1

            # 启动心跳
            self._start_heartbeat(client_id)

            return client

    def unregister_client(self, client_id: str):
        """注销客户端"""
        with self.lock:
            client = self.clients.pop(client_id, None)
            if client:
                self.message_queues.pop(client_id, None)

    def subscribe(self, client_id: str, *topics: str):
        """订阅主题"""
        with self.lock:
            client = self.clients.get(client_id)
            if client:
                client.topics.update(topics)

    def unsubscribe(self, client_id: str, *topics: str):
        """取消订阅"""
        with self.lock:
            client = self.clients.get(client_id)
            if client:
                for topic in topics:
                    client.topics.discard(topic)

    def is_subscribed(self, client_id: str, topic: str) -> bool:
        """检查客户端是否订阅了主题"""
        with self.lock:
            client = self.clients.get(client_id)
            if not client:
                return False

            if self.TOPIC_ALL in client.topics:
                return True

            # 检查精确匹配或通配符匹配
            if topic in client.topics:
                return True

            # 检查通配符匹配
            topic_parts = topic.split(':')
            for subscribed_topic in client.topics:
                if subscribed_topic.endswith('*'):
                    prefix = subscribed_topic.rstrip('*').rstrip(':')
                    if topic.startswith(prefix):
                        return True

            return False

    def send_to_client(self, client_id: str, event_type: str, data: dict, callback: Callable = None):
        """发送消息到指定客户端"""
        with self.lock:
            client = self.clients.get(client_id)
            if not client:
                return False

            message = self._format_message(event_type, data)

            try:
                if hasattr(client.connection, 'send'):
                    client.connection.send(message)
                    self.stats['total_messages_sent'] += 1
                    client.last_activity = time.time()

                    if callback:
                        callback(client_id, True)
                    return True
                else:
                    # 放入消息队列
                    if client_id not in self.message_queues:
                        self.message_queues[client_id] = []
                    self.message_queues[client_id].append(message)

                    if callback:
                        callback(client_id, True)
                    return True

            except Exception as e:
                print(f"WebSocket发送失败 {client_id}: {e}")
                if callback:
                    callback(client_id, False)
                return False

    def broadcast(self, event_type: str, data: dict, topic: str = None):
        """广播消息到所有客户端"""
        with self.lock:
            sent_count = 0
            failed_clients = []

            for client_id, client in self.clients.items():
                # 检查是否匹配主题
                if topic and not self.is_subscribed(client_id, topic):
                    continue

                message = self._format_message(event_type, data)

                try:
                    if hasattr(client.connection, 'send'):
                        client.connection.send(message)
                        sent_count += 1
                    else:
                        if client_id not in self.message_queues:
                            self.message_queues[client_id] = []
                        self.message_queues[client_id].append(message)
                        sent_count += 1

                    client.last_activity = time.time()

                except Exception as e:
                    print(f"广播到 {client_id} 失败: {e}")
                    failed_clients.append(client_id)

            self.stats['total_messages_sent'] += sent_count

            # 清理失败的客户端
            for client_id in failed_clients:
                self.unregister_client(client_id)

            return sent_count

    def broadcast_to_topic(self, topic: str, event_type: str, data: dict):
        """广播到订阅特定主题的客户端"""
        with self.lock:
            sent_count = 0

            for client_id, client in self.clients.items():
                if self.is_subscribed(client_id, topic):
                    message = self._format_message(event_type, data)

                    try:
                        if hasattr(client.connection, 'send'):
                            client.connection.send(message)
                            sent_count += 1
                        else:
                            if client_id not in self.message_queues:
                                self.message_queues[client_id] = []
                            self.message_queues[client_id].append(message)
                            sent_count += 1

                    except Exception as e:
                        print(f"发送到 {client_id} 失败: {e}")

            return sent_count

    def broadcast_monitor_update(self, stats: dict):
        """广播监控更新"""
        # 提取关键指标
        cpu_percent = stats.get('cpu', {}).get('percent', 0)
        memory_percent = stats.get('memory', {}).get('percent', 0)
        disk_percent = stats.get('disk', {}).get('percent', 0)

        # 按阈值过滤
        if cpu_percent > 0 or memory_percent > 0 or disk_percent > 0:
            self.broadcast('monitor:stats', stats, 'monitor:*')

    def broadcast_sync_progress(self, task_id: str, progress: dict):
        """广播同步进度"""
        self.broadcast('sync:progress', progress, 'sync:*')

    def broadcast_download_progress(self, download_id: str, progress: dict):
        """广播下载进度"""
        self.broadcast('download:progress', progress, 'download:*')

    def get_client_count(self) -> int:
        """获取客户端数量"""
        with self.lock:
            return len(self.clients)

    def get_client_topics(self, client_id: str) -> Set[str]:
        """获取客户端订阅的主题"""
        with self.lock:
            client = self.clients.get(client_id)
            return client.topics.copy() if client else set()

    def get_all_topics(self) -> Set[str]:
        """获取所有被订阅的主题"""
        with self.lock:
            topics = set()
            for client in self.clients.values():
                topics.update(client.topics)
            return topics

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self.lock:
            return {
                **self.stats,
                'connected_clients': len(self.clients),
                'active_topics': len(self.get_all_topics()),
                'queues_queued': sum(len(q) for q in self.message_queues.values())
            }

    def _format_message(self, event_type: str, data: dict) -> str:
        """格式化消息"""
        return json.dumps({
            'type': event_type,
            'timestamp': time.time(),
            'data': data
        }, ensure_ascii=False)

    def _start_heartbeat(self, client_id: str):
        """启动心跳"""
        def heartbeat():
            while client_id in self.clients:
                try:
                    # 发送心跳
                    self.send_to_client(
                        client_id,
                        'ping',
                        {'timestamp': time.time()}
                    )
                except Exception:
                    break

                time.sleep(self.heartbeat_interval)

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()

    def generate_client_id(self) -> str:
        """生成客户端ID"""
        return f"ws_{uuid.uuid4().hex[:12]}"

    def process_messages(self, client_id: str, messages: list):
        """处理客户端消息"""
        for message in messages:
            self._handle_message(client_id, message)

    def _handle_message(self, client_id: str, message: str):
        """处理客户端消息"""
        self.stats['total_messages_received'] += 1

        try:
            data = json.loads(message)

            event_type = data.get('type')
            payload = data.get('data', {})

            if event_type == 'subscribe':
                # 订阅主题
                topics = payload.get('topics', [])
                self.subscribe(client_id, *topics)

            elif event_type == 'unsubscribe':
                # 取消订阅
                topics = payload.get('topics', [])
                self.unsubscribe(client_id, *topics)

            elif event_type == 'ping':
                # 心跳响应
                self.send_to_client(client_id, 'pong', {'timestamp': time.time()})

            elif event_type == 'status':
                # 请求状态 - 返回服务器和客户端状态
                response_data = {'status': 'ok'}

                if payload.get('monitor'):
                    # 获取实时监控数据
                    try:
                        if handler.monitor:
                            response_data['monitor'] = handler.monitor.get_realtime_stats()
                        else:
                            # 回退到直接使用 psutil
                            import psutil
                            response_data['monitor'] = {
                                'timestamp': datetime.now().isoformat(),
                                'cpu': {
                                    'percent': psutil.cpu_percent(interval=0.1),
                                    'count': psutil.cpu_count()
                                },
                                'memory': psutil.virtual_memory()._asdict(),
                                'disk': psutil.disk_usage(handler.config.get('base_dir', './downloads'))._asdict()
                            }
                    except Exception as e:
                        response_data['monitor'] = {'error': str(e)}

                if payload.get('ws'):
                    # 获取 WebSocket 统计
                    response_data['ws'] = self.get_stats()

                if payload.get('client'):
                    # 获取当前客户端信息
                    client = self.clients.get(client_id)
                    if client:
                        response_data['client'] = {
                            'client_id': client.client_id,
                            'connected_at': client.connected_at,
                            'last_activity': client.last_activity,
                            'topics': list(client.topics),
                            'metadata': client.metadata
                        }

                self.send_to_client(client_id, 'status:response', response_data)

            elif event_type == 'sync':
                # 同步相关操作
                sync_action = payload.get('action', 'status')

                if sync_action == 'status':
                    # 获取同步状态
                    response_data = {'action': 'status'}
                    try:
                        from core.sync_scheduler import SyncScheduler
                        scheduler = SyncScheduler()
                        response_data['sync_status'] = scheduler.get_status() if hasattr(scheduler, 'get_status') else {'message': 'sync scheduler running'}
                    except Exception as e:
                        response_data['sync_status'] = {'error': str(e)}

                    self.send_to_client(client_id, 'sync:response', response_data)

                elif sync_action == 'list':
                    # 获取同步任务列表
                    response_data = {'action': 'list'}
                    self.send_to_client(client_id, 'sync:response', response_data)

                elif sync_action == 'trigger':
                    # 触发手动同步
                    response_data = {'action': 'trigger', 'status': 'pending'}
                    self.send_to_client(client_id, 'sync:response', response_data)

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"处理WebSocket消息失败: {e}")
