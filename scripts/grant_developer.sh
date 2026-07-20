#!/usr/bin/env bash

# 将一个已存在的用户设置为开发者账号。
# 用法：bash scripts/grant_developer.sh <username>
# 只修改 users.is_developer；不会创建用户、修改密码或修改其他字段。

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${DEPLOY_COMPOSE_FILE:-docker-compose.prod.yml}"
SERVICE="${DEPLOY_SERVICE:-app}"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { printf '%b\n' "${CYAN}[developer]${NC} $*"; }
ok() { printf '%b\n' "${GREEN}[ ok ]${NC} $*"; }
die() { printf '%b\n' "${RED}[fail]${NC} $*" >&2; exit 1; }

if [[ $# -ne 1 || -z "$1" || "$1" == -* ]]; then
  printf '用法：bash scripts/grant_developer.sh <已存在的用户名>\n' >&2
  exit 2
fi

USERNAME="$1"
cd "$PROJECT_ROOT"

command -v docker >/dev/null 2>&1 || die "找不到 docker。"
docker compose version >/dev/null 2>&1 || die "找不到 Docker Compose。"
[[ -f "$COMPOSE_FILE" ]] || die "找不到 Compose 配置：$COMPOSE_FILE"

log "检查用户：$USERNAME"
docker compose -f "$COMPOSE_FILE" exec -T \
  -e PYTHONPATH=/app/backend \
  -e TARGET_USERNAME="$USERNAME" \
  "$SERVICE" python -c '
import asyncio
import os
import sys

from sqlalchemy import select, update

from db.database import async_session
from db.models import User


async def main():
    username = os.environ["TARGET_USERNAME"]
    async with async_session() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            print(f"用户不存在：{username}", file=sys.stderr)
            return 1
        await db.execute(update(User).where(User.id == user.id).values(is_developer=True))
        await db.commit()
        print(f"已设置开发者：{user.username} (id={user.id})")
    return 0


raise SystemExit(asyncio.run(main()))
'

ok "开发者账号设置完成。"
