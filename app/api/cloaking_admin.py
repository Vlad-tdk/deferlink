"""
Cloaking Admin API

CRUD endpoints for managing custom IP/UA rules and viewing the audit log.
Also exposes a /test endpoint so you can check what decision the engine would
make for any given IP + User-Agent without sending real traffic.

Endpoints:
  GET    /api/v1/cloaking/rules/ip              list IP rules
  POST   /api/v1/cloaking/rules/ip              add IP rule
  PATCH  /api/v1/cloaking/rules/ip/{id}         update IP rule
  DELETE /api/v1/cloaking/rules/ip/{id}         delete IP rule

  GET    /api/v1/cloaking/rules/ua              list UA rules
  POST   /api/v1/cloaking/rules/ua              add UA rule
  PATCH  /api/v1/cloaking/rules/ua/{id}         update UA rule
  DELETE /api/v1/cloaking/rules/ua/{id}         delete UA rule

  POST   /api/v1/cloaking/test                  test engine decision
  GET    /api/v1/cloaking/log                   audit log (last N decisions)
  GET    /api/v1/cloaking/stats                 aggregate stats from audit log
"""

import json
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, validator

from ..core.cloaking import VisitorType, get_engine
from ..core.cloaking.models import IPRule, UARuleRecord
from ..database import db_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/cloaking", tags=["Cloaking Admin"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class IPRuleCreate(BaseModel):
    cidr:         Optional[str]  = None
    ip_exact:     Optional[str]  = None
    asn:          Optional[int]  = None
    visitor_type: str            = Field(..., pattern="^(bot|ad_review|suspicious|real_user)$")
    confidence:   float          = Field(0.9, ge=0.0, le=1.0)
    description:  str            = Field("", max_length=255)
    enabled:      bool           = True

    def model_post_init(self, __context) -> None:
        count = sum(1 for x in (self.cidr, self.ip_exact, self.asn) if x is not None)
        if count != 1:
            raise ValueError("Exactly one of cidr / ip_exact / asn must be set")


class IPRuleUpdate(BaseModel):
    visitor_type: Optional[str]  = Field(None, pattern="^(bot|ad_review|suspicious|real_user)$")
    confidence:   Optional[float] = Field(None, ge=0.0, le=1.0)
    description:  Optional[str]  = None
    enabled:      Optional[bool] = None


