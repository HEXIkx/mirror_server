#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""工具函数模块"""

import os
import re
import hashlib


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小为可读格式"""
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.2f} {size_names[i]}"


def get_file_hash(filepath: str, algorithm: str = 'sha256') -> str:
    """计算文件哈希值"""
    if not filepath or not isinstance(filepath, str):
        return "Error: Invalid filepath"

    if not os.path.exists(filepath):
        return "Error: File not found"

    try:
        hash_func = hashlib.new(algorithm)
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except Exception as e:
        return f"Error: {str(e)}"


def parse_size(size_str: str) -> int:
    """解析文件大小字符串为字节数"""
    size_str = size_str.upper().strip()
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([BKMGT]?)B?$', size_str)
    if not match:
        raise ValueError(f"无效的文件大小格式: {size_str}")

    number = float(match.group(1))
    unit = match.group(2) or 'B'

    units = {
        'B': 1,
        'K': 1024,
        'M': 1024 ** 2,
        'G': 1024 ** 3,
        'T': 1024 ** 4
    }

    if unit not in units:
        raise ValueError(f"无效的单位: {unit}")

    return int(number * units[unit])


def sanitize_filename(filename: str) -> str:
    """清理文件名，防止路径遍历和安全问题"""
    filename = os.path.basename(filename)  # 移除路径分隔符

    # 移除危险字符
    filename = re.sub(r'[<>:"|?*\\\x00-\x1f]', '_', filename)

    # 限制长度
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext

    # 防止空文件名
    if not filename or filename in ('.', '..'):
        filename = 'unnamed_file'

    return filename


def is_safe_path(base_dir: str, path: str) -> bool:
    """检查路径是否安全（防止目录遍历）"""
    try:
        abs_path = os.path.abspath(path)
        abs_base = os.path.abspath(base_dir)
        common_path = os.path.commonpath([abs_path, abs_base])
        return common_path == abs_base
    except ValueError:
        return False
