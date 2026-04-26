"""
CAPI Admin API — manage per-app Facebook CAPI credentials and inspect
the delivery log.

Endpoints:
  GET    /api/v1/capi/configs                list configs
  POST   /api/v1/capi/configs                create config
  PATCH  /api/v1/capi/configs/{id}           update config
  DELETE /api/v1/capi/configs/{id}           delete config

  POST   /api/v1/capi/test                   dispatch a manual test event
  GET    /api/v1/capi/log                    delivery log (filterable)
  POST   /api/v1/capi/retry                  manually trigger retry worker
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import sqlite3

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.capi import (
    CAPIEventData,
    CAPIPlatform,
    CAPIUserData,
    capi_service,
)
from ..database import db_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/capi", tags=["CAPI Admin"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CAPIConfigCreate(BaseModel):
    app_id:          str  = Field(..., min_length=1)
    platform:        str  = Field("facebook", pattern="^(facebook|tiktok|google|snap)$")
    pixel_id:        str  = Field(..., min_length=1)
    access_token:    str  = Field(..., min_length=10)
    test_event_code: Optional[str] = None
    api_version:     str  = "v21.0"
    enabled:         bool = True
    description:     str  = ""


class CAPIConfigUpdate(BaseModel):
    pixel_id:        Optional[str]  = None
    access_token:    Optional[str]  = None
    test_event_code: Optional[str]  = None
    api_version:     Optional[str]  = None
    enabled:         Optional[bool] = None
    description:     Optional[str]  = None


class CAPITestEvent(BaseModel):
    app_id:       str  = Field(..., min_length=1)
    platform:     str  = Field("facebook", pattern="^(facebook|tiktok|google|snap)$")
    event_name:   str  = Field(..., min_length=1)
    event_id:     str  = Field(..., min_length=1)
    value:        Optional[float] = None
    currency:     str  = "USD"
    external_id:  Optional[str]   = None
    ip:           Optional[str]   = None
    user_agent:   Optional[str]   = None


# ── Config CRUD ───────────────────────────────────────────────────────────────

@router.get("/configs")
def list_configs(app_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    clauses: List[str] = ["1=1"]
    params: List[Any] = []
    if app_id:
        clauses.append("app_id = ?")
        params.append(app_id)

    with db_manager.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, app_id, platform, pixel_id,
                   test_event_code, api_version, enabled,
                   description, created_at, updated_at
              FROM capi_configs
             WHERE {' AND '.join(clauses)}
             ORDER BY id DESC
            """,
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]

    return {"success": True, "count": len(rows), "configs": rows}


@router.post("/configs")
def create_config(body: CAPIConfigCreate) -> Dict[str, Any]:
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        existing = cur.execute(
            """
            SELECT id FROM capi_configs
            WHERE app_id = ? AND platform = ?
            LIMIT 1
            """,
            (body.app_id, body.platform),
        ).fetchone()
        if existing:
            raise HTTPException(409, "config for app_id/platform already exists")
        try:
            cur.execute(
                """
                INSERT INTO capi_configs (
                    app_id, platform, pixel_id, access_token,
                    test_event_code, api_version, enabled, description
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    body.app_id, body.platform, body.pixel_id, body.access_token,
                    body.test_event_code, body.api_version,
                    1 if body.enabled else 0, body.description,
                ),
            )
            conn.commit()
            new_id = cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, f"duplicate config: {exc}")

        capi_service.load_configs(conn)

    return {"success": True, "id": new_id}


@router.patch("/configs/{config_id}")
def update_config(config_id: int, body: CAPIConfigUpdate) -> Dict[str, Any]:
    sets: List[str] = []
    params: List[Any] = []

    for field in ("pixel_id", "access_token", "test_event_code",
                  "api_version", "description"):
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = ?")
            params.append(val)

    if body.enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if body.enabled else 0)

    if not sets:
        raise HTTPException(400, "no fields to update")

    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(config_id)

    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE capi_configs SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "config not found")
        conn.commit()
        capi_service.load_configs(conn)

    return {"success": True, "id": config_id}


@router.delete("/configs/{config_id}")
def delete_config(config_id: int) -> Dict[str, Any]:
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM capi_configs WHERE id = ?", (config_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "config not found")
        conn.commit()
        capi_service.load_configs(conn)

    return {"success": True, "id": config_id}


# ── Test event (manual dispatch) ──────────────────────────────────────────────

@router.post("/test")
async def test_event(body: CAPITestEvent) -> Dict[str, Any]:
    """Fire a single event to the configured CAPI — useful for verifying setup."""
    try:
        platform = CAPIPlatform(body.platform)
    except ValueError:
        raise HTTPException(400, "unsupported platform")

    event = CAPIEventData(
        event_name    = body.event_name,
        event_id      = body.event_id,
        event_time    = int(datetime.now().timestamp()),
        action_source = "app",
        user_data     = CAPIUserData(
            client_ip_address=body.ip,
            client_user_agent=body.user_agent,
            external_id=body.external_id,
        ),
        value         = body.value,
        currency      = body.currency,
        source        = "manual",
    )

    with db_manager.get_connection() as conn:
        result = await capi_service.forward(
            conn=conn, app_id=body.app_id,
            event=event, platform=platform,
        )

    return {
        "success":        result.success,
        "status_code":    result.status_code,
        "response":       result.response_body,
        "error":          result.error,
        "delivery_log_id": result.delivery_log_id,
    }


# ── Delivery log ──────────────────────────────────────────────────────────────

@router.get("/log")
def delivery_log(
    app_id:       Optional[str]  = Query(None),
    event_source: Optional[str]  = Query(None, pattern="^(sdk|skan|manual)$"),
    succeeded:    Optional[bool] = Query(None),
    limit:        int            = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    clauses: List[str] = ["1=1"]
    params: List[Any] = []
    if app_id:
        clauses.append("app_id = ?")
        params.append(app_id)
    if event_source:
        clauses.append("event_source = ?")
        params.append(event_source)
    if succeeded is not None:
        clauses.append("succeeded = ?")
        params.append(1 if succeeded else 0)

    with db_manager.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, app_id, platform, event_name, event_id,
                   event_source, source_ref_id, pixel_id,
                   response_code, succeeded, attempts,
                   last_error, created_at, last_attempt_at, next_retry_at
              FROM capi_delivery_log
             WHERE {' AND '.join(clauses)}
             ORDER BY id DESC
             LIMIT ?
            """,
            params + [limit],
        )
        rows = [dict(r) for r in cur.fetchall()]

    return {"success": True, "count": len(rows), "rows": rows}


@router.post("/retry")
async def trigger_retry() -> Dict[str, Any]:
    """Manually trigger the retry worker (normally run on a schedule)."""
    with db_manager.get_connection() as conn:
        processed = await capi_service.retry_pending(conn)
    return {"success": True, "processed": processed}
