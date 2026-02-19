#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HYC下载站 v2.2 - 完整增强版
主入口文件
支持镜像同步、下载加速源、系统监控、实时通信等
"""

import os
import sys
import signal
import argparse
import time

# PyInstaller 资源路径处理
def get_resource_path(relative_path):
    """获取打包后的资源路径"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 打包后的路径
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# 添加项目根目录到Python路径
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)

from core.config import ConfigManager, load_config_file, deep_merge, load_settings_with_override
from core.server import MirrorServer
from core.utils import parse_size
from core.database import init_database, load_db_config_from_env, merge_config
from core.sync_scheduler import init_database_sync
from core.optimization import (
    MemoryManager, LowMemoryConfig, ArchitectureDetector, check_compatibility
)


def signal_handler(signum, _frame):
    """处理退出信号"""
    print(f"\n收到信号 {signum}，正在关闭服务器...")
    import os
    os._exit(0)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='HYC下载站 v2.2 - 镜像文件服务器 + 下载加速源',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 基本启动
  python main.py -p 8080 -d ./downloads

  # 使用配置文件
  python main.py --settings settings.json --config custom.json

  # 认证配置
  python main.py --auth-type token --auth-token your_token_here

  # 功能开关
  python main.py --enable-monitor --enable-sync --enable-mirrors
  python main.py --disable-ws --disable-sse  # 适合低端设备

  # 镜像加速源 (通过 settings.json 配置各个镜像的启用/禁用)
  python main.py --enable-mirrors

  # 低端设备优化
  python main.py --preset ultra_low
  python main.py --memory-limit 256M --workers 2

  # 调试
  python main.py --debug
  python main.py --debug-types http auth api v2 error

  # 检查系统兼容性
  python main.py --check-compat
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
    auth_group.add_argument('--auth-type', choices=['none', 'basic', 'token'], default=None,
                            help='认证类型: none(无), basic(基本认证), token(令牌认证)')
    auth_group.add_argument('--auth-user', default='admin', help='基本认证用户名')
    auth_group.add_argument('--auth-pass', help='基本认证密码')
    auth_group.add_argument('--auth-token', help='令牌认证密钥')

    # 功能配置
    func_group = parser.add_argument_group('功能配置')
    func_group.add_argument('--directory-listing', type=bool, default=True,
                            help='启用目录浏览 (默认: True)')
    func_group.add_argument('--enable-stats', type=bool, default=True,
                            help='启用下载统计 (默认: True)')
    func_group.add_argument('--show-hash', action='store_true', help='显示文件哈希值')
    func_group.add_argument('--ignore-hidden', action='store_true', default=True,
                            help='忽略隐藏文件')
    func_group.add_argument('--max-upload-size', default='1G', help='最大上传文件大小')
    func_group.add_argument('--api-version', choices=['v1', 'v2'], default='v2',
                            help='API版本 (默认: v2)')

    # 实时通信配置
    realtime_group = parser.add_argument_group('实时通信配置')
    realtime_group.add_argument('--enable-ws', action='store_true', default=True,
                               help='启用WebSocket (默认: True)')
    realtime_group.add_argument('--enable-sse', action='store_true', default=True,
                               help='启用SSE (默认: True)')

    # 系统监控配置
    monitor_group = parser.add_argument_group('系统监控配置')
    monitor_group.add_argument('--enable-monitor', action='store_true', default=True,
                              help='启用系统监控 (默认: True)')
    monitor_group.add_argument('--monitor-interval', type=int, default=5,
                             help='监控数据采集间隔(秒) (默认: 5)')

    # 同步配置
    sync_group = parser.add_argument_group('同步配置')
    sync_group.add_argument('--enable-sync', action='store_true', default=True,
                           help='启用镜像同步 (默认: True)')
    sync_group.add_argument('--sync-config', help='同步配置文件路径')

    # 镜像加速源配置
    mirror_group = parser.add_argument_group('镜像加速源配置')
    mirror_group.add_argument('--enable-mirrors', action='store_true', default=True,
                            help='启用下载加速源 (默认: True)')
    # 注意: 各个镜像的启用/禁用通过 settings.json 中的 mirrors.xxx.enabled 配置

    # 下载限速
    rate_group = parser.add_argument_group('下载限速配置')
    rate_group.add_argument('--rate-limit', type=int, default=0,
                           help='全局下载限速(字节/秒) (默认: 0=不限速)')

    # 低端设备优化配置
    optimize_group = parser.add_argument_group('低端设备优化配置')
    optimize_group.add_argument('--preset', choices=['ultra_low', 'low', 'medium', 'high', 'auto'],
                               default='auto', help='设备预设 (默认: auto)')
    optimize_group.add_argument('--memory-limit', default='512M',
                               help='内存限制 (例如: 256M, 512M, 1G)')
    optimize_group.add_argument('--workers', type=int, default=0,
                               help='工作进程数 (0=自动)')
    optimize_group.add_argument('--chunk-size', default='128K',
                               help='文件传输块大小 (默认: 128K)')
    optimize_group.add_argument('--buffer-size', default='256K',
                               help='缓冲区大小 (默认: 256K)')
    optimize_group.add_argument('--disable-ws', action='store_true',
                               help='禁用WebSocket (低端设备)')
    optimize_group.add_argument('--disable-sse', action='store_true',
                               help='禁用SSE (低端设备)')
    optimize_group.add_argument('--disable-hash', action='store_true',
                               help='禁用文件哈希计算 (低端设备)')
    optimize_group.add_argument('--check-compat', action='store_true',
                               help='检查系统兼容性后退出')

    # 日志配置
    log_group = parser.add_argument_group('日志配置')
    log_group.add_argument('--access-log', help='访问日志文件路径')
    log_group.add_argument('--verbose', '-v', action='count', default=0, help='详细输出')
    log_group.add_argument('--quiet', '-q', action='store_true', help='静默模式')

    # 细粒度调试开关
    debug_group = parser.add_argument_group('调试选项')
    debug_group.add_argument('--debug', '-D', action='store_true',
                            help='启用所有调试输出')
    debug_group.add_argument('--debug-log', dest='debug_log_file',
                            help='调试日志文件路径 (debug 输出将写入此文件)')
    debug_group.add_argument('--debug-http', action='store_true',
                            help='调试 HTTP 请求')
    debug_group.add_argument('--debug-auth', action='store_true',
                            help='调试 认证检查')
    debug_group.add_argument('--debug-api', action='store_true',
                            help='调试 API 路由')
    debug_group.add_argument('--debug-v2', action='store_true',
                            help='调试 V2 API')
    debug_group.add_argument('--debug-error', action='store_true',
                            help='调试 错误堆栈')
    debug_group.add_argument('--debug-download', action='store_true',
                            help='调试 下载记录')
    debug_group.add_argument('--debug-types', '--debug-list',
                            nargs='+', metavar='TYPE',
                            choices=['http', 'auth', 'api', 'v2', 'error', 'download'],
                            help='指定调试类型列表 (http auth api v2 error download)')

    # 配置文件
    parser.add_argument('--settings', '--default-config', dest='settings',
                       help='默认配置文件路径 (settings.json)')
    parser.add_argument('--config', help='覆盖配置文件路径 (JSON格式，会覆盖默认配置)')

    return parser.parse_args()


