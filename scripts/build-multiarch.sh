#!/bin/bash
# ============================================
# HYC下载站 v2.2 - 多架构 Docker 构建脚本
# 支持: amd64, arm64, arm/v7, i386
# ============================================

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION=${1:-v2.2}
REGISTRY=${2:-hyc-download-station}
TAG=${3:-$VERSION}

# 支持的平台
PLATFORMS="linux/amd64,linux/arm64,linux/arm/v7,linux/386"

echo "========================================"
echo "  HYC下载站 v2.2 - 多架构构建"
echo "========================================"
echo "  版本: $TAG"
echo "  平台: $PLATFORMS"
echo

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker 未安装${NC}"
    exit 1
fi

# 检查 BuildX
if ! docker buildx version &> /dev/null; then
    echo -e "${YELLOW}⚠ Docker BuildX 未安装，尝试安装...${NC}"
    docker buildx install || true
fi

# 创建构建器
echo "[1/4] 创建构建器..."
docker buildx rm hyc-builder 2>/dev/null || true
docker buildx create \
    --name hyc-builder \
    --platform $PLATFORMS \
    --use

# 引导构建器
echo "[2/4] 引导构建器..."
docker buildx inspect --bootstrap

# 构建镜像
echo "[3/4] 构建镜像..."
echo "  构建中，请稍候..."

START_TIME=$(date +%s)

docker buildx build \
    --platform $PLATFORMS \
    --tag "$REGISTRY:$TAG" \
    --tag "$REGISTRY:latest" \
    --push \
    --file docker/Dockerfile.multiarch \
    .

END_TIME=$(date +%s)
BUILD_TIME=$((END_TIME - START_TIME))

echo -e "${GREEN}✓ 构建完成 (${BUILD_TIME}秒)${NC}"

# 推送清单
echo "[4/4] 创建清单..."
docker manifest create "$REGISTRY:$TAG" \
    "$REGISTRY:$TAG-amd64" \
    "$REGISTRY:$TAG-arm64" \
    "$REGISTRY:$TAG-arm-v7" \
    "$REGISTRY:$TAG-386" 2>/dev/null || true

docker manifest push "$REGISTRY:$TAG" || true

echo
echo "========================================"
echo -e "${GREEN}✓ 多架构构建完成${NC}"
echo "========================================"
echo
echo "镜像标签:"
echo "  - $REGISTRY:$TAG"
echo "  - $REGISTRY:latest"
echo
echo "推送到仓库:"
echo "  docker pull $REGISTRY:$TAG"
echo
