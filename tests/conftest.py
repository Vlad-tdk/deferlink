"""
Shared pytest fixtures.

Tests touching SQLite use an in-memory connection so they don't pollute
the real `data/deferlink.db` and run in parallel safely.
"""

from __future__ import annotations

import sqlite3

import pytest


# ── Mini SQL schema mirroring the real CAPI tables ────────────────────────────
# We keep this minimal — only columns the service actually reads/writes.

_CAPI_CONFIGS_DDL = """
CREATE TABLE capi_configs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id          TEXT NOT NULL,
    platform        TEXT NOT NULL,
    pixel_id        TEXT NOT NULL,
    access_token    TEXT NOT NULL,
    test_event_code TEXT,
    api_version     TEXT NOT NULL DEFAULT 'v21.0',
    enabled         INTEGER NOT NULL DEFAULT 1,
    description     TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(app_id, platform, pixel_id)
);
"""

_CAPI_LOG_DDL = """
CREATE TABLE capi_delivery_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id          TEXT NOT NULL,
    platform        TEXT NOT NULL,
    event_name      TEXT NOT NULL,
    event_id        TEXT NOT NULL,
    event_source    TEXT NOT NULL,
    source_ref_id   INTEGER,
    pixel_id        TEXT,
    payload_json    TEXT,
    response_code   INTEGER,
    response_body   TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    succeeded       INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_attempt_at TIMESTAMP,
    next_retry_at   TIMESTAMP
);
"""


@pytest.fixture
def conn() -> sqlite3.Connection:
    """In-memory SQLite connection with the CAPI tables created."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_CAPI_CONFIGS_DDL + _CAPI_LOG_DDL)
    yield c
    c.close()


@pytest.fixture
def capi_config_row(conn):
    """Insert a usable Facebook CAPI config and return its app_id."""
    conn.execute(
        """
        INSERT INTO capi_configs (
            app_id, platform, pixel_id, access_token,
            test_event_code, api_version, enabled
        ) VALUES (?,?,?,?,?,?,?)
        """,
        ("com.test.app", "facebook", "PIXEL123", "TOKEN_abc", None, "v21.0", 1),
    )
    conn.commit()
    return "com.test.app"
