#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
内存优化模块
专为低端设备优化 (2CPU/1G 内存等)
"""

import os
import sys
import gc
import time
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from contextlib import contextmanager
from functools import wraps

# 跨平台兼容处理：resource 模块仅在 Unix/Linux 上可用
try:
    import resource
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False
    resource = None

# 内存限制配置
DEFAULT_MEMORY_LIMIT = 512 * 1024 * 1024  # 512MB
LOW_MEMORY_LIMIT = 256 * 1024 * 1024     # 256MB
VERY_LOW_MEMORY_LIMIT = 128 * 1024 * 1024  # 128MB


class MemoryManager:
    """内存管理器 - 支持定时垃圾回收"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.memory_limit = self.config.get('memory_limit', DEFAULT_MEMORY_LIMIT)
        self.soft_limit = self.memory_limit * 0.8  # 80% 时触发警告
        self.check_interval = self.config.get('check_interval', 10)  # 秒

        # 定时垃圾回收配置
        self.gc_interval = self.config.get('gc_interval', 300)  # 默认 5 分钟
        self.enable_scheduled_gc = self.config.get('enable_scheduled_gc', True)

        # 缓存清理回调
        self.cache_cleaners: List[Callable] = []

        # 回调函数
        self.on_memory_warning: Optional[Callable] = None
        self.on_memory_critical: Optional[Callable] = None

        self._running = False
        self._monitor_thread = None
        self._gc_thread = None

    def start(self):
        """启动内存监控"""
        if not self.enabled:
            return

        self._running = True

        # 启动内存监控线程
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        # 启动定时垃圾回收线程
        if self.enable_scheduled_gc:
            self._gc_thread = threading.Thread(target=self._gc_loop, daemon=True)
            self._gc_thread.start()
            print(f"[内存管理] 定时GC: {self.gc_interval}秒")

        # 设置内存限制
        self.set_memory_limit(self.memory_limit)

        print(f"[内存管理] 已启动, 限制: {self.memory_limit // 1024 // 1024}MB")

    def stop(self):
        """停止内存监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        if self._gc_thread:
            self._gc_thread.join(timeout=2)

    def register_cache_cleaner(self, cleaner: Callable):
        """注册缓存清理回调函数"""
        self.cache_cleaners.append(cleaner)

    def set_memory_limit(self, limit: int):
        """设置内存限制 (Linux/Unix)"""
        if not _HAS_RESOURCE or resource is None:
            # Windows 平台不支持内存限制，跳过
            print(f"[内存管理] 跳过内存限制设置 (Windows平台不支持)")
            return
        try:
            # 软限制
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            print(f"[内存管理] 已设置内存限制: {limit // 1024 // 1024}MB")
        except Exception as e:
            print(f"[内存管理] 设置内存限制失败: {e}")

    def get_memory_usage(self) -> dict:
        """获取内存使用情况"""
        try:
            # 进程内存
            import psutil
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()

            # 系统内存
            sys_mem = psutil.virtual_memory()

            return {
                'process_rss': mem_info.rss,
                'process_vms': mem_info.vms,
                'process_percent': process.memory_percent(),
                'system_total': sys_mem.total,
                'system_available': sys_mem.available,
                'system_percent': sys_mem.percent,
                'process_rss_mb': mem_info.rss / 1024 / 1024,
                'system_available_mb': sys_mem.available / 1024 / 1024
            }
        except Exception as e:
            # 备用方法：使用 resource (Unix) 或返回估计值 (Windows)
            if _HAS_RESOURCE and resource is not None:
                try:
                    return {
                        'process_rss': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                        'process_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    }
                except Exception:
                    pass
            # Windows 无 psutil 的极端情况
            return {
                'process_rss': 0,
                'process_rss_mb': 0,
                'error': str(e)
            }

    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                usage = self.get_memory_usage()

                # 检查是否达到软限制
                if usage['process_rss'] >= self.soft_limit:
                    if self.on_memory_warning:
                        self.on_memory_warning(usage)
                    self._aggressive_cleanup()

                # 检查是否达到硬限制
                if usage['process_rss'] >= self.memory_limit:
                    if self.on_memory_critical:
                        self.on_memory_critical(usage)
                    self._emergency_cleanup()

                time.sleep(self.check_interval)
            except Exception:
                pass

    def _gc_loop(self):
        """定时垃圾回收循环"""
        while self._running:
            try:
                # 执行垃圾回收
                self._scheduled_gc()

                # 清理注册过的缓存
                for cleaner in self.cache_cleaners:
                    try:
                        cleaner()
                    except Exception:
                        pass

            except Exception:
                pass

            time.sleep(self.gc_interval)

    def _scheduled_gc(self):
        """定时 GC 执行"""
        # 标准 GC
        collected = gc.collect()
        # 清理 Python 内部缓存
        if hasattr(sys, 'exc_clear'):
            sys.exc_clear()

    def _aggressive_cleanup(self):
        """激进清理"""
        # 强制垃圾回收
        gc.collect()

        # 清理 Python 缓存
        if hasattr(gc, 'set_threshold'):
            gc.set_threshold(500, 10, 5)

        # 尝试释放内存
        try:
            import psutil
            process = psutil.Process(os.getpid())
            process.memory_info().rss  # 刷新
        except Exception:
            pass

    def _emergency_cleanup(self):
        """紧急清理"""
        print("[内存管理] ⚠️ 达到内存限制，尝试紧急清理...")

        # 完全垃圾回收
        gc.collect()
        gc.collect()
        gc.collect()

        # 清理所有缓存
        if hasattr(gc, 'garbage'):
            del gc.garbage[:]

        # 触发警告
        print("[内存管理] ⚠️ 内存仍过高，考虑重启服务")

    def get_status(self) -> dict:
        """获取状态"""
        usage = self.get_memory_usage()
        return {
            'enabled': self.enabled,
            'memory_limit_mb': self.memory_limit // 1024 // 1024,
            'current_mb': usage['process_rss_mb'],
            'available_mb': usage.get('system_available_mb', 0),
            'percent': (usage['process_rss'] / self.memory_limit * 100) if self.memory_limit else 0
        }


# ==================== 低内存配置 ====================

class LowMemoryConfig:
    """低端设备配置"""

    # 可禁用的功能列表
    FEATURES = {
        'ws': 'enable_ws',           # WebSocket
        'sse': 'enable_sse',         # Server-Sent Events
        'hash_calc': 'calculate_hash',  # 文件哈希计算
        'stats': 'enable_stats',     # 统计功能
        'monitor': 'enable_monitor', # 系统监控
        'sync': 'enable_sync',       # 同步功能
        'mirrors': 'enable_mirrors', # 加速源
    }

    # 预设配置
    PRESETS = {
        'ultra_low': {
            'description': '极低端设备 (<256MB RAM)',
            'workers': 1,
            'max_cache_size': 32 * 1024 * 1024,  # 32MB
            'chunk_size': 16 * 1024,  # 16KB
            'buffer_size': 32 * 1024,  # 32KB
            'db_pool_size': 1,
            'max_connections': 3,
            'monitor_interval': 60,
            'gc_interval': 180,  # 3分钟
            'timeout': 15,
            'disable_optional_features': ['ws', 'sse', 'hash_calc', 'stats', 'monitor']
        },
        'low': {
            'description': '低端设备 (256-512MB RAM)',
            'workers': 1,
            'max_cache_size': 64 * 1024 * 1024,  # 64MB
            'chunk_size': 32 * 1024,  # 32KB
            'buffer_size': 64 * 1024,  # 64KB
            'db_pool_size': 1,
            'max_connections': 5,
            'monitor_interval': 30,
            'gc_interval': 300,  # 5分钟
            'timeout': 20,
            'disable_optional_features': ['ws', 'sse', 'hash_calc', 'stats']
        },
        'medium': {
            'description': '中等设备 (512MB-1GB RAM)',
            'workers': 2,
            'max_cache_size': 128 * 1024 * 1024,  # 128MB
            'chunk_size': 64 * 1024,  # 64KB
            'buffer_size': 128 * 1024,  # 128KB
            'db_pool_size': 2,
            'max_connections': 15,
            'monitor_interval': 15,
            'gc_interval': 600,  # 10分钟
            'timeout': 30,
            'disable_optional_features': []
        },
        'high': {
            'description': '高端设备 (1GB+ RAM)',
            'workers': 4,
            'max_cache_size': 256 * 1024 * 1024,  # 256MB
            'chunk_size': 128 * 1024,  # 128KB
            'buffer_size': 256 * 1024,  # 256KB
            'db_pool_size': 4,
            'max_connections': 50,
            'monitor_interval': 5,
            'gc_interval': 900,  # 15分钟
            'timeout': 30,
            'disable_optional_features': []
        },
        'performance': {
            'description': '高性能设备 (4GB+ RAM)',
            'workers': 8,
            'max_cache_size': 1024 * 1024 * 1024,  # 1GB
            'chunk_size': 256 * 1024,  # 256KB
            'buffer_size': 512 * 1024,  # 512KB
            'db_pool_size': 8,
            'max_connections': 200,
            'monitor_interval': 3,
            'gc_interval': 1800,  # 30分钟
            'timeout': 60,
            'disable_optional_features': []
        }
    }

    def __init__(self, preset: str = 'auto', custom_config: dict = None):
        """
        初始化配置

        Args:
            preset: 预设 ('ultra_low', 'low', 'medium', 'high', 'auto')
            custom_config: 自定义配置
        """
        if preset == 'auto':
            preset = self._detect_preset()

        self.preset = preset
        self.config = self.PRESETS.get(preset, self.PRESETS['low']).copy()

        if custom_config:
            self.config.update(custom_config)

    def _detect_preset(self) -> str:
        """自动检测设备配置

        检测逻辑：
        1. 获取总内存和可用内存
        2. 计算可用内存占比
        3. 结合总内存和可用内存占比综合判断
        """
        try:
            import psutil
            mem = psutil.virtual_memory()
            total_ram = mem.total
            available_ram = mem.available
            percent_used = mem.percent  # 已使用百分比

            # 转换为MB
            total_mb = total_ram / (1024 * 1024)

            # 根据总内存和可用内存占比综合判断
            if total_mb < 200:
                # 低于 200MB 总内存
                return 'ultra_low'
            elif total_mb < 400:
                # 200MB - 400MB
                return 'ultra_low'
            elif total_mb < 700:
                # 400MB - 700MB
                if percent_used > 80:
                    return 'ultra_low'
                return 'low'
            elif total_mb < 1200:
                # 700MB - 1.2GB
                if percent_used > 70:
                    return 'ultra_low'
                elif percent_used > 50:
                    return 'low'
                return 'medium'
            elif total_mb < 2500:
                # 1.2GB - 2.5GB
                if percent_used > 70:
                    return 'low'
                elif percent_used > 40:
                    return 'medium'
                return 'high'
            elif total_mb < 5000:
                # 2.5GB - 5GB
                if percent_used > 60:
                    return 'medium'
                return 'high'
            else:
                # 5GB+
                return 'performance'
        except ImportError:
            # 如果没有 psutil，使用保守的 low 配置
            return 'low'
        except Exception:
            return 'low'

    def get_device_info(self) -> dict:
        """获取设备详细信息用于显示"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu_count = psutil.cpu_count(logical=True) or 1

            return {
                'total_ram_mb': mem.total / (1024 * 1024),
                'available_ram_mb': mem.available / (1024 * 1024),
                'percent_used': mem.percent,
                'cpu_count': cpu_count,
                'preset': self.preset
            }
        except Exception:
            return {
                'total_ram_mb': 0,
                'available_ram_mb': 0,
                'percent_used': 0,
                'cpu_count': 1,
                'preset': self.preset
            }

    def apply_to_config(self, base_config: dict) -> dict:
        """应用配置到基础配置"""
        config = base_config.copy()

        # 应用通用设置
        config['workers'] = self.config.get('workers', 1)
        config['max_cache_size'] = self.config.get('max_cache_size', 64 * 1024 * 1024)
        config['chunk_size'] = self.config.get('chunk_size', 64 * 1024)
        config['buffer_size'] = self.config.get('buffer_size', 128 * 1024)
        config['timeout'] = self.config.get('timeout', 30)

        # 数据库池
        if 'database' not in config:
            config['database'] = {}
        config['database']['db_pool_size'] = self.config.get('db_pool_size', 2)

        # 定时 GC 配置
        config['gc_interval'] = self.config.get('gc_interval', 300)

        # 禁用可选功能
        for feature in self.config.get('disable_optional_features', []):
            feature_key = self.FEATURES.get(feature, feature)
            if feature_key.startswith('enable_') or feature_key == 'calculate_hash':
                config[feature_key] = False

        return config

    def get_config(self) -> dict:
        """获取配置"""
        return self.config.copy()

    def get_status(self) -> dict:
        """获取状态"""
        return {
            'preset': self.preset,
            'description': self.config['description'],
            'settings': self.config
        }


