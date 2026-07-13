#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# 故乡来信 — 一键启动脚本（Mac / Linux）
# ═══════════════════════════════════════════════════════════════
# 自动：创建虚拟环境 → 安装依赖 → 加载 .env → 启动服务
#
# 使用方法：
#   ./start.sh              # 一键启动
#   ./start.sh --port 9090  # 指定端口
#   ./start.sh --setup-only # 仅创建 venv + 安装依赖
#
# Windows 用户请使用: .\start.ps1 (PowerShell)
# Docker 用户请使用:  docker compose up
# 跨平台 Python:      python run.py
# ═══════════════════════════════════════════════════════════════

set -e

# ── 解析命令行参数 ──
HOST="0.0.0.0"
PORT=8787
SETUP_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --host) HOST="$2"; shift 2 ;;
        --setup-only) SETUP_ONLY=true; shift ;;
        *) echo "未知参数: $1"; echo "用法: $0 [--port PORT] [--host HOST] [--setup-only]"; exit 1 ;;
    esac
done

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.example"

echo -e "${CYAN}══════════════════════════════════════${NC}"
echo -e "${CYAN}  故乡来信 — 服务启动脚本${NC}"
echo -e "${CYAN}══════════════════════════════════════${NC}"
echo ""

# ── 1. 检查 .env ──
if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}[✓] 发现 .env 文件，加载环境变量...${NC}"
    set -a
    source "$ENV_FILE"
    set +a
else
    echo -e "${YELLOW}[!] 未找到 .env 文件${NC}"
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo -e "${YELLOW}    已从 .env.example 复制模板${NC}"
        echo -e "${YELLOW}    请编辑 .env 文件填入 API Key 后重新运行${NC}"
    else
        echo -e "${YELLOW}    使用默认配置（功能受限）${NC}"
    fi
fi

# ── 2. 检查关键 API Key ──
if [ -z "$SERPER_API_KEY" ]; then
    echo -e "${YELLOW}[!] SERPER_API_KEY 未设置，搜索功能将不可用${NC}"
fi
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo -e "${YELLOW}[!] DEEPSEEK_API_KEY 未设置，LLM 功能将不可用${NC}"
fi
if [ -z "$VOLC_API_KEY" ]; then
    echo -e "${YELLOW}[!] VOLC_API_KEY 未设置，生图功能将不可用${NC}"
fi

# ── 3. 打印代理状态 ──
echo ""
echo -e "${CYAN}── 网络代理状态 ──${NC}"
if [ -n "$SERPER_PROXY_URL" ]; then
    echo -e "  Serper  (搜图):     ${GREEN}代理 $SERPER_PROXY_URL${NC}"
else
    echo -e "  Serper  (搜图):     ${YELLOW}直连（如无法访问请配置代理）${NC}"
fi
if [ -n "$DEEPSEEK_PROXY_URL" ]; then
    echo -e "  DeepSeek (LLM):     ${GREEN}代理 $DEEPSEEK_PROXY_URL${NC}"
else
    echo -e "  DeepSeek (LLM):     ${GREEN}直连${NC}"
fi
if [ -n "$VOLC_PROXY_URL" ]; then
    echo -e "  火山引擎 (生图):    ${GREEN}代理 $VOLC_PROXY_URL${NC}"
else
    echo -e "  火山引擎 (生图):    ${GREEN}直连${NC}"
fi

if [ -n "$IMAGE_CACHE_ENABLED" ] && [ "$IMAGE_CACHE_ENABLED" = "true" ]; then
    echo -e "  生图缓存:           ${GREEN}已开启（省钱模式）${NC}"
else
    echo -e "  生图缓存:           ${YELLOW}已关闭${NC}"
fi

# ── 4. 进入后端目录 ──
echo ""
echo -e "${CYAN}── 启动后端服务 ──${NC}"
cd "$BACKEND_DIR"

# ── 5. 检测/创建 Python 虚拟环境 ──
VENV_DIR=""
if [ -d "$BACKEND_DIR/venv" ]; then
    VENV_DIR="$BACKEND_DIR/venv"
elif [ -d "$BACKEND_DIR/.venv" ]; then
    VENV_DIR="$BACKEND_DIR/.venv"
fi

if [ -n "$VENV_DIR" ]; then
    echo -e "${GREEN}[✓] 使用虚拟环境: $VENV_DIR${NC}"
else
    echo -e "${YELLOW}[!] 未检测到虚拟环境，正在创建...${NC}"
    VENV_DIR="$BACKEND_DIR/.venv"
    python3 -m venv "$VENV_DIR" 2>/dev/null || python -m venv "$VENV_DIR" 2>/dev/null || {
        echo -e "${RED}[✗] 虚拟环境创建失败，请确认 Python 3.10+ 已安装${NC}"
        exit 1
    }
    echo -e "${GREEN}[✓] 虚拟环境创建成功: $VENV_DIR${NC}"
fi

# 激活虚拟环境
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo -e "${RED}[✗] 无法激活虚拟环境: $VENV_DIR${NC}"
    exit 1
fi

# ── 6. 安装依赖 ──
echo -e "${GREEN}[✓] 检查依赖...${NC}"
pip install -q -r requirements.txt 2>/dev/null || {
    echo -e "${RED}[✗] 依赖安装失败，请手动执行: pip install -r requirements.txt${NC}"
    exit 1
}

# ── 7. 启动 ──
if $SETUP_ONLY; then
    echo ""
    echo -e "${GREEN}[✓] 环境设置完成！${NC}"
    echo -e "${GREEN}    虚拟环境: $VENV_DIR${NC}"
    echo -e "${GREEN}    启动命令: ./start.sh${NC}"
    exit 0
fi

echo -e "${GREEN}[✓] 启动服务: http://${HOST}:${PORT}${NC}"
echo -e "${GREEN}[✓] API 文档: http://${HOST}:${PORT}/docs${NC}"
echo ""

exec uvicorn main:app --host "$HOST" --port "$PORT" --reload
