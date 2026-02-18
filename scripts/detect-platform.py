#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
平台检测工具
自动检测系统架构并推荐配置
"""

import sys
import os

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.optimization import (
    ArchitectureDetector, LowMemoryConfig, check_compatibility
)


def main():
    print("=" * 60)
    print("  HYC下载站 v2.2 - 平台检测")
    print("=" * 60)
    print()

    # 架构检测
    print("[1/3] 架构信息")
    arch = ArchitectureDetector.get_architecture()
    for key, value in arch.items():
        print(f"  {key}: {value}")
    print()

    # 兼容性检查
    print("[2/3] 兼容性检查")
    compat = check_compatibility()
    print(f"  兼容状态: {'✓ 通过' if compat['compatible'] else '✗ 有问题'}")
    if compat['warnings']:
        print("  警告:")
        for w in compat['warnings']:
            print(f"    ⚠ {w}")
    print()

    # 推荐配置
    print("[3/3] 推荐配置")
    recommended = ArchitectureDetector.get_recommended_config()
    for key, value in recommended.items():
        print(f"  {key}: {value}")

    # 低内存配置
    low_mem = LowMemoryConfig('auto')
    status = low_mem.get_status()
    print()
    print("  自动检测预设:")
    print(f"    - 预设: {status['preset']}")
    print(f"    - 描述: {status['description']}")
    print()
    print("  建议启动命令:")
    cmd = f"python main.py --preset {status['preset']}"
    if 'ultra_low' in str(status):
        cmd += " --disable-ws --disable-sse"
    print(f"    {cmd}")
    print()

    # 返回状态码
    return 0 if compat['compatible'] else 1


if __name__ == '__main__':
    sys.exit(main())