class UARuleCreate(BaseModel):
    pattern:      str   = Field(..., min_length=1, max_length=500)
    visitor_type: str   = Field(..., pattern="^(bot|ad_review|suspicious|real_user)$")
    confidence:   float = Field(0.9, ge=0.0, le=1.0)
    description:  str   = Field("", max_length=255)
    enabled:      bool  = True

    @validator("pattern")
    def valid_regex(cls, v):
        try:
            re.compile(v, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Invalid regex: {exc}")
        return v


class UARuleUpdate(BaseModel):
    pattern:      Optional[str]  = None
    visitor_type: Optional[str]  = Field(None, pattern="^(bot|ad_review|suspicious|real_user)$")
    confidence:   Optional[float] = Field(None, ge=0.0, le=1.0)
    description:  Optional[str]  = None
    enabled:      Optional[bool] = None


class TestRequest(BaseModel):
    ip:          str            = Field(..., min_length=2)
    user_agent:  str            = Field("", max_length=1000)
    headers:     Optional[dict] = None
    cookies:     Optional[dict] = None
    referer:     Optional[str]  = None
    asn:         Optional[int]  = None

    class Config:
        json_schema_extra = {
            "example": {
                "ip":         "66.249.64.1",
                "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "headers":    {"accept-language": "", "accept": "*/*"},
            }
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_all_rules():
    """Load all enabled rules from DB and reload the engine."""
    ip_rows = db_manager.execute_query(
        "SELECT id, cidr, ip_exact, asn, visitor_type, confidence, description, enabled "
        "FROM cloaking_ip_rules"
    )
    ua_rows = db_manager.execute_query(
        "SELECT id, pattern, visitor_type, confidence, description, enabled "
        "FROM cloaking_ua_rules"
    )

    ip_rules = [
        IPRule(
            id=r["id"], cidr=r["cidr"], ip_exact=r["ip_exact"], asn=r["asn"],
            visitor_type=VisitorType(r["visitor_type"]),
            confidence=r["confidence"], description=r["description"],
            enabled=bool(r["enabled"]),
        )
        for r in ip_rows
    ]
    ua_rules = [
        UARuleRecord(
            id=r["id"], pattern=r["pattern"],
            visitor_type=VisitorType(r["visitor_type"]),
            confidence=r["confidence"], description=r["description"],
            enabled=bool(r["enabled"]),
        )
        for r in ua_rows
    ]

    get_engine().reload_rules(ip_rules, ua_rules)
    return ip_rules, ua_rules


# ── IP Rules ──────────────────────────────────────────────────────────────────

@router.get("/rules/ip", summary="List all custom IP rules")
async def list_ip_rules():
    rows = db_manager.execute_query(
        "SELECT * FROM cloaking_ip_rules ORDER BY created_at DESC"
    )
    return {"success": True, "rules": rows, "count": len(rows)}


@router.post("/rules/ip", summary="Add a custom IP rule", status_code=201)
async def add_ip_rule(body: IPRuleCreate):
    rule_id = db_manager.execute_insert(
        """
        INSERT INTO cloaking_ip_rules
            (cidr, ip_exact, asn, visitor_type, confidence, description, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (body.cidr, body.ip_exact, body.asn, body.visitor_type,
         body.confidence, body.description, int(body.enabled)),
    )
    _load_all_rules()
    return {"success": True, "id": rule_id, "message": "IP rule added and engine reloaded"}


@router.patch("/rules/ip/{rule_id}", summary="Update a custom IP rule")
async def update_ip_rule(rule_id: int, body: IPRuleUpdate):
    existing = db_manager.execute_query(
        "SELECT id FROM cloaking_ip_rules WHERE id = ?", (rule_id,)
    )
    if not existing:
        raise HTTPException(404, "Rule not found")

    updates = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(422, "No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values     = list(updates.values()) + [rule_id]
    db_manager.execute_update(
        f"UPDATE cloaking_ip_rules SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values,
    )
    _load_all_rules()
    return {"success": True, "message": "IP rule updated and engine reloaded"}


@router.delete("/rules/ip/{rule_id}", summary="Delete a custom IP rule")
async def delete_ip_rule(rule_id: int):
    rows = db_manager.execute_update(
        "DELETE FROM cloaking_ip_rules WHERE id = ?", (rule_id,)
    )
    if rows == 0:
        raise HTTPException(404, "Rule not found")
    _load_all_rules()
    return {"success": True, "message": "IP rule deleted and engine reloaded"}


# ── UA Rules ──────────────────────────────────────────────────────────────────

@router.get("/rules/ua", summary="List all custom UA rules")
async def list_ua_rules():
    rows = db_manager.execute_query(
        "SELECT * FROM cloaking_ua_rules ORDER BY created_at DESC"
    )
    return {"success": True, "rules": rows, "count": len(rows)}


@router.post("/rules/ua", summary="Add a custom UA rule", status_code=201)
async def add_ua_rule(body: UARuleCreate):
    rule_id = db_manager.execute_insert(
        """
        INSERT INTO cloaking_ua_rules
            (pattern, visitor_type, confidence, description, enabled)
        VALUES (?, ?, ?, ?, ?)
        """,
        (body.pattern, body.visitor_type, body.confidence,
         body.description, int(body.enabled)),
    )
    _load_all_rules()
    return {"success": True, "id": rule_id, "message": "UA rule added and engine reloaded"}


@router.patch("/rules/ua/{rule_id}", summary="Update a custom UA rule")
async def update_ua_rule(rule_id: int, body: UARuleUpdate):
    existing = db_manager.execute_query(
        "SELECT id FROM cloaking_ua_rules WHERE id = ?", (rule_id,)
    )
    if not existing:
        raise HTTPException(404, "Rule not found")

    if body.pattern:
        try:
            re.compile(body.pattern, re.IGNORECASE)
        except re.error as exc:
            raise HTTPException(422, f"Invalid regex: {exc}")

    updates = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(422, "No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values     = list(updates.values()) + [rule_id]
    db_manager.execute_update(
        f"UPDATE cloaking_ua_rules SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values,
    )
    _load_all_rules()
    return {"success": True, "message": "UA rule updated and engine reloaded"}


@router.delete("/rules/ua/{rule_id}", summary="Delete a custom UA rule")
async def delete_ua_rule(rule_id: int):
    rows = db_manager.execute_update(
        "DELETE FROM cloaking_ua_rules WHERE id = ?", (rule_id,)
    )
    if rows == 0:
        raise HTTPException(404, "Rule not found")
    _load_all_rules()
    return {"success": True, "message": "UA rule deleted and engine reloaded"}


# ── Test endpoint ─────────────────────────────────────────────────────────────

@router.post("/test", summary="Test engine decision for a given IP + UA")
async def test_decision(body: TestRequest):
    """
    Returns the full CloakingDecision including all matched signals.
    Useful for debugging and verifying rules without sending real traffic.
    """
    engine   = get_engine()
    decision = engine.decide(
        ip=body.ip,
        user_agent=body.user_agent,
        headers={k.lower(): v for k, v in (body.headers or {}).items()},
        cookies=body.cookies,
        referer=body.referer,
        asn=body.asn,
    )
    return {
        "success":      True,
        "visitor_type": decision.visitor_type.value,
        "action":       decision.action.value,
        "confidence":   decision.confidence,
        "is_bot":       decision.is_bot,
        "signals": [
            {
                "source":       s.source,
                "visitor_type": s.visitor_type.value,
                "confidence":   s.confidence,
                "description":  s.description,
                "matched":      s.matched_value,
            }
            for s in decision.signals
        ],
    }


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/log", summary="View recent cloaking decisions audit log")
async def get_log(
    limit:        int           = Query(100, ge=1, le=1000),
    visitor_type: Optional[str] = Query(None),
    ip:           Optional[str] = Query(None),
):
    conditions = []
    params     = []

    if visitor_type:
        conditions.append("visitor_type = ?")
        params.append(visitor_type)
    if ip:
        conditions.append("ip = ?")
        params.append(ip)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows  = db_manager.execute_query(
        f"SELECT * FROM cloaking_decisions_log {where} ORDER BY timestamp DESC LIMIT ?",
        params + [limit],
    )
    return {"success": True, "rows": rows, "count": len(rows)}


@router.get("/stats", summary="Aggregate cloaking decision statistics")
async def get_stats(days: int = Query(7, ge=1, le=90)):
    rows = db_manager.execute_query(
        """
        SELECT
            visitor_type,
            action,
            COUNT(*)                         AS total,
            ROUND(AVG(confidence), 3)        AS avg_confidence,
            COUNT(DISTINCT ip)               AS unique_ips
        FROM cloaking_decisions_log
        WHERE timestamp >= datetime('now', ? || ' days')
        GROUP BY visitor_type, action
        ORDER BY total DESC
        """,
        (f"-{days}",),
    )
    total = sum(r["total"] for r in rows)
    return {"success": True, "period_days": days, "total_decisions": total, "breakdown": rows}
