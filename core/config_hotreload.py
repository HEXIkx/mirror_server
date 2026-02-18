#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置热更新模块
支持不重启服务的情况下重新加载配置
"""

import os
import sys
import json
import time
import threading
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfigHotReloader:
    """配置热重载管理器"""

    def __init__(self, config_path: str, callback: Callable = None):
        """
        初始化热重载管理器

        Args:
            config_path: 配置文件路径
            callback: 配置变更时的回调函数，接收 (config, change_type) 参数
        """
        self.config_path = config_path
        self.callback = callback

        self._config: Dict[str, Any] = {}
        self._last_modified: float = 0
        self._last_load_time: Optional[datetime] = None
        self._lock = threading.RLock()

        # 配置变更历史
        self._change_history: list = []

        # 监听器
        self._listeners: Dict[str, list] = {
            'on_change': [],
            'on_error': []
        }

        # 加载初始配置
        self.reload()

    def reload(self, silent: bool = False) -> bool:
        """
        重新加载配置

        Args:
            silent: 静默模式，不触发变更通知

        Returns:
            是否加载成功
        """
        try:
            if not os.path.exists(self.config_path):
                if not silent:
                    logger.warning(f"配置文件不存在: {self.config_path}")
                return False

            # 获取文件修改时间
            current_mtime = os.path.getmtime(self.config_path)

            # 检查是否有变化
            if current_mtime == self._last_modified and not silent:
                return True

            # 加载配置
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_config = json.load(f)

            # 计算变更
            changes = self._compute_changes(self._config, new_config)

            with self._lock:
                old_config = self._config.copy()
                self._config = new_config
                self._last_modified = current_mtime
                self._last_load_time = datetime.now()

            # 记录变更
            if changes:
                change_record = {
                    'timestamp': self._last_load_time.isoformat(),
                    'changes': changes,
                    'old_config_keys': list(old_config.keys()),
                    'new_config_keys': list(new_config.keys())
                }
                self._change_history.append(change_record)

                # 保持历史记录在合理范围内
                if len(self._change_history) > 100:
                    self._change_history = self._change_history[-50:]

            if not silent and changes:
                self._notify_change(changes)

            logger.info(f"配置已重新加载: {self.config_path}")
            return True

        except json.JSONDecodeError as e:
            error_msg = f"配置 JSON 格式错误: {e}"
            logger.error(error_msg)
            self._notify_error(error_msg)
            return False
        except Exception as e:
            error_msg = f"加载配置失败: {e}"
            logger.error(error_msg)
            self._notify_error(error_msg)
            return False

    def _compute_changes(self, old: Dict, new: Dict) -> Dict:
        """计算配置变更"""
        changes = {
            'added': [],
            'removed': [],
            'modified': []
        }

        old_keys = set(old.keys())
        new_keys = set(new.keys())

        # 新增的键
        for key in new_keys - old_keys:
            changes['added'].append(key)

        # 移除的键
        for key in old_keys - new_keys:
            changes['removed'].append(key)

        # 修改的键
        for key in old_keys & new_keys:
            if old[key] != new[key]:
                # 检查是否是嵌套字典
                if isinstance(old[key], dict) and isinstance(new[key], dict):
                    nested = self._compute_nested_changes(old[key], new[key], f"{key}.")
                    if nested['added'] or nested['removed'] or nested['modified']:
                        changes['modified'].append({
                            'key': key,
                            'type': 'nested',
                            'changes': nested
                        })
                else:
                    changes['modified'].append({
                        'key': key,
                        'type': 'value',
                        'old_value': old[key],
                        'new_value': new[key]
                    })

        return changes

    def _compute_nested_changes(self, old: Dict, new: Dict, prefix: str = "") -> Dict:
        """计算嵌套字典的变更"""
        changes = {
            'added': [],
            'removed': [],
            'modified': []
        }

        old_keys = set(old.keys())
        new_keys = set(new.keys())

        for key in new_keys - old_keys:
            changes['added'].append(f"{prefix}{key}")

        for key in old_keys - new_keys:
            changes['removed'].append(f"{prefix}{key}")

        for key in old_keys & new_keys:
            if old[key] != new[key]:
                changes['modified'].append(f"{prefix}{key}")

        return changes

    def _notify_change(self, changes: Dict):
        """通知配置变更"""
        for listener in self._listeners['on_change']:
            try:
                if callable(listener):
                    listener(self._config, changes)
            except Exception as e:
                logger.error(f"配置变更监听器执行失败: {e}")

        if self.callback:
            try:
                self.callback(self._config, changes)
            except Exception as e:
                logger.error(f"配置回调函数执行失败: {e}")

    def _notify_error(self, error: str):
        """通知错误"""
        for listener in self._listeners['on_error']:
            try:
                if callable(listener):
                    listener(error)
            except Exception as e:
                logger.error(f"错误监听器执行失败: {e}")

    def add_change_listener(self, callback: Callable):
        """添加配置变更监听器"""
        self._listeners['on_change'].append(callback)

    def add_error_listener(self, callback: Callable):
        """添加错误监听器"""
        self._listeners['on_error'].append(callback)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            return self._config.get(key, default)

    def get_all(self) -> Dict:
        """获取完整配置"""
        with self._lock:
            return self._config.copy()

    def set(self, key: str, value: Any, save: bool = True) -> bool:
        """设置配置值（仅内存中）"""
        with self._lock:
            self._config[key] = value

        if save:
            return self.save()

        return True

    def save(self, path: str = None) -> bool:
        """保存配置到文件"""
        save_path = path or self.config_path

        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
            self._last_modified = os.path.getmtime(save_path)
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False

    def get_change_history(self, limit: int = 10) -> list:
        """获取配置变更历史"""
        return self._change_history[-limit:]

    def watch(self, interval: float = 5.0):
        """
        启动后台监控线程

        Args:
            interval: 检查间隔（秒）
        """
        def _watch_loop():
            while True:
                try:
                    self.reload()
                except Exception as e:
                    logger.error(f"配置监控错误: {e}")
                time.sleep(interval)

        thread = threading.Thread(target=_watch_loop, daemon=True)
        thread.start()
        logger.info(f"配置热监控已启动，间隔: {interval}秒")


class ConfigManager:
    """配置管理器 - 支持热更新"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._hot_reloader: Optional[ConfigHotReloader] = None

    def load_from_file(self, path: str, enable_watch: bool = False) -> bool:
        """从文件加载配置"""
        if not os.path.exists(path):
            return False

        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

            if enable_watch:
                self._hot_reloader = ConfigHotReloader(path)
                self._hot_reloader.watch()

            return True
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return False

    def hot_reload(self, path: str = None) -> bool:
        """触发热重载"""
        if self._hot_reloader:
            return self._hot_reloader.reload()
        return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any, persist: bool = False, path: str = None) -> bool:
        """设置配置值"""
        keys = key.split('.')
        current = self.config

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

        if persist:
            if self._hot_reloader:
                return self._hot_reloader.save(path)
            elif path:
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.config, f, ensure_ascii=False, indent=4)
                    return True
                except Exception as e:
                    logger.error(f"保存配置失败: {e}")
                    return False

        return True

    def add_change_listener(self, callback: Callable):
        """添加变更监听器"""
        if self._hot_reloader:
            self._hot_reloader.add_change_listener(callback)

    def get_all(self) -> Dict:
        """获取完整配置"""
        return self.config.copy()
