#!/usr/bin/env bash

# ECS 部署入口：同步 origin/main，检查环境，构建并启动 Docker 服务。
# 不覆盖 .env，不删除数据库、生成图片或 Docker volume。
# 自动清理中断部署留下的未跟踪代码文件，并防止重复部署进程。
#
# 用法：
#   bash scripts/deploy_main.sh
#   bash scripts/deploy_main.sh --force

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${DEPLOY_HEALTH_URL:-http://127.0.0.1:8787/api/admin/health}"
HEALTH_RETRIES="${DEPLOY_HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${DEPLOY_HEALTH_INTERVAL:-2}"
COMPOSE_FILE="${DEPLOY_COMPOSE_FILE:-docker-compose.prod.yml}"
FORCE=false
LOCK_FILE="${DEPLOY_LOCK_FILE:-/tmp/hometown-letters-deploy.lock}"
PRESERVE_PATHS=(
  -e .env
  -e backend/data/
  -e backend/generated_images/
  -e backend/logs/
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { printf '%b\n' "${CYAN}[deploy]${NC} $*"; }
ok() { printf '%b\n' "${GREEN}[ ok ]${NC} $*"; }
warn() { printf '%b\n' "${YELLOW}[warn]${NC} $*"; }
die() { printf '%b\n' "${RED}[fail]${NC} $*" >&2; exit 1; }

usage() { sed -n '1,18p' "$0"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "不支持的参数：$1。使用 --help 查看用法。" ;;
  esac
done

cd "$PROJECT_ROOT"
command -v git >/dev/null 2>&1 || die "找不到 git。"
command -v docker >/dev/null 2>&1 || die "找不到 docker。"
command -v curl >/dev/null 2>&1 || die "找不到 curl。"
command -v flock >/dev/null 2>&1 || die "找不到 flock（Ubuntu 可通过 util-linux 安装）。"
docker compose version >/dev/null 2>&1 || die "找不到 Docker Compose。"
[[ -f "$COMPOSE_FILE" ]] || die "找不到生产 Compose 配置：$COMPOSE_FILE"
[[ -f .env ]] || die "找不到 .env；脚本不会自动生成或覆盖生产配置。"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "当前目录不是 Git 仓库：$PROJECT_ROOT"

exec 9>"$LOCK_FILE"
flock -n 9 || die "已有部署正在执行：$LOCK_FILE。请等待它完成后再重试。"

log "部署目录：$PROJECT_ROOT"
log "目标分支：origin/$BRANCH"
log "Compose 配置：$COMPOSE_FILE"

# 只阻止已跟踪文件改动；backend/data、generated_images 等运行数据可以保留。
if ! git diff --quiet || ! git diff --cached --quiet; then
  [[ "$FORCE" == true ]] || die "Git 工作区存在本地改动。请先处理，或明确使用 --force。"
  warn "--force：丢弃已跟踪文件的本地改动；.env 和忽略文件不会被覆盖。"
  git reset --hard HEAD >/dev/null
fi

# 中断部署可能留下 origin/main 中已有的未跟踪代码文件，导致 checkout 被拒绝。
# 只清理代码残留，明确保留 .env、数据库、生成图片和日志。
if [[ "$FORCE" == true ]]; then
  log "清理中断部署留下的未跟踪代码文件（保留运行数据）……"
  git clean -fd "${PRESERVE_PATHS[@]}"
fi

log "获取远端 main 最新代码……"
git fetch --prune origin "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH" >/dev/null
ok "代码版本：$(git rev-parse --short HEAD)"

log "校验 Compose 配置……"
docker compose -f "$COMPOSE_FILE" config -q
ok "Compose 配置有效；.env 未被覆盖。"

log "构建并启动前后端服务……"
docker compose -f "$COMPOSE_FILE" build

log "执行数据库迁移……"
docker compose -f "$COMPOSE_FILE" run --rm app bash /app/scripts/migrate_db.sh
ok "数据库迁移完成。"

docker compose -f "$COMPOSE_FILE" up -d --no-build

log "等待健康检查：$HEALTH_URL"
for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt++)); do
  if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    ok "服务已启动并通过健康检查。"
    docker compose -f "$COMPOSE_FILE" ps
    exit 0
  fi
  sleep "$HEALTH_INTERVAL"
done

docker compose -f "$COMPOSE_FILE" ps >&2 || true
warn "健康检查未通过，输出最近日志："
docker compose -f "$COMPOSE_FILE" logs --tail=80 >&2 || true
die "部署未通过健康检查。"
