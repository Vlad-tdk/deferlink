"""
Tests for the CAPI service + Facebook client.

Network calls are mocked at the httpx layer so tests stay offline.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
import httpx

from fastapi import HTTPException

from app.api import capi_admin
from app.core.capi.facebook import FacebookCAPIClient
from app.core.capi.models import (
    CAPIConfig,
    CAPIEventData,
    CAPIPlatform,
    CAPIUserData,
)
from app.core.capi.service import CAPIService


# ── Helpers ──────────────────────────────────────────────────────────────────

def _patch_async_client(service: CAPIService, handler):
    """Replace the FacebookCAPIClient's httpx.AsyncClient with a mock transport."""
    transport = httpx.MockTransport(handler)
    service._facebook._client = httpx.AsyncClient(transport=transport)


def _ev(event_id="evt-1", name="Purchase", value=9.99) -> CAPIEventData:
    return CAPIEventData(
        event_name = name,
        event_id   = event_id,
        event_time = 1700000000,
        action_source = "app",
        user_data  = CAPIUserData(
            client_ip_address="1.2.3.4",
            client_user_agent="UA/1.0",
            external_id="user-42",
        ),
        value      = value,
        currency   = "USD",
        source     = "manual",
    )


# ── Hashing ──────────────────────────────────────────────────────────────────

class TestHashing:
    def test_email_lowercased_and_hashed(self):
        c = FacebookCAPIClient()
        out = c._hash_user_data(CAPIUserData(em="USER@Example.COM"))
        assert out["em"] != "USER@Example.COM"
        assert len(out["em"]) == 64

    def test_already_hashed_pass_through(self):
        c = FacebookCAPIClient()
        pre = "a" * 64
        out = c._hash_user_data(CAPIUserData(em=pre))
        assert out["em"] == pre

    def test_ip_and_ua_not_hashed(self):
        c = FacebookCAPIClient()
        out = c._hash_user_data(CAPIUserData(
            client_ip_address="1.2.3.4",
            client_user_agent="Mozilla",
        ))
        assert out["client_ip_address"] == "1.2.3.4"
        assert out["client_user_agent"] == "Mozilla"

    def test_external_id_hashed(self):
        c = FacebookCAPIClient()
        out = c._hash_user_data(CAPIUserData(external_id="raw-uid"))
        assert out["external_id"] != "raw-uid"
        assert len(out["external_id"]) == 64

    def test_payload_includes_test_event_code(self):
        c = FacebookCAPIClient()
        payload = c._build_payload(_ev(), test_event_code="TEST123")
        assert payload["test_event_code"] == "TEST123"
        assert payload["data"][0]["custom_data"]["value"] == 9.99
        assert payload["data"][0]["custom_data"]["currency"] == "USD"


# ── Forward: success path ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forward_success_logs_succeeded(conn, capi_config_row):
    svc = CAPIService()
    svc.load_configs(conn)

    captured = {}
    def handler(req):
        captured["url"]  = str(req.url)
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"events_received": 1})

    _patch_async_client(svc, handler)
    res = await svc.forward(conn, capi_config_row, _ev(event_id="ok-1"))
    await svc.close()

    assert res.success is True
    assert res.status_code == 200
    assert "PIXEL123" in captured["url"]
    assert captured["body"]["data"][0]["event_name"] == "Purchase"

    row = conn.execute(
        "SELECT succeeded, attempts, response_code FROM capi_delivery_log"
    ).fetchone()
    assert row["succeeded"] == 1
    assert row["attempts"] == 1
    assert row["response_code"] == 200


# ── Forward: failure schedules retry ────────────────────────────────────────

@pytest.mark.asyncio
async def test_forward_failure_schedules_retry(conn, capi_config_row):
    svc = CAPIService()
    svc.load_configs(conn)

    _patch_async_client(svc, lambda req: httpx.Response(500, text="boom"))
    res = await svc.forward(conn, capi_config_row, _ev(event_id="fail-1"))
    await svc.close()

    assert res.success is False
    row = conn.execute(
        "SELECT succeeded, attempts, next_retry_at FROM capi_delivery_log"
    ).fetchone()
    assert row["succeeded"] == 0
    assert row["attempts"] == 1
    assert row["next_retry_at"] is not None


# ── Dedup ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forward_dedups_successful_events(conn, capi_config_row):
    svc = CAPIService()
    svc.load_configs(conn)

    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    _patch_async_client(svc, handler)

    await svc.forward(conn, capi_config_row, _ev(event_id="dup-1"))
    res2 = await svc.forward(conn, capi_config_row, _ev(event_id="dup-1"))
    await svc.close()

    assert calls["n"] == 1   # second call short-circuited
    assert res2.success is True
    assert "[dedup]" in res2.response_body


# ── No config ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forward_without_config_logs_failure(conn):
    svc = CAPIService()
    svc.load_configs(conn)   # no rows

    res = await svc.forward(conn, "unknown.app", _ev(event_id="noconf-1"))
    await svc.close()

    assert res.success is False
    assert "no config" in (res.error or "")
    row = conn.execute("SELECT succeeded, last_error FROM capi_delivery_log").fetchone()
    assert row["succeeded"] == 0
    assert "no config" in row["last_error"]


