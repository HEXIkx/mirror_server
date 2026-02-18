#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SSE (Server-Sent Events) 处理器模块
提供单向事件推送功能
"""

import json
import threading
import time
import uuid
from typing import Dict, Set, Optional
from dataclasses import dataclass, field


@dataclass
class SSEClient:
    """SSE客户端"""
    client_id: str
    handler: any  # HTTP请求处理器
    topics: Set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    running: bool = False


class SSEHandler:
    """SSE事件处理器"""

    # 预定义事件类型
    EVENT_STATS = 'stats'
    EVENT_MONITOR = 'monitor'
    EVENT_SYNC = 'sync'
    EVENT_DOWNLOAD = 'download'
    EVENT_SERVER = 'server'
    EVENT_ERROR = 'error'
    EVENT_PING = 'ping'

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.clients: Dict[str, SSEClient] = {}
        self.lock = threading.Lock()

        # 心跳配置
        self.heartbeat_interval = 30  # 秒
        self.retry_interval = 3000  # 毫秒（客户端重连间隔）

        # 消息缓冲区
        self.message_buffer_size = 100

        # 统计
        self.stats = {
            'total_connections': 0,
            'total_events_sent': 0,
            'total_bytes_sent': 0
        }

    def handle_connection(self, handler, topics: list = None) -> Optional[str]:
        """
        处理新的SSE连接
        返回客户端ID
        """
        client_id = self._generate_client_id()

        # 设置SSE响应头
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        handler.send_header('Connection', 'keep-alive')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('X-Accel-Buffering', 'no')  # 禁用Nginx缓冲
        handler.end_headers()

        # 创建客户端
        client = SSEClient(
            client_id=client_id,
            handler=handler,
            topics=set(topics) if topics else {self.EVENT_STATS, self.EVENT_SYNC}
        )

        with self.lock:
            self.clients[client_id] = client
            self.stats['total_connections'] += 1

        # 启动心跳
        client.running = True
        self._start_heartbeat(client_id)

        # 发送初始连接事件
        self._send_event(client, self.EVENT_SERVER, {
            'type': 'connected',
            'client_id': client_id,
            'timestamp': time.time(),
            'topics': list(client.topics)
        })

        return client_id

    def close_connection(self, client_id: str):
        """关闭连接"""
        with self.lock:
            client = self.clients.pop(client_id, None)
            if client:
                client.running = False

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

    def is_subscribed(self, client_id: str, event_type: str) -> bool:
        """检查是否订阅了事件类型"""
        with self.lock:
            client = self.clients.get(client_id)
            if not client:
                return False
            return event_type in client.topics or '*' in client.topics

    def send_event(self, client_id: str, event_type: str, data: dict):
        """发送事件到指定客户端"""
        with self.lock:
            client = self.clients.get(client_id)
            if not client or not client.running:
                return False

            if event_type not in client.topics and '*' not in client.topics:
                return False

            return self._send_event(client, event_type, data)

    def broadcast(self, event_type: str, data: dict, topic: str = None):
        """广播事件到所有客户端"""
        with self.lock:
            sent_count = 0
            dead_clients = []

            for client_id, client in self.clients.items():
                if not client.running:
                    dead_clients.append(client_id)
                    continue

                # 检查主题匹配
                if topic and event_type != topic:
                    continue

                if self._send_event(client, event_type, data):
                    sent_count += 1

            # 清理死掉的客户端
            for client_id in dead_clients:
                self.clients.pop(client_id, None)

            return sent_count

    def broadcast_to_topic(self, topic: str, event_type: str, data: dict):
        """广播到订阅特定主题的客户端"""
        self.broadcast(event_type, data, topic)

    def send_monitor_update(self, stats: dict):
        """发送监控更新"""
        self.broadcast(self.EVENT_MONITOR, stats)

    def send_sync_update(self, sync_data: dict):
        """发送同步更新"""
        self.broadcast(self.EVENT_SYNC, sync_data)

    def send_download_update(self, download_data: dict):
        """发送下载更新"""
        self.broadcast(self.EVENT_DOWNLOAD, download_data)

    def send_server_event(self, event_data: dict):
        """发送服务器事件"""
        self.broadcast(self.EVENT_SERVER, event_data)

    def get_client_count(self) -> int:
        """获取客户端数量"""
        with self.lock:
            return len(self.clients)

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self.lock:
            return {
                **self.stats,
                'connected_clients': len(self.clients),
                'topics': list(set(
                    t for client in self.clients.values()
                    for t in client.topics
                ))
            }

    def _send_event(self, client: SSEClient, event_type: str, data: dict) -> bool:
        """发送单个事件"""
        try:
            event_data = {
                'event': event_type,
                'timestamp': time.time(),
                'data': data
            }

            # SSE格式
            message = f"event: {event_type}\n"
            message += f"id: {uuid.uuid4().hex[:16]}\n"
            message += f"retry: {self.retry_interval}\n"
            message += "data: " + json.dumps(event_data, ensure_ascii=False) + "\n\n"

            # 发送
            client.handler.wfile.write(message.encode('utf-8'))
            client.handler.wfile.flush()

            # 统计
            self.stats['total_events_sent'] += len(message)
            client.last_activity = time.time()

            return True

        except Exception as e:
            print(f"SSE发送失败 {client.client_id}: {e}")
            client.running = False
            return False

    def _start_heartbeat(self, client_id: str):
        """启动心跳"""
        def heartbeat():
            while True:
                time.sleep(self.heartbeat_interval)

                with self.lock:
                    client = self.clients.get(client_id)
                    if not client or not client.running:
                        return

                # 发送心跳
                self.send_event(client_id, self.EVENT_PING, {
                    'timestamp': time.time()
                })

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()

    def _generate_client_id(self) -> str:
        """生成客户端ID"""
        return f"sse_{uuid.uuid4().hex[:12]}"

    def cleanup(self, max_idle_time: float = 300.0):
        """清理空闲连接"""
        now = time.time()
        idle_clients = []

        with self.lock:
            for client_id, client in self.clients.items():
                if now - client.last_activity > max_idle_time:
                    idle_clients.append(client_id)

        for client_id in idle_clients:
            self.send_event(client_id, self.EVENT_ERROR, {
                'type': 'timeout',
                'message': 'Connection timed out'
            })
            self.close_connection(client_id)

    def get_client_info(self, client_id: str) -> Optional[dict]:
        """获取客户端信息"""
        with self.lock:
            client = self.clients.get(client_id)
            if not client:
                return None

            return {
                'client_id': client.client_id,
                'topics': list(client.topics),
                'connected_at': client.connected_at,
                'last_activity': client.last_activity,
                'running': client.running
            }
