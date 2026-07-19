#!/usr/bin/env bash

# 将 frontend/assets/ 上传到 OSS。
#
# 安全约定：
# - 本脚本不保存、不打印 AccessKey。
# - 凭证只从项目根目录 .env 由 backend/config.py 读取。
# - .env 必须被 .gitignore 忽略，禁止提交到 Git。
#
# 用法：
#   ./docs/oss-frontend-assets/upload_frontend_assets_to_oss.sh --check
#   ./docs/oss-frontend-assets/upload_frontend_assets_to_oss.sh --dry-run
#   ./docs/oss-frontend-assets/upload_frontend_assets_to_oss.sh

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/.env}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

fail() {
  printf '错误：%s\n' "$1" >&2
  exit 1
}

usage() {
  sed -n '1,22p' "$0"
}

[[ -f "$ENV_FILE" ]] || fail "找不到 .env：$ENV_FILE。请先复制 .env.example 并填写 OSS 配置。"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "找不到 Python：$PYTHON_BIN"
[[ -f "$PROJECT_ROOT/backend/scripts/upload_frontend_assets.py" ]] || fail "找不到上传程序。"
[[ -d "$PROJECT_ROOT/frontend/assets" ]] || fail "找不到前端素材目录：$PROJECT_ROOT/frontend/assets"

if ! git -C "$PROJECT_ROOT" check-ignore -q "$ENV_FILE"; then
  fail ".env 没有被 Git 忽略。请先修复 .gitignore，避免凭证泄露。"
fi

case "${1:-}" in
  --help|-h)
    usage
    exit 0
    ;;
  --dry-run)
    printf '仅检查素材，不上传：%s\n' "$PROJECT_ROOT/frontend/assets"
    find "$PROJECT_ROOT/frontend/assets" -type f -print | sort
    exit 0
    ;;
  --check)
    cd "$PROJECT_ROOT"
    "$PYTHON_BIN" - <<'PY'
import sys
sys.path.insert(0, "backend")
from config import settings
from services.image_storage import validate_storage_config

if settings.storage_backend.lower() != "oss":
    raise SystemExit("STORAGE_BACKEND 当前不是 oss")
validate_storage_config()
print("OSS 配置检查通过。凭证未打印。")
print(f"素材前缀：{settings.oss_asset_prefix.strip('/') or 'assets'}")
PY
    exit 0
    ;;
  "")
    ;;
  *)
    fail "不支持的参数：$1。使用 --help 查看用法。"
    ;;
esac

cd "$PROJECT_ROOT"
printf '开始上传前端素材到 OSS；不会输出 AccessKey。\n'
exec "$PYTHON_BIN" backend/scripts/upload_frontend_assets.py
