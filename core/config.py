#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""配置管理模块"""

import os
import sys
import json
import hashlib
import time
from typing import Dict, Any, Optional

from .utils import parse_size


def get_resource_path(relative_path: str) -> str:
    """获取打包后的资源路径"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 打包后的路径
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)

    # 打包模式
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 外部目录：与 exe 同级
        external_path = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(external_path):
            return external_path

        # 打包后的资源路径（_MEIPASS）
        bundled_path = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(bundled_path):
            return bundled_path

        return external_path

    # 开发模式
    return os.path.join(project_root, relative_path)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    深度合并配置
    - 如果 override 中有的键，会完全替换 base 中的值（除非都是 dict）
    - 如果都是 dict，则递归合并
    - 不会修改原参数

    Args:
        base: 默认配置（基础配置）
        override: 要合并的配置（优先级更高）

    Returns:
        合并后的配置
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # 两者都是字典，递归合并
            result[key] = deep_merge(result[key], value)
        else:
            # 直接覆盖
            result[key] = value

    return result


def load_json_config(file_path: str) -> Optional[Dict[str, Any]]:
    """加载 JSON 配置文件"""
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"警告: 配置文件 {file_path} JSON 格式错误: {e}")
        return None
    except Exception as e:
        print(f"警告: 无法读取配置文件 {file_path}: {e}")
        return None


class ConfigManager:
    """配置管理器"""

    def __init__(self, config: Dict[str, Any] = None, settings_path: str = None):
        """
        初始化配置管理器

        Args:
            config: 传入的配置（会覆盖默认配置）
            settings_path: 默认配置文件路径（可以是位置参数或关键字参数）
        """
        # 支持 settings_path 作为位置参数
        if isinstance(config, str):
            settings_path = config
            config = None
        elif settings_path is None:
            # 使用打包后的资源路径
            settings_path = get_resource_path('settings.json')
        elif settings_path:
            settings_path = settings_path

        self._settings_path = settings_path

        # 加载默认配置
        self.default_config = self._load_default_config()

        # 合并传入的配置
        if config:
            self.config = self._validate_config(deep_merge(self.default_config, config))
        else:
            self.config = self._validate_config(self.default_config.copy())

    def _load_default_config(self) -> Dict[str, Any]:
        """加载默认配置文件"""
        default_config = load_json_config(self._settings_path)
        if default_config is None:
            # 如果找不到默认配置，使用内联最小配置
            default_config = {
                'server_name': 'HYC下载站',
                'host': '0.0.0.0',
                'port': 8080,
                'base_dir': './downloads',
                'api_version': 'v2',
                'directory_listing': True,
                'enable_stats': True,
                'auth_type': 'none',
                'max_upload_size': 1024 * 1024 * 1024,
                'timeout': 30,
                'verbose': 0,
                'enable_range': True,
                'ignore_hidden': True,
                'show_hash': False,
                'calculate_hash': False,
                'max_search_results': 100,
                'enable_ws': True,
                'enable_sse': True,
                'enable_monitor': True,
                'monitor_interval': 5,
                'enable_sync': True,
                'enable_mirrors': True,
                'database': {
                    'enabled': True,
                    'type': 'sqlite',
                    'sqlite': {'path': './data/hyc.db'}
                },
                'mirrors': {
                    'docker': {'enabled': True},
                    'apt': {'enabled': True},
                    'yum': {'enabled': True},
                    'pypi': {'enabled': True},
                    'npm': {'enabled': True},
                    'go': {'enabled': True}
                },
                'sync_sources': {},
                'webhooks': {'enabled': False, 'storage': 'webhooks.json'},
                'admin_keys_file': 'admin_keys.json',
                'auth_sessions_file': 'auth_sessions.json',
                'auth_session_timeout': 3600,
                'auth_cookie_max_age': 86400
            }
            print(f"警告: 未找到默认配置文件 ({self._settings_path})，使用内联默认配置")
        return default_config

    @classmethod
    def from_settings(cls, custom_config: Dict[str, Any] = None, settings_path: str = None) -> 'ConfigManager':
        """
        从默认配置创建配置管理器

        Args:
            custom_config: 自定义配置，会覆盖默认配置
            settings_path: 默认配置文件路径

        Returns:
            ConfigManager 实例
        """
        return cls(config=custom_config, settings_path=settings_path)

    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证和修复配置"""
        # 确保必要配置存在
        required = ['base_dir', 'host', 'port']
        for key in required:
            if key not in config:
                raise ValueError(f"缺少必要配置: {key}")

        # 修复路径配置
        config['base_dir'] = os.path.abspath(config['base_dir'])

        # 设置默认值（不在 _validate_config 中处理，由默认配置提供）

        # 验证认证配置
        auth_type = config.get('auth_type', 'none')
        if auth_type == 'basic':
            if 'auth_user' not in config:
                config['auth_user'] = 'admin'
            if 'auth_pass' not in config:
                config['auth_pass'] = 'admin123'
        elif auth_type == 'token':
            # 每次运行都重新生成标准的 token
            import secrets
            config['auth_token'] = secrets.token_hex(32)

        # 验证上传大小配置
        if 'max_upload_size' in config:
            try:
                if isinstance(config['max_upload_size'], str):
                    config['max_upload_size'] = parse_size(config['max_upload_size'])
            except ValueError as e:
                print(f"警告: 无效的上传大小配置: {e}")
                config['max_upload_size'] = 1024 * 1024 * 1024

        # 验证端口范围
        if 'port' in config:
            port = config['port']
            if not (1 <= port <= 65535):
                raise ValueError(f"无效的端口号: {port}")

        # 验证并创建必要目录
        base_dir = config['base_dir']
        try:
            if not os.path.exists(base_dir):
                os.makedirs(base_dir, exist_ok=True)

            # 测试写入权限
            test_file = os.path.join(base_dir, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)

        except Exception as e:
            raise ValueError(f"基础目录无法访问: {e}")

        # 获取项目根目录（脚本所在目录）
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 在项目根目录创建必要的数据目录
        necessary_dirs = [
            os.path.join(project_root, 'data'),
            os.path.join(project_root, 'logs'),
        ]

        for dir_path in necessary_dirs:
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                except Exception as e:
                    print(f"警告: 无法创建目录 {dir_path}: {e}")

        # 更新配置指向项目根目录
        config['data_dir'] = os.path.join(project_root, 'data')
        config['logs_dir'] = os.path.join(project_root, 'logs')

        return config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)

    def update(self, updates: Dict[str, Any]):
        """更新配置"""
        self.config.update(updates)
        self.config = self._validate_config(self.config)

    def get_full_config(self) -> Dict[str, Any]:
        """获取完整配置字典"""
        return self.config.copy()

    def to_dict(self) -> Dict[str, Any]:
        """返回配置字典（不包含敏感信息）"""
        safe_config = {
            "server_name": self.config.get("server_name", "Mirror Server"),
            "version": "2.2",
            "base_dir": self.config['base_dir'],
            "directory_listing": self.config.get('directory_listing', True),
            "max_upload_size": self.config.get('max_upload_size'),
            "enable_stats": self.config.get('enable_stats', True),
            "auth_type": self.config.get('auth_type', 'none'),
            "sort_by": self.config.get('sort_by', 'name'),
            "sort_reverse": self.config.get('sort_reverse', False),
            "ignore_hidden": self.config.get('ignore_hidden', True),
            "enable_range": self.config.get('enable_range', True),
            "show_hash": self.config.get('show_hash', False),
            "calculate_hash": self.config.get('calculate_hash', False),
            "max_search_results": self.config.get('max_search_results', 100),
            "api_version": self.config.get('api_version', 'v1'),
            "verbose": self.config.get('verbose', 0)
        }
        return safe_config


def load_config_file(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    if not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"错误: 无法加载配置文件 {config_path}: {e}")
        return {}


def load_settings_with_override(settings_path: str, override_path: str = None) -> Dict[str, Any]:
    """
    加载默认配置并合并覆盖配置

    Args:
        settings_path: 默认配置文件路径
        override_path: 覆盖配置文件路径（可选）

    Returns:
        合并后的完整配置
    """
    # 加载默认配置
    default_config = load_json_config(settings_path) or {}

    # 加载覆盖配置
    override_config = {}
    if override_path:
        override_config = load_json_config(override_path) or {}

    # 深度合并
    return deep_merge(default_config, override_config)


def save_config_file(config_path: str, config: Dict[str, Any]) -> bool:
    """
    保存配置文件

    Args:
        config_path: 保存路径
        config: 配置字典

    Returns:
        是否保存成功
    """
    try:
        # 创建目录
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

        return True
    except Exception as e:
        print(f"错误: 无法保存配置文件 {config_path}: {e}")
        return False
