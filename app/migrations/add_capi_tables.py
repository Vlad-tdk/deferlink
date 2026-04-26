"""
Migration: Facebook Conversions API tables.

Adds:
  • capi_configs         — per-app Facebook pixel + access token
  • capi_delivery_log    — every attempt (success or failure) to forward
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)

MIGRATION_ID = "add_capi_tables"


def run(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

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
            conn.close()
            return

        logger.info("Applying migration: %s", MIGRATION_ID)

        # ── CAPI configuration per app + platform ─────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS capi_configs (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id             TEXT NOT NULL,
                platform           TEXT NOT NULL DEFAULT 'facebook',  -- reserved for TikTok/Google
                pixel_id           TEXT NOT NULL,
                access_token       TEXT NOT NULL,        -- encrypt at rest in prod
                test_event_code    TEXT,                 -- Facebook "TEST12345" for debugging
                api_version        TEXT NOT NULL DEFAULT 'v21.0',
                enabled            INTEGER NOT NULL DEFAULT 1,
                description        TEXT DEFAULT '',
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (app_id, platform, pixel_id),
                CHECK (platform IN ('facebook', 'tiktok', 'google', 'snap'))
            )
        """)

        # ── Delivery log (one row per attempt) ────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS capi_delivery_log (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id             TEXT NOT NULL,
                platform           TEXT NOT NULL DEFAULT 'facebook',
                event_name         TEXT NOT NULL,        -- "Purchase", "Lead", etc.
                event_id           TEXT NOT NULL,        -- dedup key for Facebook
                event_source       TEXT NOT NULL,        -- "sdk" | "skan" | "manual"
                source_ref_id      INTEGER,              -- FK-ish link to user_events / skan_postbacks
                pixel_id           TEXT NOT NULL,

                payload_json       TEXT NOT NULL,        -- full request body
                response_code      INTEGER,              -- HTTP status
                response_body      TEXT,                 -- trimmed response
                attempts           INTEGER NOT NULL DEFAULT 1,
                succeeded          INTEGER NOT NULL DEFAULT 0,  -- 0/1
                last_error         TEXT,

                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_attempt_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                next_retry_at      TIMESTAMP,            -- NULL = no more retries

                CHECK (platform IN ('facebook', 'tiktok', 'google', 'snap')),
                CHECK (event_source IN ('sdk', 'skan', 'manual'))
            )
        """)

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_capi_cfg_app        ON capi_configs(app_id)",
            "CREATE INDEX IF NOT EXISTS idx_capi_cfg_platform   ON capi_configs(platform)",
            "CREATE INDEX IF NOT EXISTS idx_capi_log_app        ON capi_delivery_log(app_id)",
            "CREATE INDEX IF NOT EXISTS idx_capi_log_event_id   ON capi_delivery_log(event_id)",
            "CREATE INDEX IF NOT EXISTS idx_capi_log_source     ON capi_delivery_log(event_source, source_ref_id)",
            "CREATE INDEX IF NOT EXISTS idx_capi_log_retry      ON capi_delivery_log(next_retry_at) WHERE succeeded = 0 AND next_retry_at IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_capi_log_created    ON capi_delivery_log(created_at)",
        ]
        for sql in indexes:
            cur.execute(sql)

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
