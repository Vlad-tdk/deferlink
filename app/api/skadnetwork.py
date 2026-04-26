"""
SKAdNetwork REST API.

Endpoints:

  Apple postback receiver:
    POST   /api/v1/skan/postback              Apple posts here

  CV config (SDK polls this):
    GET    /api/v1/skan/config                query: app_id=<bundle>
    PUT    /api/v1/skan/config                upsert per-app config

  Campaign decoders (admin):
    GET    /api/v1/skan/decoders
    POST   /api/v1/skan/decoders
    PATCH  /api/v1/skan/decoders/{id}
    DELETE /api/v1/skan/decoders/{id}

  Observability:
    GET    /api/v1/skan/postbacks             filter by app, campaign, seq
    GET    /api/v1/skan/stats                 CV distribution (last N days)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..core.skadnetwork import (
    DEFAULT_ENGAGEMENT_THRESHOLDS,
    DEFAULT_REVENUE_BUCKETS,
    skan_service,
)
from ..core.capi import CAPIEventData, CAPIPlatform, CAPIUserData, capi_service
from ..database import db_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/skan", tags=["SKAdNetwork"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DecoderRuleSchema(BaseModel):
    cv_min:           int   = Field(..., ge=0, le=63)
    cv_max:           int   = Field(..., ge=0, le=63)
    capi_event:       str   = Field(..., min_length=1, max_length=64)
    forward:          bool  = True
    static_value:     Optional[float] = None
    value_multiplier: float = 1.0
    currency:         str   = "USD"
    description:      str   = ""


class DecoderCreate(BaseModel):
    source_identifier: Optional[str] = None
    campaign_id:       Optional[int] = Field(None, ge=0, le=99)
    app_id:            str           = Field(..., min_length=1)
    rules:             List[DecoderRuleSchema]
    description:       str           = ""
    enabled:           bool          = True

    def model_post_init(self, __context) -> None:
        if self.source_identifier is None and self.campaign_id is None:
            raise ValueError("Either source_identifier or campaign_id is required")


class DecoderUpdate(BaseModel):
    rules:       Optional[List[DecoderRuleSchema]] = None
    description: Optional[str]  = None
    enabled:     Optional[bool] = None


class CVConfigUpsert(BaseModel):
    app_id:                     str    = Field(..., min_length=1)
    schema_version:             int    = 1
    schema_name:                str    = "rev3_eng2_flag1"
    revenue_buckets_usd:        Optional[List[float]] = None
    bounce_max_seconds:         int    = 30
    active_min_sessions:        int    = 2
    deep_min_sessions:          int    = 5
    deep_min_core_actions:      int    = 1
    power_requires_retention:   bool   = True
    conversion_window_hours:    int    = 48
    cache_ttl_seconds:          int    = 86400


# ── Postback receiver ─────────────────────────────────────────────────────────

@router.post("/postback")
async def receive_postback(request: Request) -> Dict[str, Any]:
    """
    Apple posts SKAdNetwork install postbacks here.

    Apple sends a JSON body with fields like:
      version, ad-network-id, source-identifier, transaction-id,
      conversion-value, coarse-conversion-value,
      postback-sequence-index, attribution-signature, did-win, ...

    We: parse → verify signature → persist → forward to CAPI (if decoder matches).
    """
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"bad JSON: {exc}")

    client_ip = request.client.host if request.client else None
    client_ua = request.headers.get("user-agent", "")

    try:
        with db_manager.get_connection() as conn:
            pb, row_id, instruction = skan_service.ingest_postback(payload, conn)

            # Forward to CAPI if decoder matched
            forward_result = None
            if instruction and pb.app_id:
                event = CAPIEventData(
                    event_name    = instruction.capi_event,
                    event_id      = f"skan_{pb.transaction_id}",
                    event_time    = int(datetime.utcnow().timestamp()),
                    action_source = "app",
                    user_data     = CAPIUserData(
                        client_ip_address=client_ip,
                        client_user_agent=client_ua,
                    ),
                    value         = instruction.value,
                    currency      = instruction.currency,
                    custom_data   = {
                        "skan_source_identifier": pb.source_identifier,
                        "skan_campaign_id":       pb.campaign_id,
                        "skan_sequence_index":    int(pb.postback_sequence_index),
                        "skan_conversion_value":  pb.conversion_value,
                        "skan_coarse_value":      (
                            pb.coarse_conversion_value.value
                            if pb.coarse_conversion_value else None
                        ),
                    },
                    source        = "skan",
                    source_ref_id = row_id,
                )
                try:
                    forward_result = await capi_service.forward(
                        conn=conn,
                        app_id=pb.app_id,
                        event=event,
                        platform=CAPIPlatform.FACEBOOK,
                    )
                    skan_service.mark_forwarded(
                        conn, row_id,
                        status=1 if forward_result.success else 2,
                        error=forward_result.error,
                    )
                except Exception as exc:
                    logger.exception("CAPI forward failed for postback %d", row_id)
                    skan_service.mark_forwarded(conn, row_id, status=2, error=str(exc))

        return {
            "success":            True,
            "postback_id":        row_id,
            "transaction_id":     pb.transaction_id,
            "signature_verified": pb.signature_verified,
            "decoded":            instruction is not None,
            "capi_forwarded":     forward_result.success if forward_result else False,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("SKAN postback handling failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ── CV config (SDK reads) ─────────────────────────────────────────────────────

@router.get("/config")
def get_cv_config(app_id: str = Query(..., min_length=1)) -> Dict[str, Any]:
    """Public endpoint — SDK polls this at startup and refreshes in background."""
    cfg = skan_service.get_config(app_id)
    return {
        "success":              True,
        "app_id":               cfg.app_id,
        "schema_version":       cfg.schema_version,
        "schema_name":          cfg.schema_name,
        "revenue_buckets_usd":  cfg.revenue_buckets_usd,
        "engagement_thresholds": {
            "bounce_max_seconds":       cfg.bounce_max_seconds,
            "active_min_sessions":      cfg.active_min_sessions,
            "deep_min_sessions":        cfg.deep_min_sessions,
            "deep_min_core_actions":    cfg.deep_min_core_actions,
            "power_requires_retention": cfg.power_requires_retention,
        },
        "conversion_window_hours": cfg.conversion_window_hours,
        "cache_ttl_seconds":       cfg.cache_ttl_seconds,
    }


@router.put("/config")
def upsert_cv_config(body: CVConfigUpsert) -> Dict[str, Any]:
    """Admin — upsert per-app CV config."""
    buckets = body.revenue_buckets_usd or DEFAULT_REVENUE_BUCKETS
    if len(buckets) != 8:
        raise HTTPException(400, "revenue_buckets_usd must have exactly 8 entries")
    if buckets != sorted(buckets):
        raise HTTPException(400, "revenue_buckets_usd must be sorted ascending")

    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO skan_cv_configs (
                app_id, schema_version, schema_name, revenue_buckets_json,
                bounce_max_seconds, active_min_sessions,
                deep_min_sessions, deep_min_core_actions,
                power_requires_retention,
                conversion_window_hours, cache_ttl_seconds
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(app_id) DO UPDATE SET
                schema_version           = excluded.schema_version,
                schema_name              = excluded.schema_name,
                revenue_buckets_json     = excluded.revenue_buckets_json,
                bounce_max_seconds       = excluded.bounce_max_seconds,
                active_min_sessions      = excluded.active_min_sessions,
                deep_min_sessions        = excluded.deep_min_sessions,
                deep_min_core_actions    = excluded.deep_min_core_actions,
                power_requires_retention = excluded.power_requires_retention,
                conversion_window_hours  = excluded.conversion_window_hours,
                cache_ttl_seconds        = excluded.cache_ttl_seconds,
                updated_at               = CURRENT_TIMESTAMP
        """, (
            body.app_id, body.schema_version, body.schema_name,
            json.dumps(buckets),
            body.bounce_max_seconds, body.active_min_sessions,
            body.deep_min_sessions, body.deep_min_core_actions,
            1 if body.power_requires_retention else 0,
            body.conversion_window_hours, body.cache_ttl_seconds,
        ))
        conn.commit()
        skan_service.load_rules(conn)

    return {"success": True, "app_id": body.app_id}


