"""
Migration: Add DeviceCheck and IAB-escape fields
Миграция: добавление полей для DeviceCheck и Safari escape

Новые колонки в deeplink_sessions:
  - source_context         TEXT    — откуда пришёл пользователь ('safari', 'facebook_iab', ...)
  - device_check_token_hash TEXT   — SHA-256 хэш DeviceCheck токена (не сырой токен!)
  - match_method           TEXT    — метод матчинга ('clipboard', 'safari_cookie', 'device_check', 'fingerprint')
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

MIGRATION_ID = "add_devicecheck_fields_001"

SQL_ADD_COLUMNS = [
    "ALTER TABLE deeplink_sessions ADD COLUMN source_context TEXT",
    "ALTER TABLE deeplink_sessions ADD COLUMN device_check_token_hash TEXT",
    "ALTER TABLE deeplink_sessions ADD COLUMN match_method TEXT",
]

SQL_ADD_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_dc_token_hash
    ON deeplink_sessions (device_check_token_hash)
    WHERE device_check_token_hash IS NOT NULL
"""

SQL_CREATE_MIGRATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        migration_id TEXT PRIMARY KEY,
        applied_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""


def _already_applied(conn: sqlite3.Connection) -> bool:
    conn.execute(SQL_CREATE_MIGRATIONS_TABLE)
    conn.commit()
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE migration_id = ?", (MIGRATION_ID,)
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def run(db_path: str) -> bool:
    """
    Запустить миграцию.

    Returns:
        True  — миграция применена
        False — уже была применена ранее
    """
    conn = sqlite3.connect(db_path)
    try:
        if _already_applied(conn):
            logger.debug("Migration %s already applied, skipping", MIGRATION_ID)
            return False

        logger.info("Applying migration: %s", MIGRATION_ID)

        for sql in SQL_ADD_COLUMNS:
            # Извлекаем имя колонки из SQL для проверки существования
            col_name = sql.split("ADD COLUMN")[1].strip().split()[0]
            if _column_exists(conn, "deeplink_sessions", col_name):
                logger.debug("Column %s already exists, skipping ADD COLUMN", col_name)
                continue
            try:
                conn.execute(sql)
                logger.info("Added column: %s", col_name)
            except sqlite3.OperationalError as e:
                logger.warning("Could not add column %s: %s", col_name, e)

        conn.execute(SQL_ADD_INDEX)
        conn.execute(
            "INSERT INTO schema_migrations (migration_id) VALUES (?)",
            (MIGRATION_ID,)
        )
        conn.commit()

        logger.info("Migration %s applied successfully", MIGRATION_ID)
        return True

    except Exception as e:
        conn.rollback()
        logger.error("Migration %s FAILED: %s", MIGRATION_ID, e)
        raise

    finally:
        conn.close()
