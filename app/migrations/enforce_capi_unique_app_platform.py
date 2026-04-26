"""
Migration: enforce single CAPI config per (app_id, platform).

Older versions allowed multiple rows distinguished only by pixel_id.
Runtime now treats config as unique by (app_id, platform), so this
migration deduplicates historical rows and adds a DB-level unique index.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

MIGRATION_ID = "enforce_capi_unique_app_platform"


def run(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_id = ?",
            (MIGRATION_ID,),
        )
        if cur.fetchone():
            logger.debug("Migration '%s' already applied — skipping", MIGRATION_ID)
            return

        cur.execute("""
            SELECT app_id, platform
              FROM capi_configs
             GROUP BY app_id, platform
            HAVING COUNT(*) > 1
        """)
        duplicate_keys = cur.fetchall()

        for app_id, platform in duplicate_keys:
            cur.execute(
                """
                SELECT id
                  FROM capi_configs
                 WHERE app_id = ? AND platform = ?
                 ORDER BY enabled DESC, updated_at DESC, id DESC
                """,
                (app_id, platform),
            )
            rows = [row[0] for row in cur.fetchall()]
            keep_id, duplicate_ids = rows[0], rows[1:]
            if duplicate_ids:
                placeholders = ",".join("?" for _ in duplicate_ids)
                cur.execute(
                    f"DELETE FROM capi_configs WHERE id IN ({placeholders})",
                    duplicate_ids,
                )
                logger.warning(
                    "Removed duplicate CAPI configs for %s/%s, kept id=%s removed=%s",
                    app_id,
                    platform,
                    keep_id,
                    duplicate_ids,
                )

        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_capi_cfg_unique_app_platform
                ON capi_configs(app_id, platform)
        """)

        cur.execute(
            "INSERT INTO schema_migrations (migration_id) VALUES (?)",
            (MIGRATION_ID,),
        )
        conn.commit()
        logger.info("Migration '%s' applied successfully", MIGRATION_ID)

    except Exception as exc:
        conn.rollback()
        logger.error("Migration '%s' failed: %s", MIGRATION_ID, exc)
        raise
    finally:
        conn.close()
