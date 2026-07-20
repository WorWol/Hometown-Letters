# ═══════════════════════════════════════════════════════════════
# 故乡来信 — Docker 镜像
# ═══════════════════════════════════════════════════════════════
# 使用方式：
#   docker compose up        # 开发模式（热重载）
#   docker compose up -d     # 后台运行
# ═══════════════════════════════════════════════════════════════

FROM python:3.12-slim

# ECS 默认使用阿里云 PyPI 镜像，避免生产机从境外 PyPI 慢速下载依赖。
# 可在构建时通过 PIP_INDEX_URL 覆盖。
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

LABEL org.opencontainers.image.title="故乡来信"
LABEL org.opencontainers.image.description="Hometown Letters — 像素风书信生成应用"

# ── 工作目录 ──
WORKDIR /app

# ── 安装 Python 依赖 ──
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --timeout 60 \
    --retries 5 \
    -r /app/backend/requirements.txt

# ── 复制全部代码 ──
COPY . /app/

# ── 暴露端口 ──
EXPOSE 8787

# ── 启动 ──
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8787"]
WORKDIR /app/backend
