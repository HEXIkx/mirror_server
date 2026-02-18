#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
安全增强模块
提供 IP 白名单/黑名单、请求速率限制、HTTPS 支持
"""

import os
import sys
import time
import json
import hashlib
import threading
import logging
import ssl
import ipaddress
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from functools import wraps
from collections import defaultdict
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


# ==================== IP 管理器 ====================

class IPManager:
    """IP 管理器 - 白名单/黑名单"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.whitelist: List[str] = []
        self.blacklist: List[str] = []
        self._load_lists()

    def _load_lists(self):
        """加载 IP 列表"""
        # 加载白名单
        whitelist_file = self.config.get('whitelist_file', 'whitelist.txt')
        if os.path.exists(whitelist_file):
            with open(whitelist_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.whitelist.append(line)

        # 加载黑名单
        blacklist_file = self.config.get('blacklist_file', 'blacklist.txt')
        if os.path.exists(blacklist_file):
            with open(blacklist_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.blacklist.append(line)

    def is_allowed(self, ip: str) -> Tuple[bool, str]:
        """
        检查 IP 是否允许访问
        返回: (是否允许, 原因)
        """
        # 检查白名单
        if self.whitelist:
            for pattern in self.whitelist:
                if self._match_ip(ip, pattern):
                    return True, "白名单"

        # 检查黑名单
        for pattern in self.blacklist:
            if self._match_ip(ip, pattern):
                return False, "黑名单"

        return True, "允许"

    def _match_ip(self, ip: str, pattern: str) -> bool:
        """匹配 IP"""
        try:
            # 单个 IP
            if pattern == ip:
                return True

            # CIDR 范围
            if '/' in pattern:
                network = ipaddress.ip_network(pattern, strict=False)
                return ipaddress.ip_address(ip) in network

            # 通配符 (例如: 192.168.1.*)
            if pattern.endswith('*'):
                prefix = pattern.rstrip('*').rstrip('.')
                return ip.startswith(prefix)

        except Exception:
            pass

        return False

    def add_to_whitelist(self, ip: str):
        """添加到白名单"""
        if ip not in self.whitelist:
            self.whitelist.append(ip)
            self._save_list('whitelist')

    def add_to_blacklist(self, ip: str):
        """添加到黑名单"""
        if ip not in self.blacklist:
            self.blacklist.append(ip)
            self._save_list('blacklist')

    def remove_from_whitelist(self, ip: str):
        """从白名单移除"""
        if ip in self.whitelist:
            self.whitelist.remove(ip)
            self._save_list('whitelist')

    def remove_from_blacklist(self, ip: str):
        """从黑名单移除"""
        if ip in self.blacklist:
            self.blacklist.remove(ip)
            self._save_list('blacklist')

    def _save_list(self, list_type: str):
        """保存列表到文件"""
        filename = f'{list_type}.txt'
        data = '\n'.join(self.whitelist if list_type == 'whitelist' else self.blacklist)
        with open(filename, 'w') as f:
            f.write(data)

    def get_status(self) -> dict:
        """获取状态"""
        return {
            'whitelist_count': len(self.whitelist),
            'blacklist_count': len(self.blacklist),
            'whitelist': self.whitelist[:10],
            'blacklist': self.blacklist[:10]
        }


# ==================== 速率限制器 ====================

class RateLimiter:
    """请求速率限制器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.Lock()

        # 配置
        self.requests_per_minute = self.config.get('requests_per_minute', 100)
        self.burst_limit = self.config.get('burst_limit', 20)
        self.window_seconds = 60

    def is_allowed(self, identifier: str) -> Tuple[bool, int]:
        """
        检查请求是否允许
        返回: (是否允许, 剩余配额)
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self.lock:
            # 清理过期记录
            self.requests[identifier] = [
                t for t in self.requests[identifier]
                if t > window_start
            ]

            # 检查限制
            if len(self.requests[identifier]) >= self.requests_per_minute:
                return False, 0

            # 记录请求
            self.requests[identifier].append(now)

            remaining = self.requests_per_minute - len(self.requests[identifier])
            return True, remaining

    def get_usage(self, identifier: str) -> dict:
        """获取使用情况"""
        now = time.time()
        window_start = now - self.window_seconds

        with self.lock:
            requests = [
                t for t in self.requests[identifier]
                if t > window_start
            ]

            return {
                'requests': len(requests),
                'limit': self.requests_per_minute,
                'remaining': self.requests_per_minute - len(requests),
                'reset_in': int(self.window_seconds - (now - min(requests) if requests else now))
            }

    def get_status(self) -> dict:
        """获取全局状态"""
        total_requests = sum(len(v) for v in self.requests.values())
        return {
            'active_ips': len(self.requests),
            'total_requests': total_requests,
            'limit_per_minute': self.requests_per_minute,
            'burst_limit': self.burst_limit
        }

    def reset(self):
        """重置所有记录"""
        with self.lock:
            self.requests.clear()


# ==================== HTTPS 管理器 ====================

class HTTPSManager:
    """HTTPS 证书管理器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.cert_file = self.config.get('ssl_cert')
        self.key_file = self.config.get('ssl_key')
        self.context = None

    def is_enabled(self) -> bool:
        """是否启用 HTTPS"""
        return bool(self.cert_file and self.key_file)

    def create_context(self) -> Optional[ssl.SSLContext]:
        """创建 SSL 上下文"""
        if not self.is_enabled():
            return None

        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

            # 加载证书
            context.load_cert_chain(self.cert_file, self.key_file)

            # 安全配置
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.set_ciphers('ECDHE+AESGCM:DHE+AESGCM:ECDHE+CHACHA20')

            self.context = context
            return context

        except Exception as e:
            logger.error(f"创建 SSL 上下文失败: {e}")
            return None

    @staticmethod
    def generate_self_signed_cert(cert_path: str, key_path: str, common_name: str = 'localhost') -> bool:
        """生成自签名证书（用于测试）"""
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            import datetime as dt

            # 生成私钥
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # 生成证书
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Shanghai"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Shanghai"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HYC Download Station"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ])

            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(dt.datetime.utcnow())
                .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=365))
                .add_extension(
                    x509.SubjectAlternativeName([
                        x509.DNSName(common_name),
                        x509.DNSName("localhost"),
                    ]),
                    critical=False,
                )
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            # 保存证书
            with open(cert_path, 'wb') as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))

            # 保存私钥
            with open(key_path, 'wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))

            return True

        except Exception as e:
            logger.error(f"生成自签名证书失败: {e}")
            return False

    def get_status(self) -> dict:
        """获取状态"""
        return {
            'enabled': self.is_enabled(),
            'cert_file': self.cert_file,
            'key_file': self.key_file
        }


# ==================== 安全中间件 ====================

class SecurityMiddleware:
    """安全中间件"""

    def __init__(self, config: dict = None):
        self.config = config or {}

        # 初始化各组件
        self.ip_manager = IPManager(self.config.get('ip', {}))
        self.rate_limiter = RateLimiter(self.config.get('rate_limit', {}))
        self.https_manager = HTTPSManager(self.config.get('ssl', {}))

    def check_request(self, handler) -> Tuple[bool, str]:
        """
        检查请求是否安全
        返回: (是否通过, 原因)
        """
        client_ip = self._get_client_ip(handler)

        # IP 检查
        allowed, reason = self.ip_manager.is_allowed(client_ip)
        if not allowed:
            return False, f"IP被阻止: {reason}"

        # 速率限制
        allowed, _ = self.rate_limiter.is_allowed(client_ip)
        if not allowed:
            return False, "请求过于频繁"

        return True, "通过"

    def _get_client_ip(self, handler) -> str:
        """获取客户端 IP"""
        # 检查代理头
        forwarded = handler.headers.get('X-Forwarded-For')
        if forwarded:
            return forwarded.split(',')[0].strip()

        real_ip = handler.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        return handler.client_address[0] if hasattr(handler, 'client_address') else 'unknown'

    def get_security_headers(self) -> dict:
        """获取安全响应头"""
        return {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'SAMEORIGIN',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        }

    def get_status(self) -> dict:
        """获取安全状态"""
        return {
            'ip': self.ip_manager.get_status(),
            'rate_limit': self.rate_limiter.get_status(),
            'ssl': self.https_manager.get_status()
        }


# ==================== 审计日志 ====================

class AuditLogger:
    """审计日志记录器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logs: Queue = Queue(maxsize=10000)
        self.log_file = self.config.get('audit_log', 'audit.log')
        self.enabled = self.config.get('enabled', True)

        # 启动日志写入线程
        if self.enabled:
            self._start_writer()

    def log(self, event_type: str, data: dict):
        """记录事件"""
        if not self.enabled:
            return

        entry = {
            'timestamp': time.time(),
            'type': event_type,
            **data
        }

        if self.logs.full():
            self.logs.get()  # 移除最旧的

        self.logs.put(entry)

    def _start_writer(self):
        """启动日志写入线程"""
        def writer():
            while True:
                try:
                    entry = self.logs.get(timeout=1)
                    self._write_entry(entry)
                except Exception:
                    continue

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()

    def _write_entry(self, entry: dict):
        """写入日志条目"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                line = json.dumps(entry, ensure_ascii=False)
                f.write(line + '\n')
        except Exception as e:
            logger.error(f"写入审计日志失败: {e}")

    def get_recent_logs(self, event_type: str = None, limit: int = 100) -> List[dict]:
        """获取最近的日志"""
        result = []
        with self.logs.mutex:
            for entry in list(self.logs.queue):
                if event_type and entry.get('type') != event_type:
                    continue
                result.append(entry)
                if len(result) >= limit:
                    break
        return result[-limit:]

    def get_status(self) -> dict:
        """获取状态"""
        with self.logs.mutex:
            return {
                'enabled': self.enabled,
                'log_file': self.log_file,
                'pending_logs': self.logs.qsize(),
                'max_size': self.logs.maxsize
            }


# ==================== 便捷函数 ====================

def get_security_middleware(config: dict = None) -> SecurityMiddleware:
    """获取安全中间件"""
    return SecurityMiddleware(config)


def get_ip_manager(config: dict = None) -> IPManager:
    """获取 IP 管理器"""
    return IPManager(config)


def get_rate_limiter(config: dict = None) -> RateLimiter:
    """获取速率限制器"""
    return RateLimiter(config)