# ── Decoder CRUD ──────────────────────────────────────────────────────────────

@router.get("/decoders")
def list_decoders(
    app_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    where = "WHERE 1=1"
    params: List[Any] = []
    if app_id:
        where += " AND app_id = ?"
        params.append(app_id)

    with db_manager.get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, source_identifier, campaign_id, app_id,
                   decoder_json, description, enabled,
                   created_at, updated_at
              FROM skan_campaign_decoders
              {where}
             ORDER BY id DESC
            """,
            params,
        )
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["rules"] = json.loads(d.pop("decoder_json"))
            except Exception:
                d["rules"] = []
            rows.append(d)

    return {"success": True, "count": len(rows), "decoders": rows}


@router.post("/decoders")
def create_decoder(body: DecoderCreate) -> Dict[str, Any]:
    # Validate each rule's range
    for r in body.rules:
        if r.cv_min > r.cv_max:
            raise HTTPException(400, f"cv_min > cv_max in rule: {r}")

    rules_json = json.dumps([r.model_dump() for r in body.rules])

    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO skan_campaign_decoders (
                source_identifier, campaign_id, app_id,
                decoder_json, description, enabled
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                body.source_identifier,
                body.campaign_id,
                body.app_id,
                rules_json,
                body.description,
                1 if body.enabled else 0,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
        skan_service.load_rules(conn)

    return {"success": True, "id": new_id}


@router.patch("/decoders/{decoder_id}")
def update_decoder(decoder_id: int, body: DecoderUpdate) -> Dict[str, Any]:
    sets: List[str] = []
    params: List[Any] = []

    if body.rules is not None:
        for r in body.rules:
            if r.cv_min > r.cv_max:
                raise HTTPException(400, f"cv_min > cv_max in rule: {r}")
        sets.append("decoder_json = ?")
        params.append(json.dumps([r.model_dump() for r in body.rules]))

    if body.description is not None:
        sets.append("description = ?")
        params.append(body.description)

    if body.enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if body.enabled else 0)

    if not sets:
        raise HTTPException(400, "no fields to update")

    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(decoder_id)

    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE skan_campaign_decoders SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "decoder not found")
        conn.commit()
        skan_service.load_rules(conn)

    return {"success": True, "id": decoder_id}


@router.delete("/decoders/{decoder_id}")
def delete_decoder(decoder_id: int) -> Dict[str, Any]:
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM skan_campaign_decoders WHERE id = ?",
            (decoder_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "decoder not found")
        conn.commit()
        skan_service.load_rules(conn)

    return {"success": True, "id": decoder_id}


# ── Observability ─────────────────────────────────────────────────────────────

@router.get("/postbacks")
def list_postbacks(
    app_id:         Optional[str] = Query(None),
    source_id:      Optional[str] = Query(None),
    sequence_index: Optional[int] = Query(None, ge=0, le=2),
    limit:          int           = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    clauses: List[str] = ["1=1"]
    params: List[Any] = []
    if app_id:
        clauses.append("app_id = ?")
        params.append(app_id)
    if source_id:
        clauses.append("source_identifier = ?")
        params.append(source_id)
    if sequence_index is not None:
        clauses.append("postback_sequence_index = ?")
        params.append(sequence_index)

    with db_manager.get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, version, ad_network_id, source_identifier, campaign_id,
                   transaction_id, app_id, conversion_value,
                   coarse_conversion_value, postback_sequence_index,
                   did_win, signature_verified,
                   capi_forwarded, received_at
              FROM skan_postbacks
             WHERE {" AND ".join(clauses)}
             ORDER BY id DESC
             LIMIT ?
            """,
            params + [limit],
        )
        rows = [dict(r) for r in cur.fetchall()]

    return {"success": True, "count": len(rows), "postbacks": rows}


@router.get("/stats")
def cv_stats(
    app_id: Optional[str] = Query(None),
    days:   int           = Query(7, ge=1, le=90),
) -> Dict[str, Any]:
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    params: List[Any] = [since]
    app_clause = ""
    if app_id:
        app_clause = "AND app_id = ?"
        params.append(app_id)

    with db_manager.get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT conversion_value, SUM(postback_count) AS count
              FROM skan_cv_distribution
             WHERE date >= ? {app_clause}
             GROUP BY conversion_value
             ORDER BY conversion_value
            """,
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]

    total = sum(r["count"] for r in rows)
    return {
        "success":     True,
        "period_days": days,
        "app_id":      app_id,
        "total":       total,
        "distribution": rows,
    }