def build_config_from_args(args):
    """从命令行参数构建配置"""
    cmd_config = {}

    # 服务器基本配置
    basic_args = ['host', 'port', 'server_name', 'ssl_cert', 'ssl_key',
                  'auth_type', 'auth_user', 'auth_pass', 'auth_token',
                  'access_log', 'verbose',
                  'api_version', 'directory_listing',
                  'enable_stats', 'show_hash', 'ignore_hidden', 'max_upload_size']

    for arg_name in basic_args:
        arg_value = getattr(args, arg_name, None)
        if arg_value is not None:
            cmd_config[arg_name] = arg_value

    # Debug 配置处理
    # 优先级: --debug > --debug-types > individual --debug-xxx
    debug_types = []
    if args.debug_types:
        # 用户指定了类型列表
        debug_types = list(args.debug_types)
        cmd_config['debug'] = debug_types
    elif args.debug_http or args.debug_auth or args.debug_api or args.debug_v2 or args.debug_error or args.debug_download:
        # 用户指定了单个类型
        if args.debug_http:
            debug_types.append('http')
        if args.debug_auth:
            debug_types.append('auth')
        if args.debug_api:
            debug_types.append('api')
        if args.debug_v2:
            debug_types.append('v2')
        if args.debug_error:
            debug_types.append('error')
        if args.debug_download:
            debug_types.append('download')
        cmd_config['debug'] = debug_types
    elif args.debug:
        # 开启所有
        cmd_config['debug'] = True
    else:
        # 未开启任何 debug
        cmd_config['debug'] = False

    # Debug 日志文件
    if args.debug_log_file:
        cmd_config['debug_log_file'] = args.debug_log_file

    # 路径处理
    if args.base_dir:
        cmd_config['base_dir'] = os.path.abspath(args.base_dir)

    # 实时通信
    cmd_config['enable_ws'] = args.enable_ws
    cmd_config['enable_sse'] = args.enable_sse

    # 系统监控
    cmd_config['enable_monitor'] = args.enable_monitor
    cmd_config['monitor_interval'] = args.monitor_interval

    # 同步
    cmd_config['enable_sync'] = args.enable_sync

    # 镜像加速源
    cmd_config['enable_mirrors'] = args.enable_mirrors
    # 各个镜像的启用/禁用通过 settings.json 中的 mirrors.xxx.enabled 配置

    # 下载限速
    cmd_config['rate_limit'] = args.rate_limit

    # 静默模式
    if args.quiet:
        cmd_config['verbose'] = -1

    return cmd_config