# ==================== 流式处理优化 ====================

class StreamingOptimizer:
    """流式处理优化器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.chunk_size = self.config.get('chunk_size', 128 * 1024)
        self.buffer_size = self.config.get('buffer_size', 256 * 1024)

        # 内存池
        self._chunk_pool = None
        self._use_memory_pool = self.config.get('use_memory_pool', True)

    def get_optimized_chunk_size(self, file_size: int) -> int:
        """根据文件大小获取优化的块大小"""
        if file_size < 1024 * 1024:  # < 1MB
            return 16 * 1024  # 16KB
        elif file_size < 10 * 1024 * 1024:  # < 10MB
            return 32 * 1024  # 32KB
        elif file_size < 100 * 1024 * 1024:  # < 100MB
            return 64 * 1024  # 64KB
        else:
            return self.chunk_size

    @contextmanager
    def memory_efficient_file_read(self, file_path: str, chunk_size: int = None):
        """
        内存高效的文件读取

        Usage:
            with optimizer.memory_efficient_file_read('/path/to/file') as f:
                for chunk in f:
                    process(chunk)
        """
        chunk_size = chunk_size or self.chunk_size
        file_size = os.path.getsize(file_path)
        chunk_size = self.get_optimized_chunk_size(file_size)

        file = open(file_path, 'rb')
        try:
            yield file
        finally:
            file.close()

    @contextmanager
    def memory_efficient_file_write(self, file_path: str, chunk_size: int = None):
        """内存高效的文件写入"""
        chunk_size = chunk_size or self.chunk_size
        file = open(file_path, 'wb')
        try:
            yield file
        finally:
            file.close()


# ==================== 架构检测 ====================

class ArchitectureDetector:
    """架构检测器"""

    @staticmethod
    def get_architecture() -> dict:
        """
        获取架构信息

        Returns:
            dict: 包含架构信息的字典
        """
        info = {
            'platform': sys.platform,
            'architecture': 'unknown',
            'machine': 'unknown',
            'processor': 'unknown',
            'python_version': sys.version,
            'byte_order': sys.byteorder
        }

        # 机器类型
        info['machine'] = os.uname().machine if hasattr(os, 'uname') else 'unknown'

        # 检测 32位/64位
        if info['machine'] in ['x86_64', 'amd64', 'aarch64', 'arm64']:
            info['architecture'] = '64bit'
        elif info['machine'] in ['i386', 'i686', 'armv7l', 'armv6l']:
            info['architecture'] = '32bit'
        elif info['machine'] in ['armv8l', 'aarch32']:
            info['architecture'] = '32bit'  # 32位ARM

        # ARM 变体
        if info['machine'].startswith('arm'):
            if info['machine'] in ['armv7l', 'armv7hl']:
                info['arm_variant'] = 'armv7'
            elif info['machine'].startswith('armv8'):
                info['arm_variant'] = 'armv8'
            elif info['machine'].startswith('armv6'):
                info['arm_variant'] = 'armv6'
            else:
                info['arm_variant'] = 'unknown'

        # x86 变体
        if info['machine'] in ['i386', 'i686']:
            info['x86_variant'] = 'i386'
        elif info['machine'] == 'x86_64':
            info['x86_variant'] = 'x86_64'

        return info

    @staticmethod
    def is_low_end_device() -> bool:
        """检测是否为低端设备"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.total < 1024 * 1024 * 1024  # < 1GB
        except Exception:
            return False

    @staticmethod
    def get_recommended_config() -> dict:
        """获取推荐的配置"""
        arch = ArchitectureDetector.get_architecture()

        if arch['architecture'] == '32bit':
            return {
                'max_workers': 2,
                'max_cache_size': 100 * 1024 * 1024,  # 100MB
                'enable_threading': True,
                'use_processes': False,  # 32位进程数有限制
                'max_file_handles': 256
            }
        elif ArchitectureDetector.is_low_end_device():
            return {
                'max_workers': 1,
                'max_cache_size': 50 * 1024 * 1024,  # 50MB
                'enable_threading': True,
                'use_processes': False,
                'max_file_handles': 128
            }
        else:
            return {
                'max_workers': 4,
                'max_cache_size': 500 * 1024 * 1024,  # 500MB
                'enable_threading': True,
                'use_processes': True,
                'max_file_handles': 1024
            }


