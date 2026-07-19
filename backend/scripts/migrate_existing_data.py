"""一次性把当前旧 SQLite 和本地图片迁移到当前结构与私有 OSS。

执行前先做 dry-run。真正迁移必须显式传入 --execute，并要求 STORAGE_BACKEND=oss。
脚本会创建数据库备份，先在临时数据库完成结构迁移和数据复制，所有图片上传成功后
再替换正式数据库；任何失败都不会修改原数据库。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from services import image_storage  # noqa: E402

TABLES = (
    "users",
    "hometowns",
    "profiles",
    "landmarks",
    "letters",
    "memories",
    "past_self_profiles",
    "letter_summaries",
    "letter_memories",
    "postcards",
    "mails",
    "letter_likes",
)


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    cursor = connection.execute(f'SELECT * FROM "{table}"')
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _old_postcards(connection: sqlite3.Connection) -> list[dict]:
    rows = _rows(connection, "postcards")
    required = {"id", "user_id", "image_path"}
    if not required.issubset(_columns(connection, "postcards")):
        raise RuntimeError("当前数据库不是待迁移的旧 postcards 结构")
    return rows


def _source_path(source_dir: Path, image_path: str) -> Path:
    """解析旧本地图片名；旧记录保存无扩展名的 image id。"""
    name = Path(image_path).name
    direct = source_dir / name
    if direct.is_file():
        return direct
    if not Path(name).suffix:
        jpg = source_dir / f"{name}.jpg"
        if jpg.is_file():
            return jpg
    raise FileNotFoundError(f"旧本地图片不存在: {direct}")


def _build_temp_database(path: Path) -> None:
    if path.exists():
        path.unlink()
    database_url = f"sqlite:///{path}"
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        command.upgrade(config, "head")
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


def _insert_rows(old: sqlite3.Connection, new: sqlite3.Connection) -> dict[int, int]:
    user_postcard_counts = {
        row["user_id"]: row["count"]
        for row in old.execute("SELECT user_id, COUNT(*) AS count FROM postcards GROUP BY user_id")
    }
    for table in TABLES:
        old_columns = _columns(old, table)
        new_columns = _columns(new, table)
        common = [column for column in old_columns & new_columns if column not in {"image_path", "used_fallback"}]
        if table == "users":
            common += ["postcard_limit", "postcard_count"]
        if table == "postcards":
            common += ["image_thumb_key", "image_card_key", "image_original_key"]

        for row in _rows(old, table):
            values = {column: row[column] for column in common if column in row}
            if table == "users":
                values["postcard_limit"] = 5
                values["postcard_count"] = user_postcard_counts.get(row["id"], 0)
            if table == "postcards":
                values.update({"image_thumb_key": "", "image_card_key": "", "image_original_key": ""})
            columns = list(values)
            placeholders = ", ".join(f":{column}" for column in columns)
            column_sql = ", ".join(f'"{column}"' for column in columns)
            new.execute(
                f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
                values,
            )
    new.commit()
    return user_postcard_counts


async def _upload_images(
    old_rows: list[dict],
    temp: sqlite3.Connection,
    source_dir: Path,
    dry_run: bool,
) -> tuple[int, int, list[str]]:
    uploaded: list[str] = []
    migrated = 0
    skipped = 0
    for row in old_rows:
        image_path = (row.get("image_path") or "").strip()
        if not image_path:
            skipped += 1
            continue
        try:
            source = _source_path(source_dir, image_path)
        except FileNotFoundError as error:
            raise FileNotFoundError(f"明信片 {row['id']} 的本地图片不存在") from error
        image_id = Path(image_path).stem
        if dry_run:
            migrated += 1
            continue
        keys = await image_storage.save_image_variants(
            int(row["user_id"]), image_id, source.read_bytes()
        )
        temp.execute(
            "UPDATE postcards SET image_thumb_key=?, image_card_key=?, image_original_key=? WHERE id=?",
            (keys["thumb"], keys["card"], keys["original"], row["id"]),
        )
        uploaded.extend(keys.values())
        migrated += 1
    if not dry_run:
        temp.commit()
    return migrated, skipped, uploaded


async def migrate(db_path: Path, execute: bool) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    with sqlite3.connect(db_path) as old:
        old_rows = _old_postcards(old)
        old_counts = {table: len(_rows(old, table)) for table in TABLES}
        has_new_schema = "image_thumb_key" in _columns(old, "postcards")
        if has_new_schema:
            raise RuntimeError("数据库已经是当前图片结构，不重复执行一次性迁移")

    print(f"数据库: {db_path}")
    print(f"明信片: {len(old_rows)} 条，已有本地图片: {sum(bool(row.get('image_path')) for row in old_rows)} 条")
    print(f"旧表数据: {old_counts}")
    if not execute:
        migrated, skipped, _ = await _upload_images(
            old_rows,
            sqlite3.connect(":memory:"),
            image_storage.IMAGES_DIR,
            dry_run=True,
        )
        print(f"dry-run 完成: {migrated} 条图片可迁移，{skipped} 条没有本地图片。")
        print("未上传 OSS，未修改数据库。")
        return

    image_storage.validate_storage_config()
    backup = db_path.with_name(
        f"{db_path.name}.backup-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    temp_path = db_path.with_name(f"{db_path.name}.migration-tmp")
    shutil.copy2(db_path, backup)
    uploaded: list[str] = []
    try:
        _build_temp_database(temp_path)
        with sqlite3.connect(db_path) as old, sqlite3.connect(temp_path) as temp:
            _insert_rows(old, temp)
            migrated, skipped, uploaded = await _upload_images(
                old_rows, temp, image_storage.IMAGES_DIR, dry_run=False
            )
        os.replace(temp_path, db_path)
        print(f"迁移完成: {migrated} 条图片已上传，{skipped} 条没有本地图片")
        print(f"数据库备份: {backup}")
    except Exception:
        if uploaded:
            await image_storage.delete_image_variants(
                {str(index): key for index, key in enumerate(uploaded)}
            )
        temp_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=BACKEND / "data" / "hometown.db")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute and image_storage.settings.storage_backend.lower() != "oss":
        raise SystemExit("执行迁移前必须设置 STORAGE_BACKEND=oss")
    asyncio.run(migrate(args.db, args.execute))


if __name__ == "__main__":
    main()
