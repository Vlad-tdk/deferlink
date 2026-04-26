from __future__ import annotations

import sqlite3

from app.core.event_tracker import insert_event
from app.database import db_manager


def _init_event_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE deeplink_sessions (
            session_id TEXT PRIMARY KEY
        );

        CREATE TABLE user_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id        TEXT UNIQUE NOT NULL,
            session_id      TEXT,
            app_user_id     TEXT,
            promo_id        TEXT,
            event_name      TEXT NOT NULL,
            revenue         REAL,
            currency        TEXT DEFAULT 'USD',
            properties      TEXT,
            platform        TEXT DEFAULT 'iOS',
            app_version     TEXT,
            sdk_version     TEXT,
            timestamp       TIMESTAMP NOT NULL,
            received_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address      TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_insert_event_reports_duplicate(tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    _init_event_db(str(db_path))
    monkeypatch.setattr(db_manager, "db_path", str(db_path))

    assert insert_event("evt-1", "af_purchase", "2026-04-26T10:00:00Z") == "inserted"
    assert insert_event("evt-1", "af_purchase", "2026-04-26T10:00:00Z") == "duplicate"

