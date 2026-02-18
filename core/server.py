#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""服务器核心模块 - 线程池版本"""

import os
import sys
import ssl
import signal
import mimetypes
import threading
import socketserver
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .config import ConfigManager
from .mirror_sync import MirrorSyncManager


class ThreadPoolHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """使用线程池的 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True  # 使用守护线程

    def __init__(self, server_address, RequestHandlerClass, max_workers=50):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="http_handler"
        )
        super().__init__(server_address, RequestHandlerClass)

    def process_request(self, request, client_address):
        """使用线程池处理请求"""
        self._executor.submit(self._handle_request, request, client_address)

    def _handle_request(self, request, client_address):
        """实际处理请求"""
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)

    def server_close(self):
        """关闭服务器和线程池"""
        # Python 3.8 兼容处理
        import sys
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # Python 3.8 不支持 cancel_futures 参数
            self._executor.shutdown(wait=False)
        super().server_close()


class MirrorServer:
    """镜像服务器主类"""

    def __init__(self, config):
        if isinstance(config, dict):
            self.config_manager = ConfigManager(config)
        else:
            self.config_manager = config

        self.config = self.config_manager.config
        self.server = None
        self.sync_manager = None
        self.is_running = False

    def _validate_config(self, config):
        """验证和修复配置"""
        return self.config_manager._validate_config(config)

    def start(self):
        """启动服务器"""
        try:
            # 创建下载目录
            base_dir = self.config['base_dir']
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
                print(f"创建下载目录: {os.path.abspath(base_dir)}")

            # 初始化MIME类型
            mimetypes.init()

            # 记录启动时间
            self.config['start_time'] = __import__('time').time()

            # 创建同步管理器（仅当启用时）
            if self.config.get('enable_sync', True):
                self.sync_manager = MirrorSyncManager(self.config)
                self.sync_manager.start()

            # 创建系统监控器（仅当启用时）
            self.monitor = None
            if self.config.get('enable_monitor', True):
                try:
                    from .monitor import SystemMonitor
                    self.monitor = SystemMonitor(self.config)
                    print(f"  ✓ 系统监控已启用 (间隔: {self.config.get('monitor_interval', 5)}秒)")
                except ImportError as e:
                    print(f"  ✗ 系统监控导入失败: {e}")
                except Exception as e:
                    print(f"  ✗ 系统监控初始化失败: {e}")

            # 延迟导入 handler（避免循环导入）
            from handlers.http_handler import MirrorServerHandler

            # 获取线程数配置
            max_workers = min(self.config.get('max_workers', 10), 10)  # 限制最大线程数

            # 创建服务器
            server_address = (self.config['host'], self.config['port'])
            self.server = ThreadPoolHTTPServer(
                server_address,
                MirrorServerHandler,
                max_workers=max_workers
            )

            # 传递配置到处理器
            MirrorServerHandler.config = self.config
            MirrorServerHandler.sync_manager = self.sync_manager
            MirrorServerHandler.monitor = self.monitor
            # 设置调试模式
            MirrorServerHandler._setup_debug(self.config)

            # 设置超时
            self.server.timeout = self.config.get('timeout', 30)

            # 启用HTTPS
            if self.config.get('ssl_cert') and self.config.get('ssl_key'):
                if not self._setup_ssl():
                    return False

            self.is_running = True
            return True

        except Exception as e:
            import traceback
            print(f"服务器启动失败: {e}")
            traceback.print_exc()
            return False

    def _setup_ssl(self):
        """设置SSL"""
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(self.config['ssl_cert'], self.config['ssl_key'])
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
            print(f"启用HTTPS，证书: {self.config['ssl_cert']}")
            return True
        except Exception as e:
            print(f"启用HTTPS失败: {e}")
            return False

    def stop(self):
        """停止服务器"""
        print("正在停止服务器...")

        if self.sync_manager:
            try:
                self.sync_manager.stop()
            except Exception as e:
                print(f"停止同步管理器时出错: {e}")

        if self.server:
            try:
                self.server.server_close()
            except Exception as e:
                print(f"关闭服务器连接时出错: {e}")

        self.is_running = False
        print("服务器已停止")

    def serve_forever(self):
        """运行服务器"""
        if not self.server:
            print("服务器未启动")
            return

        # 打印服务器信息（已在 main.py 中显示，此处仅保留最简信息）
        protocol = "https" if self.config.get('ssl_cert') else "http"
        sync_count = len(self.sync_manager.sync_sources) if self.sync_manager else 0
        print(f"\n▶ 服务器运行于: {protocol}://{self.config['host']}:{self.config['port']}")
        print(f"▶ 同步源数: {sync_count} | 最大线程: {self.server.max_workers}")
        print("▶ 按 Ctrl+C 停止服务器")

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\n正在关闭服务器...")
        finally:
            self.stop()


# 全局变量，用于信号处理器访问服务器实例（预留）
# _server_instance = None

# def signal_handler(signum, frame):
#     """处理退出信号"""
#     print(f"\n收到信号 {signum}，正在关闭服务器...")
#     import os
#     os._exit(0)
