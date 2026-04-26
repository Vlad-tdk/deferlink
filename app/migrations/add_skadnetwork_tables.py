"""
Migration: SKAdNetwork tables.

Adds:
  • skan_postbacks           — raw postbacks from Apple (PB1/PB2/PB3)
  • skan_cv_configs          — per-app conversion-value encoding config
  • skan_campaign_decoders   — per-campaign mapping CV → CAPI event
  • skan_cv_distribution     — aggregated CV distribution (for analytics)
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)

MIGRATION_ID = "add_skadnetwork_tables"


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

        # ── Raw postbacks from Apple ──────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS skan_postbacks (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                version                   TEXT NOT NULL,          -- "4.0"
                ad_network_id             TEXT NOT NULL,          -- e.g. "example123.skadnetwork"
                source_identifier         TEXT,                   -- 4-digit campaign id (SKAN 4+)
                campaign_id               INTEGER,                -- legacy SKAN 2/3 (0-99)
                transaction_id            TEXT NOT NULL UNIQUE,   -- dedup key
                app_id                    TEXT,                   -- target iTunes id
                source_app_id             TEXT,                   -- publisher iTunes id
                source_domain             TEXT,                   -- web-attribution
                redownload                INTEGER DEFAULT 0,      -- 0/1
                fidelity_type             INTEGER,                -- 0=view, 1=click
                conversion_value          INTEGER,                -- 0-63 (PB1 only)
                coarse_conversion_value   TEXT,                   -- "low" | "medium" | "high"
                postback_sequence_index   INTEGER NOT NULL,       -- 0=PB1 1=PB2 2=PB3
                did_win                   INTEGER,                -- 0/1 (SKAN 4+)
                attribution_signature     TEXT,                   -- raw signature
                signature_verified        INTEGER DEFAULT 0,      -- 0=no, 1=ok, 2=failed
                raw_json                  TEXT NOT NULL,          -- full payload
                received_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- forwarding state
                capi_forwarded            INTEGER DEFAULT 0,      -- 0=pending, 1=done, 2=failed
                capi_forwarded_at         TIMESTAMP,
                capi_last_error           TEXT,

                CHECK (postback_sequence_index IN (0, 1, 2)),
                CHECK (coarse_conversion_value IS NULL
                       OR coarse_conversion_value IN ('low', 'medium', 'high')),
                CHECK (conversion_value IS NULL
                       OR conversion_value BETWEEN 0 AND 63)
            )
        """)

        # ── CV encoding config per app ────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS skan_cv_configs (
                id                         INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id                     TEXT NOT NULL UNIQUE,
                schema_version             INTEGER NOT NULL DEFAULT 1,
                schema_name                TEXT NOT NULL DEFAULT 'rev3_eng2_flag1',

                -- revenue buckets (8 entries, ascending USD thresholds)
                revenue_buckets_json       TEXT NOT NULL,

                -- engagement thresholds
                bounce_max_seconds         INTEGER NOT NULL DEFAULT 30,
                active_min_sessions        INTEGER NOT NULL DEFAULT 2,
                deep_min_sessions          INTEGER NOT NULL DEFAULT 5,
                deep_min_core_actions      INTEGER NOT NULL DEFAULT 1,
                power_requires_retention   INTEGER NOT NULL DEFAULT 1,

                conversion_window_hours    INTEGER NOT NULL DEFAULT 48,
                cache_ttl_seconds          INTEGER NOT NULL DEFAULT 86400,

                created_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Per-campaign decoder: CV → CAPI event ─────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS skan_campaign_decoders (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                source_identifier  TEXT,                 -- 4-digit SKAN 4 campaign id
                campaign_id        INTEGER,              -- legacy SKAN 2/3 campaign id
                app_id             TEXT NOT NULL,

                -- decoder_json stores array of rules:
                --   [{ "cv_min": 0, "cv_max": 7,
                --      "capi_event": "Purchase",
                --      "value_multiplier": 1.0,
                --      "static_value": null,
                --      "currency": "USD",
                --      "forward": true }, ...]
                decoder_json       TEXT NOT NULL,

                description        TEXT NOT NULL DEFAULT '',
                enabled            INTEGER NOT NULL DEFAULT 1,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                CHECK (
                    (source_identifier IS NOT NULL) + (campaign_id IS NOT NULL) >= 1
                )
            )
        """)

        # ── CV distribution stats (aggregated) ────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS skan_cv_distribution (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                date               TEXT NOT NULL,        -- YYYY-MM-DD
                app_id             TEXT NOT NULL,
                source_identifier  TEXT,
                campaign_id        INTEGER,
                conversion_value   INTEGER,
                postback_count     INTEGER NOT NULL DEFAULT 0,
                UNIQUE (date, app_id, source_identifier, campaign_id, conversion_value)
            )
        """)

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_skan_pb_transaction     ON skan_postbacks(transaction_id)",
            "CREATE INDEX IF NOT EXISTS idx_skan_pb_app             ON skan_postbacks(app_id)",
            "CREATE INDEX IF NOT EXISTS idx_skan_pb_source          ON skan_postbacks(source_identifier)",
            "CREATE INDEX IF NOT EXISTS idx_skan_pb_campaign        ON skan_postbacks(campaign_id)",
            "CREATE INDEX IF NOT EXISTS idx_skan_pb_sequence        ON skan_postbacks(postback_sequence_index)",
            "CREATE INDEX IF NOT EXISTS idx_skan_pb_received        ON skan_postbacks(received_at)",
            "CREATE INDEX IF NOT EXISTS idx_skan_pb_capi_pending    ON skan_postbacks(capi_forwarded) WHERE capi_forwarded = 0",
            "CREATE INDEX IF NOT EXISTS idx_skan_dec_source         ON skan_campaign_decoders(source_identifier)",
            "CREATE INDEX IF NOT EXISTS idx_skan_dec_campaign       ON skan_campaign_decoders(campaign_id)",
            "CREATE INDEX IF NOT EXISTS idx_skan_dec_app            ON skan_campaign_decoders(app_id)",
            "CREATE INDEX IF NOT EXISTS idx_skan_dist_date          ON skan_cv_distribution(date)",
            "CREATE INDEX IF NOT EXISTS idx_skan_dist_app           ON skan_cv_distribution(app_id)",
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
