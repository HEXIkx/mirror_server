#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HYC下载站 - 主入口文件
模块化重构版本
"""

import os
import sys
import signal
import argparse

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import ConfigManager, load_config_file
from core.server import MirrorServer, signal_handler
from core.utils import parse_size


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Python镜像文件服务器 v2.1 - 专为文件分享和镜像同步优化',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'''
示例:
  {sys.argv[0]} -p 8080 -d ./downloads
  {sys.argv[0]} --host 0.0.0.0 --port 443 --ssl-cert cert.pem --ssl-key key.pem
  {sys.argv[0]} --auth basic --auth-user admin --auth-pass password
  {sys.argv[0]} --config config.json
  {sys.argv[0]} --api-version v2  # 使用API v2版本

新增功能:
  - 镜像同步功能（HTTP/HTTPS、FTP、SFTP、本地目录）
  - 动态管理同步源
  - 实时同步状态监控
  - API版本化支持（v1/v2）
  - 增强搜索和统计功能
  - 文件元数据管理
  - Webhook支持（v2）

API端点:
  - /api/v1/... - API v1 基础功能
  - /api/v2/... - API v2 增强功能
  - /api/... - 使用默认版本（可通过 --api-version 配置）
  - /api/sync/    - 同步管理
  - /api/files    - 文件管理
  - /api/search   - 文件搜索
        '''
    )

    # 服务器配置
    parser.add_argument('--host', default='0.0.0.0', help='监听地址 (默认: 0.0.0.0)')
    parser.add_argument('-p', '--port', type=int, default=8080, help='监听端口 (默认: 8080)')
    parser.add_argument('-d', '--base-dir', default='./downloads', help='文件存储目录 (默认: ./downloads)')
    parser.add_argument('--server-name', default='HYC下载站', help='服务器名称')

    # HTTPS配置
    parser.add_argument('--ssl-cert', help='SSL证书文件路径')
    parser.add_argument('--ssl-key', help='SSL私钥文件路径')

    # 认证配置
    auth_group = parser.add_argument_group('认证配置')
    auth_group.add_argument('--auth-type', choices=['none', 'basic', 'token'], default='none',
                            help='认证类型: none(无), basic(基本认证), token(令牌认证)')
    auth_group.add_argument('--auth-user', default='admin', help='基本认证用户名')
    auth_group.add_argument('--auth-pass', help='基本认证密码')
    auth_group.add_argument('--auth-token', help='令牌认证密钥')

    # 功能配置
    func_group = parser.add_argument_group('功能配置')
    func_group.add_argument('--no-directory-listing', action='store_false', dest='directory_listing',
                            help='禁用目录浏览')
    func_group.add_argument('--no-stats', action='store_false', dest='enable_stats',
                            help='禁用下载统计')
    func_group.add_argument('--show-hash', action='store_true', help='显示文件哈希值')
    func_group.add_argument('--ignore-hidden', action='store_true', default=True,
                            help='忽略隐藏文件')
    func_group.add_argument('--max-upload-size', default='1G', help='最大上传文件大小')
    func_group.add_argument('--sync-config', help='同步配置文件路径')
    func_group.add_argument('--api-version', choices=['v1', 'v2'], default='v1',
                            help='API版本 (默认: v1)')

    # 日志配置
    log_group = parser.add_argument_group('日志配置')
    log_group.add_argument('--access-log', help='访问日志文件路径')
    log_group.add_argument('--verbose', '-v', action='count', default=0, help='详细输出')
    log_group.add_argument('--quiet', '-q', action='store_true', help='静默模式')

    # 配置文件
    parser.add_argument('--config', help='配置文件路径 (JSON格式)')

    return parser.parse_args()


def build_config_from_args(args):
    """从命令行参数构建配置"""
    cmd_config = {}
    
    # 直接映射的参数
    direct_args = ['host', 'port', 'server_name', 'ssl_cert', 'ssl_key', 
                  'auth_type', 'auth_user', 'auth_pass', 'auth_token',
                  'access_log', 'verbose', 'api_version']
    
    for arg_name in direct_args:
        arg_value = getattr(args, arg_name)
        if arg_value is not None:
            cmd_config[arg_name] = arg_value

    # 特殊处理的参数
    if args.base_dir:
        cmd_config['base_dir'] = os.path.abspath(args.base_dir)
    
    if hasattr(args, 'directory_listing'):
        cmd_config['directory_listing'] = args.directory_listing
        
    if hasattr(args, 'enable_stats'):
        cmd_config['enable_stats'] = args.enable_stats
        
    if hasattr(args, 'show_hash'):
        cmd_config['show_hash'] = args.show_hash
        
    if hasattr(args, 'ignore_hidden'):
        cmd_config['ignore_hidden'] = args.ignore_hidden
        
    if args.max_upload_size:
        try:
            cmd_config['max_upload_size'] = parse_size(args.max_upload_size)
        except ValueError as e:
            print(f"错误: {e}")
            sys.exit(1)
    
    if args.quiet:
        cmd_config['verbose'] = -1
    
    return cmd_config


def main():
    """主入口函数"""
    args = parse_arguments()

    # 加载配置
    config = {}

    # 从配置文件加载（如果指定）
    if args.config:
        file_config = load_config_file(args.config)
        config.update(file_config)

    # 从命令行参数构建配置
    cmd_config = build_config_from_args(args)

    # 加载同步配置
    if args.sync_config:
        sync_config = load_config_file(args.sync_config)
        if 'sync_sources' in sync_config:
            config['sync_sources'] = sync_config['sync_sources']

    # 命令行参数覆盖配置文件
    config.update(cmd_config)

    # 设置信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 创建并启动服务器
    try:
        server = MirrorServer(config)
        if server.start():
            server.serve_forever()
        else:
            print("服务器启动失败")
            sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
