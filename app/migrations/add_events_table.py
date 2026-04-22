"""
Migration: add user_events table for AppsFlyer-style event tracking
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)

MIGRATION_ID = "add_events_table"


def run(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Ensure migrations table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_id = ?",
            (MIGRATION_ID,)
        )
        if cursor.fetchone():
            logger.debug("Migration '%s' already applied — skipping", MIGRATION_ID)
            conn.close()
            return

        logger.info("Applying migration: %s", MIGRATION_ID)

        # ── user_events table ─────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        TEXT UNIQUE NOT NULL,     -- UUID, client-generated (dedup key)
                session_id      TEXT,                      -- attribution session_id (nullable for organic)
                app_user_id     TEXT,                      -- developer-supplied user identifier
                promo_id        TEXT,                      -- from resolved attribution
                event_name      TEXT NOT NULL,             -- e.g. "af_purchase", "af_complete_registration"
                revenue         REAL,                      -- monetary value (nullable)
                currency        TEXT DEFAULT 'USD',        -- ISO 4217
                properties      TEXT,                      -- JSON blob of custom properties
                platform        TEXT DEFAULT 'iOS',
                app_version     TEXT,
                sdk_version     TEXT,
                timestamp       TIMESTAMP NOT NULL,        -- client-side event time (ISO 8601)
                received_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address      TEXT,
                FOREIGN KEY (session_id) REFERENCES deeplink_sessions(session_id)
            )
        """)

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_events_event_name  ON user_events(event_name)",
            "CREATE INDEX IF NOT EXISTS idx_events_session_id  ON user_events(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_app_user_id ON user_events(app_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_promo_id    ON user_events(promo_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON user_events(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_events_revenue     ON user_events(revenue) WHERE revenue IS NOT NULL",
        ]
        for sql in indexes:
            cursor.execute(sql)

        cursor.execute(
            "INSERT INTO schema_migrations (migration_id) VALUES (?)",
            (MIGRATION_ID,)
        )
        conn.commit()
        logger.info("Migration '%s' applied successfully", MIGRATION_ID)

    except Exception as exc:
        conn.rollback()
        logger.error("Migration '%s' failed: %s", MIGRATION_ID, exc)
        raise
    finally:
        conn.close()