# ==================== 兼容性检查 ====================

def check_compatibility() -> dict:
    """
    检查系统兼容性

    Returns:
        dict: 兼容性检查结果
    """
    results = {
        'compatible': True,
        'warnings': [],
        'errors': [],
        'info': {}
    }

    # Python 版本检查
    if sys.version_info < (3, 8):
        results['compatible'] = False
        results['errors'].append(f"Python 3.8+ 所需, 当前版本: {sys.version}")

    # 架构信息
    arch_info = ArchitectureDetector.get_architecture()
    results['info']['architecture'] = arch_info

    # 检查必需模块
    required_modules = [
        ('os', '标准库'),
        ('json', '标准库'),
        ('http', '标准库'),
        ('sqlite3', '标准库')
    ]

    optional_modules = [
        ('psutil', '系统监控 (推荐)'),
        ('sqlalchemy', '数据库 (推荐)'),
        (' cryptography', '加密 (推荐)'),
        ('aiohttp', '异步HTTP (可选)'),
        ('paramiko', 'SSH/SFTP (可选)')
    ]

    for module, desc in required_modules:
        try:
            __import__(module)
        except ImportError:
            results['compatible'] = False
            results['errors'].append(f"必需模块缺失: {module} ({desc})")

    for module, desc in optional_modules:
        try:
            __import__(module)
        except ImportError:
            results['warnings'].append(f"可选模块缺失: {module} ({desc})")

    # 内存检查
    try:
        import psutil
        mem = psutil.virtual_memory()
        if mem.total < 256 * 1024 * 1024:
            results['warnings'].append("内存低于 256MB，可能无法正常运行")
    except Exception:
        results['warnings'].append("无法检测内存，可能内存不足")

    # 磁盘空间检查
    try:
        disk = psutil.disk_usage('.')
        if disk.free < 100 * 1024 * 1024:  # 100MB
            results['warnings'].append("可用磁盘空间不足 100MB")
    except Exception:
        pass

    return results


# ==================== 便捷函数 ====================

def get_memory_manager(config: dict = None) -> MemoryManager:
    """获取内存管理器"""
    return MemoryManager(config)


def get_low_memory_config(preset: str = 'auto') -> LowMemoryConfig:
    """获取低端设备配置"""
    return LowMemoryConfig(preset)


def detect_and_configure() -> dict:
    """
    自动检测并配置

    Returns:
        dict: 配置信息
    """
    # 检查兼容性
    compat = check_compatibility()
    if not compat['compatible']:
        print("⚠️ 系统兼容性警告:")
        for error in compat['errors']:
            print(f"  - {error}")

    # 获取推荐配置
    arch_config = ArchitectureDetector.get_recommended_config()

    # 获取低端设备配置
    low_mem_config = get_low_memory_config('auto')
    arch_info = ArchitectureDetector.get_architecture()

    return {
        'compatible': compat['compatible'],
        'architecture': arch_info,
        'recommended': arch_config,
        'low_memory': low_mem_config.get_status(),
        'warnings': compat['warnings']
    }
