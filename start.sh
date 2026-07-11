#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# 故乡来信 — 一键启动脚本
# ═══════════════════════════════════════════════════════════════
# 自动加载 .env 环境变量，激活虚拟环境，启动后端服务
#
# 使用方法：
#   1. 首次使用：  chmod +x start.sh
#   2. 配置环境：  cp .env.example .env  然后编辑 .env
#   3. 启动服务：  ./start.sh
# ═══════════════════════════════════════════════════════════════

set -e

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
ENV_FILE="$PROJECT_DIR/.env"

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
    echo -e "${YELLOW}[!] 未找到 .env 文件，使用默认配置${NC}"
    echo -e "${YELLOW}    建议: cp .env.example .env 并填入 API Key${NC}"
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

# ── 5. 检测 Python 虚拟环境 ──
if [ -d "venv" ]; then
    echo -e "${GREEN}[✓] 使用 venv 虚拟环境${NC}"
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo -e "${GREEN}[✓] 使用 .venv 虚拟环境${NC}"
    source .venv/bin/activate
else
    echo -e "${YELLOW}[!] 未检测到虚拟环境，使用系统 Python${NC}"
fi

# ── 6. 安装依赖 ──
echo -e "${GREEN}[✓] 检查依赖...${NC}"
pip install -q -r requirements.txt 2>/dev/null || {
    echo -e "${RED}[✗] 依赖安装失败，请手动执行: pip install -r requirements.txt${NC}"
    exit 1
}

# ── 7. 启动 ──
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8787}"
echo -e "${GREEN}[✓] 启动服务: http://${HOST}:${PORT}${NC}"
echo -e "${GREEN}[✓] API 文档: http://${HOST}:${PORT}/docs${NC}"
echo ""

exec uvicorn main:app --host "$HOST" --port "$PORT" --reload
