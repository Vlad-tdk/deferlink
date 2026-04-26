"""
Events API — AppsFlyer-style event tracking endpoints.

POST /api/v1/events          — single event
POST /api/v1/events/batch    — up to 100 events at once
GET  /api/v1/events/stats    — aggregate stats
GET  /api/v1/events/funnel   — funnel analysis
GET  /api/v1/events/revenue  — daily revenue cohort
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator

from ..core.event_tracker import (
    insert_event,
    insert_events_batch,
    get_event_stats,
    get_funnel,
    get_cohort_revenue,
    STANDARD_EVENTS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/events", tags=["Events"])


# ── Request / Response models ────────────────────────────────────────────────

class EventRequest(BaseModel):
    """Single event payload — mirrors AppsFlyer SDK parameters."""
    event_id:    str  = Field(...,  min_length=8, description="Client UUID — used for deduplication")
    event_name:  str  = Field(...,  min_length=1, max_length=100)
    timestamp:   str  = Field(...,  description="ISO 8601 client-side timestamp")

    # Attribution context (resolved by SDK after resolveOnFirstLaunch)
    session_id:  Optional[str]  = None
    app_user_id: Optional[str]  = None   # developer-supplied user ID
    promo_id:    Optional[str]  = None

    # Revenue
    revenue:     Optional[float] = Field(None, ge=0)
    currency:    str             = Field("USD", min_length=3, max_length=3)

    # Custom properties
    properties:  Optional[Dict[str, Any]] = None

    # Device / app context
    platform:    str            = Field("iOS", max_length=20)
    app_version: Optional[str]  = None
    sdk_version: Optional[str]  = None

    @validator("currency")
    def upper_currency(cls, v: str) -> str:
        return v.upper()

    @validator("timestamp")
    def validate_timestamp(cls, v: str) -> str:
        try:
            parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be valid ISO 8601") from exc

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @validator("properties")
    def limit_properties(cls, v: Optional[Dict]) -> Optional[Dict]:
        if v and len(v) > 50:
            raise ValueError("properties may contain at most 50 keys")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "event_id":    "550e8400-e29b-41d4-a716-446655440000",
                "event_name":  "af_purchase",
                "timestamp":   "2025-04-22T14:30:00Z",
                "session_id":  "abc-123",
                "app_user_id": "user_42",
                "promo_id":    "SUMMER24",
                "revenue":     29.99,
                "currency":    "USD",
                "properties":  {"item_id": "pro_monthly", "item_name": "Pro subscription"},
                "platform":    "iOS",
                "app_version": "2.1.0",
            }
        }


class BatchEventRequest(BaseModel):
    events: List[EventRequest] = Field(..., min_items=1, max_items=100)


class EventResponse(BaseModel):
    success: bool
    message: str
    event_id: Optional[str] = None


class BatchEventResponse(BaseModel):
    success:   bool
    inserted:  int
    duplicate: int
    failed:    int


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", response_model=EventResponse, summary="Track a single event")
async def track_event(body: EventRequest, request: Request):
    ip = request.client.host if request.client else None
    ok = insert_event(
        event_id=body.event_id,
        event_name=body.event_name,
        timestamp=body.timestamp,
        session_id=body.session_id,
        app_user_id=body.app_user_id,
        promo_id=body.promo_id,
        revenue=body.revenue,
        currency=body.currency,
        properties=body.properties,
        platform=body.platform,
        app_version=body.app_version,
        sdk_version=body.sdk_version,
        ip_address=ip,
    )
    if ok == "inserted":
        return EventResponse(success=True, message="Event tracked", event_id=body.event_id)
    if ok == "duplicate":
        return EventResponse(success=True, message="Duplicate event ignored", event_id=body.event_id)
    raise HTTPException(status_code=500, detail="Error tracking event")


@router.post("/batch", response_model=BatchEventResponse, summary="Track up to 100 events")
async def track_events_batch(body: BatchEventRequest, request: Request):
    ip = request.client.host if request.client else None
    raw = [ev.dict() for ev in body.events]
    result = insert_events_batch(raw, ip_address=ip)
    return BatchEventResponse(success=True, **result)


@router.get("/stats", summary="Aggregate event statistics")
async def event_stats(
    start:    Optional[str] = Query(None, description="ISO 8601 start time"),
    end:      Optional[str] = Query(None, description="ISO 8601 end time"),
    promo_id: Optional[str] = Query(None, description="Filter by promo_id"),
):
    try:
        data = get_event_stats(start=start, end=end, promo_id=promo_id)
        return {"success": True, **data}
    except Exception as exc:
        logger.error("event_stats error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/funnel", summary="Ordered funnel conversion analysis")
async def event_funnel(
    steps:    List[str] = Query(..., description="Ordered event names, e.g. af_content_view,af_add_to_cart,af_purchase"),
    start:    Optional[str] = Query(None),
    end:      Optional[str] = Query(None),
    promo_id: Optional[str] = Query(None),
):
    if len(steps) < 2:
        raise HTTPException(status_code=422, detail="Funnel requires at least 2 steps")
    if len(steps) > 10:
        raise HTTPException(status_code=422, detail="Funnel supports at most 10 steps")
    try:
        data = get_funnel(steps=steps, start=start, end=end, promo_id=promo_id)
        return {"success": True, **data}
    except Exception as exc:
        logger.error("event_funnel error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/revenue", summary="Daily revenue cohort")
async def event_revenue(
    promo_id: Optional[str] = Query(None),
    days:     int           = Query(30, ge=1, le=365),
):
    try:
        rows = get_cohort_revenue(promo_id=promo_id, days=days)
        return {"success": True, "rows": rows}
    except Exception as exc:
        logger.error("event_revenue error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/standard-events", summary="List all standard event names")
async def list_standard_events():
    return {"standard_events": sorted(STANDARD_EVENTS)}
