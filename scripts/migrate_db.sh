#!/usr/bin/env bash

# 统一数据库迁移入口：本地和 ECS 都只使用 Alembic。
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT/backend"

if [[ -n "${SQLITE_DATABASE_PATH:-}" ]]; then
  export SQLITE_DATABASE_PATH
fi

if [[ -x "./.venv/bin/alembic" ]]; then
  exec ./.venv/bin/alembic upgrade head
fi

if command -v alembic >/dev/null 2>&1; then
  exec alembic upgrade head
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 -m alembic upgrade head
fi

echo "找不到 Alembic，请先安装 backend/requirements.txt。" >&2
exit 1
