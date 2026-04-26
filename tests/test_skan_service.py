from __future__ import annotations

import json
import sqlite3

from app.core.skadnetwork.service import SKANService


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE skan_postbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            ad_network_id TEXT NOT NULL,
            source_identifier TEXT,
            campaign_id INTEGER,
            transaction_id TEXT NOT NULL UNIQUE,
            app_id TEXT,
            source_app_id TEXT,
            source_domain TEXT,
            redownload INTEGER DEFAULT 0,
            fidelity_type INTEGER,
            conversion_value INTEGER,
            coarse_conversion_value TEXT,
            postback_sequence_index INTEGER NOT NULL,
            did_win INTEGER,
            attribution_signature TEXT,
            signature_verified INTEGER DEFAULT 0,
            raw_json TEXT NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            capi_forwarded INTEGER DEFAULT 0,
            capi_forwarded_at TIMESTAMP,
            capi_last_error TEXT
        );

        CREATE TABLE skan_cv_distribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            app_id TEXT NOT NULL,
            source_identifier TEXT,
            campaign_id INTEGER,
            conversion_value INTEGER,
            postback_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (date, app_id, source_identifier, campaign_id, conversion_value)
        );

        CREATE TABLE skan_campaign_decoders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_identifier TEXT,
            campaign_id INTEGER,
            app_id TEXT NOT NULL,
            decoder_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE skan_cv_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id TEXT NOT NULL UNIQUE,
            schema_version INTEGER NOT NULL DEFAULT 1,
            schema_name TEXT NOT NULL DEFAULT 'rev3_eng2_flag1',
            revenue_buckets_json TEXT NOT NULL,
            bounce_max_seconds INTEGER NOT NULL DEFAULT 30,
            active_min_sessions INTEGER NOT NULL DEFAULT 2,
            deep_min_sessions INTEGER NOT NULL DEFAULT 5,
            deep_min_core_actions INTEGER NOT NULL DEFAULT 1,
            power_requires_retention INTEGER NOT NULL DEFAULT 1,
            conversion_window_hours INTEGER NOT NULL DEFAULT 48,
            cache_ttl_seconds INTEGER NOT NULL DEFAULT 86400
        );
        """
    )
    return conn


def test_duplicate_postback_is_not_redecoded_or_counted_twice():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO skan_campaign_decoders (source_identifier, campaign_id, app_id, decoder_json, enabled)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("1234", None, "com.test.app", json.dumps([
            {"cv_min": 0, "cv_max": 63, "capi_event": "Purchase", "forward": True, "currency": "USD"}
        ]), 1),
    )
    conn.commit()

    service = SKANService(verify_signatures=False)
    service.load_rules(conn)

    payload = {
        "version": "4.0",
        "ad-network-id": "com.example.adnetwork",
        "transaction-id": "tx-001",
        "source-identifier": "1234",
        "app-id": "com.test.app",
        "postback-sequence-index": 0,
        "conversion-value": 10,
    }

    _, row_id_1, instruction_1 = service.ingest_postback(payload, conn)
    _, row_id_2, instruction_2 = service.ingest_postback(payload, conn)

    assert row_id_1 == row_id_2
    assert instruction_1 is not None
    assert instruction_2 is None

    row = conn.execute(
        "SELECT postback_count FROM skan_cv_distribution WHERE app_id = ? AND conversion_value = ?",
        ("com.test.app", 10),
    ).fetchone()
    assert row["postback_count"] == 1

