# ============================================
# HYC下载站 v2.2 - Docker 构建配置
# ============================================

# 构建阶段
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    musl-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================
# 运行阶段
FROM python:3.11-slim

LABEL maintainer="HYC Download Station"
LABEL description="HYC下载站 v2.2 - 镜像文件服务器 + 下载加速源"

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HYC_HOME=/app

# 创建工作目录
WORKDIR ${HYC_HOME}

# 复制 Python 和依赖
COPY --from=builder /install /usr/local

# 复制应用代码
COPY main.py .
COPY settings.json .
COPY requirements.txt .
COPY core/ ./core/
COPY api/ ./api/
COPY handlers/ ./handlers/
COPY mirrors/ ./mirrors/
COPY scripts/ ./scripts/

# 创建数据目录
RUN mkdir -p \
    /data \
    /downloads \
    && chown -R nobody:nogroup /data /downloads 

# 设置工作用户
USER nobody

# 挂载卷
VOLUME ["/data", "/downloads"]

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/v1/health')" || exit 1

# 启动命令
CMD ["python", "main.py", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--base-dir", "/downloads"]
