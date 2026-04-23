"""
Migration: add cloaking_ip_rules, cloaking_ua_rules, cloaking_decisions_log tables.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)

MIGRATION_ID = "add_cloaking_tables"


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
            (MIGRATION_ID,)
        )
        if cur.fetchone():
            logger.debug("Migration '%s' already applied — skipping", MIGRATION_ID)
            conn.close()
            return

        logger.info("Applying migration: %s", MIGRATION_ID)

        # ── Custom IP rules ───────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cloaking_ip_rules (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                cidr         TEXT,           -- e.g. "31.13.24.0/21"
                ip_exact     TEXT,           -- e.g. "1.2.3.4"
                asn          INTEGER,        -- e.g. 32934
                visitor_type TEXT NOT NULL,  -- "bot" | "ad_review" | "suspicious"
                confidence   REAL NOT NULL DEFAULT 0.9,
                description  TEXT NOT NULL DEFAULT '',
                enabled      INTEGER NOT NULL DEFAULT 1,  -- BOOLEAN
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- exactly one of cidr / ip_exact / asn must be set
                CHECK (
                    (cidr IS NOT NULL) + (ip_exact IS NOT NULL) + (asn IS NOT NULL) = 1
                ),
                CHECK (confidence BETWEEN 0.0 AND 1.0),
                CHECK (visitor_type IN ('bot', 'ad_review', 'suspicious', 'real_user'))
            )
        """)

        # ── Custom UA rules ───────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cloaking_ua_rules (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern      TEXT NOT NULL,  -- case-insensitive regex
                visitor_type TEXT NOT NULL,
                confidence   REAL NOT NULL DEFAULT 0.9,
                description  TEXT NOT NULL DEFAULT '',
                enabled      INTEGER NOT NULL DEFAULT 1,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (confidence BETWEEN 0.0 AND 1.0),
                CHECK (visitor_type IN ('bot', 'ad_review', 'suspicious', 'real_user'))
            )
        """)

        # ── Decision audit log ────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cloaking_decisions_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ip           TEXT,
                user_agent   TEXT,
                visitor_type TEXT NOT NULL,
                action       TEXT NOT NULL,
                confidence   REAL,
                signals      TEXT,           -- JSON array of DetectionSignal dicts
                path         TEXT,           -- requested URL path
                timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_ip_rules_cidr     ON cloaking_ip_rules(cidr)",
            "CREATE INDEX IF NOT EXISTS idx_ip_rules_ip_exact ON cloaking_ip_rules(ip_exact)",
            "CREATE INDEX IF NOT EXISTS idx_ip_rules_asn      ON cloaking_ip_rules(asn)",
            "CREATE INDEX IF NOT EXISTS idx_ua_rules_pattern  ON cloaking_ua_rules(pattern)",
            "CREATE INDEX IF NOT EXISTS idx_clog_ip           ON cloaking_decisions_log(ip)",
            "CREATE INDEX IF NOT EXISTS idx_clog_visitor_type ON cloaking_decisions_log(visitor_type)",
            "CREATE INDEX IF NOT EXISTS idx_clog_timestamp    ON cloaking_decisions_log(timestamp)",
        ]
        for sql in indexes:
            cur.execute(sql)

        cur.execute(
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
