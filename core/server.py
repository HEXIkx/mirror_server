#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""服务器核心模块"""

import os
import ssl
import signal
import mimetypes
from http.server import ThreadingHTTPServer

from .config import ConfigManager
from .mirror_sync import MirrorSyncManager
from handlers.http_handler import MirrorServerHandler


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
            import time
            self.config['start_time'] = time.time()

            # 创建同步管理器
            self.sync_manager = MirrorSyncManager(self.config)
            self.sync_manager.start()

            # 创建服务器
            server_address = (self.config['host'], self.config['port'])

            # 创建自定义服务器类
            class ConfigurableThreadingHTTPServer(ThreadingHTTPServer):
                def __init__(self, server_address, handler_class, config, sync_manager):
                    self.config = config
                    self.sync_manager = sync_manager
                    super().__init__(server_address, handler_class)

                def finish_request(self, request, client_address):
                    """覆盖 finish_request 以传递配置"""
                    self.RequestHandlerClass(
                        request, client_address, self,
                        config=self.config,
                        sync_manager=self.sync_manager
                    )

            # 设置处理器的类变量
            MirrorServerHandler.config = self.config
            MirrorServerHandler.sync_manager = self.sync_manager

            # 创建服务器实例
            self.server = ConfigurableThreadingHTTPServer(
                server_address,
                MirrorServerHandler,
                config=self.config,
                sync_manager=self.sync_manager
            )

            # 设置超时
            self.server.timeout = self.config.get('timeout', 30)

            # 启用HTTPS
            if self.config.get('ssl_cert') and self.config.get('ssl_key'):
                if not self._setup_ssl():
                    return False

            self.is_running = True
            return True

        except Exception as e:
            print(f"服务器启动失败: {e}")
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
        if self.sync_manager:
            self.sync_manager.stop()
            
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            
        self.is_running = False
        print("服务器已停止")

    def serve_forever(self):
        """运行服务器"""
        if not self.server:
            print("服务器未启动")
            return

        # 打印服务器信息
        protocol = "https" if self.config.get('ssl_cert') else "http"
        print(f"\n{'='*60}")
        print(f"HYC下载站 v2.1")
        print(f"{'='*60}")
        print(f"服务器地址: {protocol}://{self.config['host']}:{self.config['port']}")
        print(f"下载目录: {os.path.abspath(self.config['base_dir'])}")
        print(f"API端点: {protocol}://{self.config['host']}:{self.config['port']}/api/")
        print(f"API版本: {self.config.get('api_version', 'v1')}")
        print(f"同步管理: {protocol}://{self.config['host']}:{self.config['port']}/api/sync/")
        print(f"目录浏览: {'启用' if self.config.get('directory_listing', True) else '禁用'}")
        print(f"认证方式: {self.config.get('auth_type', '无')}")
        print(f"最大上传: {self.config.get('max_upload_size', 1024 * 1024 * 1024) // (1024 * 1024)} MB")
        print(f"同步源数: {len(self.sync_manager.sync_sources)}")
        print(f"{'='*60}")
        print("按 Ctrl+C 停止服务器")

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\n正在关闭服务器...")
        finally:
            self.stop()


def signal_handler(signum, frame):
    """处理退出信号"""
    print(f"\n收到信号 {signum}，正在关闭服务器...")
    import sys
    sys.exit(0)
