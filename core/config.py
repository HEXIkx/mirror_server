#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""配置管理模块"""

import os
import json
import hashlib
import time
from typing import Dict, Any

from .utils import parse_size


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """初始化配置管理器"""
        self.config = self._validate_config(config or {})
        
    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证和修复配置"""
        # 确保必要配置存在
        required = ['base_dir', 'host', 'port']
        for key in required:
            if key not in config:
                raise ValueError(f"缺少必要配置: {key}")
        
        # 修复路径配置
        config['base_dir'] = os.path.abspath(config['base_dir'])
        
        # 设置默认值
        defaults = {
            'server_name': 'HYC下载站',
            'directory_listing': True,
            'enable_stats': True,
            'auth_type': 'none',
            'max_upload_size': 1024 * 1024 * 1024,  # 1GB
            'timeout': 30,
            'verbose': 0,
            'enable_range': True,
            'sort_by': 'name',
            'sort_reverse': False,
            'ignore_hidden': True,
            'show_hash': False,
            'calculate_hash': False,
            'max_search_results': 100,
            'max_preview_size': 10 * 1024 * 1024,  # 10MB
            'overwrite_existing': False,
            'api_version': 'v1'  # 默认API版本
        }
        
        for key, value in defaults.items():
            if key not in config:
                config[key] = value
                
        # 验证认证配置
        auth_type = config['auth_type']
        if auth_type == 'basic':
            if 'auth_user' not in config:
                config['auth_user'] = 'admin'
            if 'auth_pass' not in config:
                config['auth_pass'] = 'admin123'
        elif auth_type == 'token':
            if 'auth_token' not in config:
                config['auth_token'] = hashlib.md5(str(time.time()).encode()).hexdigest()
        
        # 验证上传大小配置
        if 'max_upload_size' in config:
            try:
                if isinstance(config['max_upload_size'], str):
                    config['max_upload_size'] = parse_size(config['max_upload_size'])
            except ValueError as e:
                print(f"警告: 无效的上传大小配置: {e}")
                config['max_upload_size'] = 1024 * 1024 * 1024  # 默认1GB
        
        # 验证端口范围
        if 'port' in config:
            port = config['port']
            if not (1 <= port <= 65535):
                raise ValueError(f"无效的端口号: {port}")
        
        # 验证基础目录权限
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
        
        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)
    
    def update(self, updates: Dict[str, Any]):
        """更新配置"""
        self.config.update(updates)
        self.config = self._validate_config(self.config)
    
    def to_dict(self) -> Dict[str, Any]:
        """返回配置字典（不包含敏感信息）"""
        safe_config = {
            "server_name": self.config.get("server_name", "Mirror Server"),
            "version": "2.0",
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
