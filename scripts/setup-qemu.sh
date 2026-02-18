#!/bin/bash
# ============================================
# HYC下载站 v2.2 - QEMU 仿真支持设置
# 用于在 x86_64 上构建 ARM 镜像
# ============================================

set -e

echo "========================================"
echo "  QEMU 仿真支持设置"
echo "========================================"

# 检查是否需要设置
if [ "$(uname -m)" = "x86_64" ]; then
    echo "检测到 x86_64 平台"
    echo "将启用 ARM/i386 仿真支持"
fi

# 启用 QEMU 仿真
echo
echo "[1/3] 检查 QEMU ..."

# 注册 ARM 二进制格式
if [ -f /usr/bin/qemu-arm-static ]; then
    echo "✓ qemu-arm-static 已安装"
    docker run --rm --privileged multiarch/qemu-user-static --reset -p yes || true
elif [ -f /usr/bin/qemu-arm ]; then
    echo "✓ qemu-arm 已安装"
else
    echo "⚠ QEMU 未安装，正在安装..."
    apt-get update && apt-get install -y qemu-user-static || \
    yum install -y qemu-user-static || \
    apk add --no-cache qemu-arm qemu-i386
fi

# 设置 binfmt-misc
echo
echo "[2/3] 注册二进制格式..."
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes 2>/dev/null || \
    echo "  (可能需要手动配置)"

echo
echo "[3/3] 验证设置..."
echo "可用的仿真架构:"

for arch in arm arm64 i386; do
    if [ -f "/usr/bin/qemu-$arch-static" ] || [ -f "/usr/bin/qemu-$arch" ]; then
        echo "  ✓ $arch"
    else
        echo "  ✗ $arch"
    fi
done

echo
echo "========================================"
echo "✓ QEMU 设置完成"
echo "========================================"
echo
echo "现在可以构建多架构镜像:"
echo "  ./scripts/build-multiarch.sh"
echo