def main():
    """主入口函数"""
    args = parse_arguments()

    # 确定默认配置文件路径
    project_root = os.path.dirname(os.path.abspath(__file__))
    settings_path = args.settings or os.path.join(project_root, 'settings.json')

    # 打印配置来源信息
    print(f"[配置加载]")
    print(f"  默认配置: {settings_path}")

    # 加载配置（优先级从低到高：默认配置 -> 覆盖配置 -> 环境变量 -> 命令行参数）
    # 使用深度合并，只替换覆盖配置中有的字段

    # 1. 加载默认配置 (settings.json)
    from core.config import load_json_config
    default_config = load_json_config(settings_path) or {}
    print(f"  默认配置加载: {'成功' if default_config else '使用内联默认'}")

    # 2. 从覆盖配置文件加载
    override_config = {}
    if args.config:
        override_config = load_json_config(args.config) or {}
        print(f"  覆盖配置: {args.config} ({len(override_config)} 个顶层键)")
    else:
        print(f"  覆盖配置: 未指定")

    # 3. 深度合并默认配置和覆盖配置
    config = deep_merge(default_config, override_config)

    # 4. 从环境变量加载数据库配置
    env_db_config = load_db_config_from_env()
    if env_db_config:
        config = deep_merge(config, env_db_config)

    # 5. 同步配置
    if args.sync_config:
        sync_config = load_json_config(args.sync_config)
        if sync_config:
            if 'sync_sources' in sync_config:
                config['sync_sources'] = deep_merge(
                    config.get('sync_sources', {}),
                    sync_config['sync_sources']
                )
            if 'mirrors' in sync_config:
                config['mirrors'] = deep_merge(
                    config.get('mirrors', {}),
                    sync_config['mirrors']
                )

    # 6. 命令行参数覆盖（最高优先级）
    cmd_config = build_config_from_args(args)
    config = deep_merge(config, cmd_config)

    # 7. 每次运行都重新生成标准的 auth_token
    import secrets
    config['auth_token'] = secrets.token_hex(32)
    print(f"  已生成新的 auth_token: {config['auth_token'][:16]}...")

    # 保存新的 token 到文件
    try:
        token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auth_token.txt')
        with open(token_file, 'w') as f:
            f.write(config['auth_token'])
        print(f"  已保存 auth_token 到: auth_token.txt")
    except Exception as e:
        print(f"  警告: 保存 auth_token 失败: {e}")

    print(f"  最终配置: {len(config)} 个顶层配置项")

    # ==================== 系统兼容性检查 ====================
    if args.check_compat:
        print("\n[系统兼容性检查]")
        compat = check_compatibility()
        print(f"\n兼容状态: {'✓ 通过' if compat['compatible'] else '✗ 存在问题'}")

        arch = ArchitectureDetector.get_architecture()
        print(f"\n架构信息:")
        print(f"  - 平台: {arch['platform']}")
        print(f"  - 机器: {arch['machine']}")
        print(f"  - 架构: {arch['architecture']}")

        recommended = ArchitectureDetector.get_recommended_config()
        print(f"\n推荐配置:")
        for k, v in recommended.items():
            print(f"  - {k}: {v}")

        if compat['warnings']:
            print(f"\n警告:")
            for w in compat['warnings']:
                print(f"  ⚠ {w}")

        if compat['errors']:
            print(f"\n错误:")
            for e in compat['errors']:
                print(f"  ✗ {e}")

        sys.exit(0 if compat['compatible'] else 1)

    # ==================== 低端设备优化 ====================
    print("\n[设备检测与优化]")

    # 检测架构
    arch = ArchitectureDetector.get_architecture()

    # 应用低端设备配置
    preset = config.get('preset', 'auto')
    low_mem_config = LowMemoryConfig(preset)

    # 获取设备信息
    device_info = low_mem_config.get_device_info()

    # 显示设备信息
    if device_info['total_ram_mb'] > 0:
        print(f"  [硬件配置]")
        print(f"    - 总内存: {device_info['total_ram_mb']:.0f} MB")
        print(f"    - 可用内存: {device_info['available_ram_mb']:.0f} MB ({100-device_info['percent_used']:.1f}% 可用)")
        print(f"    - CPU核心: {device_info['cpu_count']} 核心")
        print(f"    - 系统架构: {arch['machine']} ({arch['architecture']})")
    else:
        print(f"  - 系统架构: {arch['machine']} ({arch['architecture']})")

    print(f"\n  [性能优化]")
    print(f"    - 优化模式: {preset}")

    # 应用配置
    if preset != 'auto':
        status = low_mem_config.get_status()
        print(f"    - 预设方案: {status.get('description', preset)}")

    config = low_mem_config.apply_to_config(config)

    # 覆盖命令行参数
    if args.memory_limit:
        config['memory_limit'] = parse_size(args.memory_limit)
    if args.workers > 0:
        config['workers'] = args.workers
    if args.chunk_size:
        config['chunk_size'] = parse_size(args.chunk_size)
    if args.buffer_size:
        config['buffer_size'] = parse_size(args.buffer_size)

    # 禁用可选功能
    if args.disable_ws:
        config['enable_ws'] = False
    if args.disable_sse:
        config['enable_sse'] = False
    if args.disable_hash:
        config['calculate_hash'] = False

    # 启动内存管理器
    memory_manager = MemoryManager({
        'enabled': True,
        'memory_limit': config.get('memory_limit', 512 * 1024 * 1024),
        'gc_interval': config.get('gc_interval', 300),  # 定时GC间隔
        'enable_scheduled_gc': config.get('enable_scheduled_gc', True)
    })
    memory_manager.start()
    config['_memory_manager'] = memory_manager

    mem_status = memory_manager.get_status()
    print(f"    - 内存限制: {mem_status['memory_limit_mb']} MB")
    print(f"    - 工作进程: {config.get('workers', 1)}")
    print(f"    - 传输块: {config.get('chunk_size', 128 * 1024) // 1024} KB")
    print(f"    - GC间隔: {config.get('gc_interval', 300)}秒")
    print(f"    - 缓存大小: {config.get('max_cache_size', 0) // (1024*1024)} MB")

    # 设置信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 打印启动信息
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 22 + "HYC下载站 v2.2" + " " * 22 + "║")
    print("╚" + "═" * 58 + "╝")

    print()
    print("【服务器配置】")
    print(f"  ▶ 监听地址: {config.get('host')}:{config.get('port')}")
    print(f"  ▶ 文件目录: {os.path.abspath(config.get('base_dir', './downloads'))}")
    print(f"  ▶ API版本: {config.get('api_version', 'v2')}")
    print(f"  ▶ 认证方式: {config.get('auth_type', 'none')}")
    max_upload = config.get('max_upload_size', '1G')
    if isinstance(max_upload, str):
        max_upload = parse_size(max_upload)
    else:
        max_upload = int(max_upload)
    print(f"  ▶ 最大上传: {max_upload // (1024*1024)} MB")

    # 数据库状态
    db_config = config.get('database', {})
    db_enabled = db_config.get('enabled', True)

    print()
    print("【功能模块】")
    print(f"  {'●' if config.get('enable_monitor') else '○'} 系统监控", end='')
    print(f"    {'●' if config.get('enable_sync') else '○'} 镜像同步", end='')
    print(f"    {'●' if config.get('enable_mirrors') else '○'} 加速源")
    print(f"  {'●' if config.get('enable_ws') else '○'} WebSocket", end='')
    print(f"   {'●' if config.get('enable_sse') else '○'} SSE", end='')
    print(f"       {'●' if db_enabled else '○'} 数据库")

    if db_enabled:
        print(f"    └── 类型: {db_config.get('type', 'sqlite')} | 同步间隔: {db_config.get('sync_interval', 60)}s")

    print()
    print("【性能参数】")
    print(f"  ▶ 最大线程: {config.get('max_workers', 10)}")
    print(f"  ▶ 工作进程: {config.get('workers', 1)}")
    print(f"  ▶ 内存限制: {config.get('memory_limit', 512*1024*1024) // (1024*1024)} MB")
    print(f"  ▶ 连接超时: {config.get('timeout', 30)}s")

    print()
    print("=" * 60)

    # 初始化数据库
    db = None
    scheduler = None
    if db_enabled:
        print("\n[初始化数据库...]")
        try:
            db = init_database(config)

            # 健康检查
            health = db.health_check()
            if health.get('healthy'):
                print(f"  ✓ 数据库连接成功 ({db_config.get('type', 'sqlite')})")
                print(f"  ✓ 表数量: {health.get('table_count', 0)}")
            else:
                print(f"  ✗ 数据库健康检查失败: {health.get('error')}")

            # 检查并更新Schema
            if db.check_schema_version():
                print(f"  ✓ 数据库结构版本检查通过")

            # 获取统计
            db_stats = db.get_stats()
            print(f"\n  数据库统计:")
            print(f"    - 文件记录: {db_stats['total_files']}")
            print(f"    - 同步记录: {db_stats['total_sync_records']}")
            print(f"    - 缓存记录: {db_stats['total_cache_records']}")
            print(f"    - 下载记录: {db_stats['total_download_records']}")

            # 将数据库实例添加到配置中
            config['_db_instance'] = db

        except Exception as e:
            print(f"\n  ✗ 数据库初始化失败: {e}")
            print("  ⚠ 服务器将继续运行，但不使用数据库功能")

            # 初始化同步调度器（不使用数据库）
            if config.get('enable_sync'):
                _, scheduler, _ = init_database_sync(config)
                scheduler.start()
                print("  - 同步调度器已启动")

    # ==================== 优雅关闭处理 ====================
    import atexit

    def cleanup():
        """服务器关闭时清理资源"""
        print("\n正在关闭服务器...")

        # 关闭数据库连接池
        if db:
            try:
                db.engine.dispose()
                print("✓ 数据库连接已关闭")
            except Exception as e:
                print(f"✗ 关闭数据库连接时出错: {e}")

        # 停止同步调度器
        if scheduler:
            try:
                scheduler.stop()
                print("✓ 同步调度器已停止")
            except Exception as e:
                print(f"✗ 停止同步调度器时出错: {e}")

        print("服务器已关闭")

    # 注册关闭处理函数
    atexit.register(cleanup)

    # 设置服务器启动时间（用于计算运行时间）
    config['start_time'] = time.time()

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