# ── Retry worker ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_pending_picks_up_due_rows(conn, capi_config_row):
    svc = CAPIService()
    svc.load_configs(conn)

    # Seed a failed delivery whose retry is due.
    past = (datetime.utcnow() - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO capi_delivery_log (
            app_id, platform, event_name, event_id, event_source,
            pixel_id, payload_json,
            response_code, response_body,
            attempts, succeeded, last_error, next_retry_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (capi_config_row, "facebook", "Purchase", "retry-1", "manual",
         "PIXEL123", json.dumps({"data": [{"event_name": "Purchase"}]}),
         500, "boom", 1, 0, "http 500", past),
    )
    conn.commit()

    _patch_async_client(svc, lambda req: httpx.Response(200, text="{}"))
    n = await svc.retry_pending(conn)
    await svc.close()

    assert n == 1
    row = conn.execute(
        "SELECT succeeded, attempts, next_retry_at FROM capi_delivery_log WHERE event_id='retry-1'"
    ).fetchone()
    assert row["succeeded"] == 1
    assert row["attempts"] == 2
    assert row["next_retry_at"] is None


@pytest.mark.asyncio
async def test_retry_pending_skips_future_rows(conn, capi_config_row):
    svc = CAPIService()
    svc.load_configs(conn)

    future = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO capi_delivery_log (
            app_id, platform, event_name, event_id, event_source,
            pixel_id, payload_json,
            response_code, attempts, succeeded, next_retry_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (capi_config_row, "facebook", "Purchase", "future-1", "manual",
         "PIXEL123", "{}", 500, 1, 0, future),
    )
    conn.commit()

    n = await svc.retry_pending(conn)
    await svc.close()
    assert n == 0


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts(conn, capi_config_row):
    svc = CAPIService()
    svc.load_configs(conn)

    past = (datetime.utcnow() - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
    # Simulate already on attempt 3 (= _MAX_ATTEMPTS) — one more failure
    # should leave next_retry_at NULL.
    conn.execute(
        """
        INSERT INTO capi_delivery_log (
            app_id, platform, event_name, event_id, event_source,
            pixel_id, payload_json,
            response_code, attempts, succeeded, next_retry_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (capi_config_row, "facebook", "Purchase", "giveup-1", "manual",
         "PIXEL123", "{}", 500, 2, 0, past),
    )
    conn.commit()

    _patch_async_client(svc, lambda req: httpx.Response(500))
    n = await svc.retry_pending(conn)
    await svc.close()

    assert n == 1
    row = conn.execute(
        "SELECT attempts, succeeded, next_retry_at FROM capi_delivery_log WHERE event_id='giveup-1'"
    ).fetchone()
    assert row["attempts"] == 3
    assert row["succeeded"] == 0
    assert row["next_retry_at"] is None


def test_load_configs_prefers_latest_duplicate_app_platform(conn):
    conn.execute(
        """
        INSERT INTO capi_configs (
            app_id, platform, pixel_id, access_token, api_version, enabled, description, updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        ("dup.app", "facebook", "PIXEL_OLD", "TOKEN_old", "v21.0", 1, "", "2026-01-01 00:00:00"),
    )
    conn.execute(
        """
        INSERT INTO capi_configs (
            app_id, platform, pixel_id, access_token, api_version, enabled, description, updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        ("dup.app", "facebook", "PIXEL_NEW", "TOKEN_new", "v21.0", 1, "", "2026-02-01 00:00:00"),
    )
    conn.commit()

    svc = CAPIService()
    svc.load_configs(conn)
    cfg = svc.get_config("dup.app", CAPIPlatform.FACEBOOK)

    assert cfg is not None
    assert cfg.pixel_id == "PIXEL_NEW"
    assert cfg.access_token == "TOKEN_new"


def test_create_config_rejects_second_app_platform_config(conn, monkeypatch):
    @contextmanager
    def fake_connection():
        yield conn

    monkeypatch.setattr(capi_admin.db_manager, "get_connection", fake_connection)
    load_calls: list[bool] = []
    monkeypatch.setattr(capi_admin.capi_service, "load_configs", lambda db_conn: load_calls.append(True))

    body = capi_admin.CAPIConfigCreate(
        app_id="dup.app",
        platform="facebook",
        pixel_id="PIXEL_1",
        access_token="TOKEN_1234567890",
    )
    created = capi_admin.create_config(body)
    assert created["success"] is True
    assert load_calls == [True]

    with pytest.raises(HTTPException) as exc:
        capi_admin.create_config(
            capi_admin.CAPIConfigCreate(
                app_id="dup.app",
                platform="facebook",
                pixel_id="PIXEL_2",
                access_token="TOKEN_0987654321",
            )
        )

    assert exc.value.status_code == 409
