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
FETCH_RETRIES="${DEPLOY_FETCH_RETRIES:-5}"
FETCH_INTERVAL="${DEPLOY_FETCH_INTERVAL:-5}"
GIT_CONNECT_TIMEOUT="${DEPLOY_GIT_CONNECT_TIMEOUT:-15}"
GIT_LOW_SPEED_LIMIT="${DEPLOY_GIT_LOW_SPEED_LIMIT:-1000}"
GIT_LOW_SPEED_TIME="${DEPLOY_GIT_LOW_SPEED_TIME:-20}"
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

retry() {
  local label="$1"
  shift
  local attempt
  for ((attempt = 1; attempt <= FETCH_RETRIES; attempt++)); do
    if "$@"; then
      return 0
    fi
    if (( attempt < FETCH_RETRIES )); then
      warn "$label失败（${attempt}/${FETCH_RETRIES}），${FETCH_INTERVAL} 秒后重试……"
      sleep "$FETCH_INTERVAL"
    fi
  done
  return 1
}

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
GIT_HTTP_OPTIONS=(
  -c "http.connectTimeout=$GIT_CONNECT_TIMEOUT"
  -c "http.lowSpeedLimit=$GIT_LOW_SPEED_LIMIT"
  -c "http.lowSpeedTime=$GIT_LOW_SPEED_TIME"
)
retry "Git 获取远端代码" git "${GIT_HTTP_OPTIONS[@]}" -c http.version=HTTP/1.1 fetch --prune origin "$BRANCH" \
  || retry "Git 获取远端代码（兼容 HTTP/2）" git "${GIT_HTTP_OPTIONS[@]}" -c http.version=HTTP/2 fetch --prune origin "$BRANCH" \
  || die "无法获取 origin/$BRANCH。请检查 ECS 到 GitHub 的网络，或稍后重试。"
git checkout -B "$BRANCH" "origin/$BRANCH" >/dev/null
DEPLOY_COMMIT="$(git rev-parse --short HEAD)"
ok "代码版本：$DEPLOY_COMMIT"

log "校验 Compose 配置……"
docker compose -f "$COMPOSE_FILE" config -q
ok "Compose 配置有效；.env 未被覆盖。"

log "构建并启动前后端服务……"
docker compose -f "$COMPOSE_FILE" build

log "执行数据库迁移……"
docker compose -f "$COMPOSE_FILE" run --rm app bash /app/scripts/migrate_db.sh
ok "数据库迁移完成。"

docker compose -f "$COMPOSE_FILE" up -d --no-build

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log "等待后端健康检查：$HEALTH_URL"
for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt++)); do
  if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    ok "后端已启动并通过数据库、存储健康检查。"
    break
  fi
  if (( attempt == HEALTH_RETRIES )); then
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    warn "健康检查未通过，输出最近日志："
    docker compose -f "$COMPOSE_FILE" logs --tail=80 >&2 || true
    die "部署未通过健康检查。"
  fi
  sleep "$HEALTH_INTERVAL"
done

check_http() {
  local name="$1"
  local url="$2"
  local output="$TMP_DIR/${name}.body"
  local status
  status="$(curl -L -sS -o "$output" -w '%{http_code}' --max-time 10 "$url" || true)"
  [[ "$status" == "200" ]] || die "$name 检查失败：HTTP $status ($url)"
  ok "$name：HTTP 200"
}

check_status() {
  local name="$1"
  local expected="$2"
  local url="$3"
  local status
  status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$url" || true)"
  [[ "$status" == "$expected" ]] || die "$name 检查失败：期望 HTTP $expected，实际 HTTP $status ($url)"
  ok "$name：HTTP $expected"
}

BASE_URL="${DEPLOY_BASE_URL:-http://127.0.0.1:8787}"
check_http "home" "$BASE_URL/"
check_http "admin-login" "$BASE_URL/admin-login.html"
check_http "admin" "$BASE_URL/admin.html"
check_http "openapi" "$BASE_URL/openapi.json"
check_status "user-auth-route" "401" "$BASE_URL/api/auth/me"
check_status "user-state-route" "401" "$BASE_URL/api/state"

ADMIN_JS_URL="$(sed -nE 's#.*<script[^>]+src="([^"]*admin/admin\.js[^"]*)".*#\1#p' "$TMP_DIR/admin.body" | head -n 1)"
LOGIN_JS_URL="$(sed -nE 's#.*<script[^>]+src="([^"]*admin/login\.js[^"]*)".*#\1#p' "$TMP_DIR/admin-login.body" | head -n 1)"
[[ -n "$ADMIN_JS_URL" ]] || die "admin.html 没有引用 admin.js。"
[[ -n "$LOGIN_JS_URL" ]] || die "admin-login.html 没有引用 login.js。"
check_http "admin-js" "$BASE_URL/${ADMIN_JS_URL#/}"
check_http "login-js" "$BASE_URL/${LOGIN_JS_URL#/}"

USER_API_URL="$(sed -nE 's#.*<script[^>]+src="([^"]*js/core/api\.js[^"]*)".*#\1#p' "$TMP_DIR/home.body" | head -n 1)"
[[ -n "$USER_API_URL" ]] || die "首页没有引用用户端 api.js。"
check_http "user-api-js" "$BASE_URL/${USER_API_URL#/}"
if grep -Eq "(['\"]|:)http://127\.0\.0\.1:8787(['\"]|$)|(['\"]|:)http://localhost:8787(['\"]|$)" "$TMP_DIR/user-api-js.body"; then
  die "用户端 api.js 仍包含固定本机 API 地址，公网用户会请求自己的电脑。"
fi
ok "用户端 API 使用同源地址。"

ok "部署验收完成，代码版本：$DEPLOY_COMMIT"
docker compose -f "$COMPOSE_FILE" ps
