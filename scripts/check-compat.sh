#!/bin/bash
# ============================================
# HYC下载站 v2.2 - 系统兼容性检查脚本
# 支持: X86_32, X86_64, ARMv7, ARM64, MIPS 等
# ============================================

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "  HYC下载站 v2.2 - 兼容性检查"
echo "========================================"
echo

# 检测架构
ARCH=$(uname -m)
OS=$(uname -s)
echo "系统信息:"
echo "  - 架构: $ARCH"
echo "  - 系统: $OS"
echo

# 架构特定配置
case "$ARCH" in
    x86_64)
        echo "✓ x86_64 (64位) - 完全支持"
        RECOMMENDED_WORKERS=4
        ;;
    i386|i686)
        echo "⚠ i386/i686 (32位) - 有限支持"
        RECOMMENDED_WORKERS=2
        echo "  建议: --workers 2"
        ;;
    armv7l|armv7hl)
        echo "✓ ARMv7 (32位) - 完全支持"
        RECOMMENDED_WORKERS=2
        ;;
    armv8l|aarch64)
        echo "✓ ARM64 (64位) - 完全支持"
        RECOMMENDED_WORKERS=4
        ;;
    armv6l)
        echo "⚠ ARMv6 - 有限支持 (可能需要重新编译)"
        RECOMMENDED_WORKERS=1
        ;;
    mips*)
        echo "⚠ MIPS - 实验性支持"
        RECOMMENDED_WORKERS=1
        ;;
    *)
        echo "⚠ 未知架构: $ARCH - 需要测试"
        RECOMMENDED_WORKERS=1
        ;;
esac
echo

# Python 版本检查
PYTHON_VERSION=$(python3 --version 2>&1 || echo "未安装")
echo "Python 版本: $PYTHON_VERSION"

PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")

if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
    echo "✓ Python 3.8+ - 支持"
else
    echo "✗ 需要 Python 3.8 或更高版本"
    exit 1
fi
echo

# 内存检查
echo "内存检查:"
if command -v free &> /dev/null; then
    TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
    echo "  - 总内存: ${TOTAL_MEM}MB"

    if [ "$TOTAL_MEM" -lt 256 ]; then
        echo "⚠ 内存低于 256MB - 使用 ultra_low 预设"
        echo "  python main.py --preset ultra_low"
    elif [ "$TOTAL_MEM" -lt 512 ]; then
        echo "⚠ 内存 256-512MB - 使用 low 预设"
        echo "  python main.py --preset low"
    elif [ "$TOTAL_MEM" -lt 1024 ]; then
        echo "✓ 内存 512MB-1GB - 使用 medium 预设 (默认)"
    else
        echo "✓ 内存 1GB+ - 使用 high 预设 (默认)"
    fi
else
    echo "  (无法检测，使用默认配置)"
fi
echo

# 磁盘空间检查
echo "磁盘空间检查:"
DISK_FREE=$(df -BG . | awk '/^\//{print $4}' | sed 's/G//')
echo "  - 可用: ${DISK_FREE}GB"

if [ "$DISK_FREE" -lt 1 ]; then
    echo "⚠ 可用空间不足 1GB"
fi
echo

# 必需依赖检查
echo "必需依赖检查:"
MISSING_DEPS=""

check_dep() {
    if command -v "$1" &> /dev/null; then
        echo "  ✓ $1"
    else
        echo "  ✗ $1 (必需)"
        MISSING_DEPS="$MISSING_DEPS $1"
    fi
}

check_dep "python3"
echo

# 可选依赖检查
echo "可选依赖检查:"
check_opt() {
    if command -v "$1" &> /dev/null; then
        echo "  ✓ $1"
    else
        echo "  ⚠ $1 (可选)"
    fi
}

check_opt "psutil"  || pip3 install psutil
check_opt "sqlalchemy" || pip3 install sqlalchemy
echo

# Docker 构建检查 (如果使用 Docker)
if [ -f "../Dockerfile" ]; then
    echo "Docker 构建检查:"
    if command -v docker &> /dev/null; then
        echo "  ✓ Docker 可用"

        # 检查 buildx 支持
        if docker buildx version &> /dev/null; then
            echo "  ✓ Docker BuildX 支持多架构构建"
            echo
            echo "多架构构建命令:"
            echo "  docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t hyc:v2.2 ."
        fi
    else
        echo "  ⚠ Docker 不可用 (需要安装 Docker)"
    fi
    echo
fi

# 推荐启动命令
echo "========================================"
echo "  推荐启动命令"
echo "========================================"

# 根据检测结果生成推荐命令
CMD="python main.py --preset "

if [ "$TOTAL_MEM" -lt 256 ]; then
    CMD="${CMD}ultra_low"
elif [ "$TOTAL_MEM" -lt 512 ]; then
    CMD="${CMD}low"
elif [ "$TOTAL_MEM" -lt 1024 ]; then
    CMD="${CMD}medium"
else
    CMD="${CMD}high"
fi

echo
echo "$CMD"
echo

# 完整命令示例
echo "完整示例:"
echo "  $CMD --host 0.0.0.0 --port 8080 --base-dir ./downloads"
echo
