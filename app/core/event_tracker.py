"""
Event tracker — AppsFlyer-style event storage and analytics.
Хранение событий и базовая аналитика (воронка, выручка, DAU и т.д.)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import db_manager

logger = logging.getLogger(__name__)

# ── Standard event names (mirrors AppsFlyer) ─────────────────────────────────

STANDARD_EVENTS = {
    "af_install",
    "af_launch",
    "af_complete_registration",
    "af_login",
    "af_purchase",
    "af_add_to_cart",
    "af_add_to_wishlist",
    "af_initiated_checkout",
    "af_content_view",
    "af_search",
    "af_subscribe",
    "af_level_achieved",
    "af_tutorial_completion",
    "af_rate",
    "af_share",
    "af_invite",
    "af_re_engage",
    "af_update",
}


# ── Write ─────────────────────────────────────────────────────────────────────

def insert_event(
    event_id: str,
    event_name: str,
    timestamp: str,
    session_id: Optional[str] = None,
    app_user_id: Optional[str] = None,
    promo_id: Optional[str] = None,
    revenue: Optional[float] = None,
    currency: str = "USD",
    properties: Optional[Dict[str, Any]] = None,
    platform: str = "iOS",
    app_version: Optional[str] = None,
    sdk_version: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> str:
    """
    Insert a single event.

    Returns:
        "inserted" | "duplicate" | "failed"
    """
    props_json = json.dumps(properties, ensure_ascii=False) if properties else None

    try:
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
            """
            INSERT OR IGNORE INTO user_events
                (event_id, session_id, app_user_id, promo_id, event_name,
                 revenue, currency, properties, platform, app_version, sdk_version,
                 timestamp, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event_id, session_id, app_user_id, promo_id, event_name,
                    revenue, currency, props_json, platform, app_version, sdk_version,
                    timestamp, ip_address,
                ),
            )
            conn.commit()

        if cur.rowcount == 0:
            logger.debug("Duplicate event ignored: %s", event_id[:8])
            return "duplicate"

        logger.debug("Event inserted: %s / %s", event_name, event_id[:8])
        return "inserted"
    except Exception as exc:
        logger.error("Failed to insert event %s: %s", event_id, exc)
        return "failed"


def insert_events_batch(events: List[Dict[str, Any]], ip_address: Optional[str] = None) -> Dict[str, int]:
    """Insert a batch of events.  Returns {inserted, duplicate, failed}."""
    inserted = duplicate = failed = 0

    for ev in events:
        event_id   = ev.get("event_id", "")
        event_name = ev.get("event_name", "")
        if not event_id or not event_name:
            failed += 1
            continue

        # Check duplicate before insert to track count
        existing = db_manager.execute_query(
            "SELECT 1 FROM user_events WHERE event_id = ?", (event_id,)
        )
        if existing:
            duplicate += 1
            continue

        status = insert_event(
            event_id=event_id,
            event_name=event_name,
            timestamp=ev.get("timestamp", datetime.now(timezone.utc).isoformat()),
            session_id=ev.get("session_id"),
            app_user_id=ev.get("app_user_id"),
            promo_id=ev.get("promo_id"),
            revenue=ev.get("revenue"),
            currency=ev.get("currency", "USD"),
            properties=ev.get("properties"),
            platform=ev.get("platform", "iOS"),
            app_version=ev.get("app_version"),
            sdk_version=ev.get("sdk_version"),
            ip_address=ip_address,
        )
        if status == "inserted":
            inserted += 1
        elif status == "duplicate":
            duplicate += 1
        else:
            failed += 1

    logger.info("Batch: inserted=%d duplicate=%d failed=%d", inserted, duplicate, failed)
    return {"inserted": inserted, "duplicate": duplicate, "failed": failed}


# ── Read / Analytics ──────────────────────────────────────────────────────────

def get_event_stats(
    start: Optional[str] = None,
    end: Optional[str] = None,
    promo_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate event statistics for a time window."""
    conditions = []
    params: List[Any] = []

    if start:
        conditions.append("timestamp >= ?")
        params.append(start)
    if end:
        conditions.append("timestamp <= ?")
        params.append(end)
    if promo_id:
        conditions.append("promo_id = ?")
        params.append(promo_id)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Total events + unique users
    row = db_manager.execute_query(
        f"""
        SELECT
            COUNT(*)                              AS total_events,
            COUNT(DISTINCT app_user_id)           AS unique_users,
            COUNT(DISTINCT session_id)            AS unique_sessions,
            COALESCE(SUM(revenue), 0)             AS total_revenue,
            COUNT(CASE WHEN revenue IS NOT NULL THEN 1 END) AS revenue_events
        FROM user_events {where}
        """,
        params,
    )
    totals = row[0] if row else {}

    # Top events
    top_events = db_manager.execute_query(
        f"""
        SELECT event_name, COUNT(*) AS cnt, COALESCE(SUM(revenue), 0) AS revenue
        FROM user_events {where}
        GROUP BY event_name
        ORDER BY cnt DESC
        LIMIT 20
        """,
        params,
    )

    # Revenue by currency
    revenue_by_currency = db_manager.execute_query(
        f"""
        SELECT currency, COALESCE(SUM(revenue), 0) AS total
        FROM user_events
        WHERE revenue IS NOT NULL {('AND ' + ' AND '.join(conditions)) if conditions else ''}
        GROUP BY currency
        """,
        params,
    )

    return {
        "total_events":      totals.get("total_events", 0),
        "unique_users":      totals.get("unique_users", 0),
        "unique_sessions":   totals.get("unique_sessions", 0),
        "total_revenue":     round(totals.get("total_revenue", 0.0), 2),
        "revenue_events":    totals.get("revenue_events", 0),
        "top_events":        top_events,
        "revenue_by_currency": revenue_by_currency,
    }


def get_funnel(
    steps: List[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    promo_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ordered funnel analysis.

    For each step N, count users who completed step N-1 AND step N
    (in chronological order, i.e. timestamp of step N ≥ timestamp of step N-1).
    """
    if not steps:
        return {"steps": [], "funnel": []}

    time_conditions = []
    base_params: List[Any] = []
    if start:
        time_conditions.append("timestamp >= ?")
        base_params.append(start)
    if end:
        time_conditions.append("timestamp <= ?")
        base_params.append(end)
    if promo_id:
        time_conditions.append("promo_id = ?")
        base_params.append(promo_id)

    where_base = (" AND ".join(time_conditions)) if time_conditions else "1=1"

    funnel: List[Dict[str, Any]] = []
    prev_users: Optional[set] = None

    for idx, step in enumerate(steps):
        rows = db_manager.execute_query(
            f"""
            SELECT app_user_id, MIN(timestamp) AS first_ts
            FROM user_events
            WHERE event_name = ? AND {where_base} AND app_user_id IS NOT NULL
            GROUP BY app_user_id
            """,
            [step] + base_params,
        )

        step_users = {r["app_user_id"]: r["first_ts"] for r in rows}

        if idx == 0:
            entered = set(step_users.keys())
        else:
            # Only users who were in the previous step AND did this step later
            entered = set()
            for uid, ts in step_users.items():
                if uid in prev_users_ts and ts >= prev_users_ts[uid]:  # type: ignore[name-defined]
                    entered.add(uid)

        prev_users_ts = {uid: step_users[uid] for uid in entered}  # noqa: F841

        count       = len(entered)
        prev_count  = funnel[idx - 1]["users"] if idx > 0 else count
        conversion  = round(count / prev_count * 100, 1) if prev_count > 0 else 0.0
        overall_top = funnel[0]["users"] if funnel else count
        overall_conv = round(count / overall_top * 100, 1) if overall_top > 0 else 100.0

        funnel.append({
            "step":             idx + 1,
            "event_name":       step,
            "users":            count,
            "conversion_prev":  conversion,    # vs. previous step
            "conversion_total": overall_conv,  # vs. first step
        })

        prev_users = entered  # noqa: F841 — used as prev_users_ts above

    return {"steps": steps, "funnel": funnel}


def get_cohort_revenue(
    promo_id: Optional[str] = None,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """Daily revenue aggregated per promo_id."""
    conditions = ["revenue IS NOT NULL"]
    params: List[Any] = []

    if promo_id:
        conditions.append("promo_id = ?")
        params.append(promo_id)

    where = "WHERE " + " AND ".join(conditions)

    return db_manager.execute_query(
        f"""
        SELECT
            DATE(timestamp) AS day,
            promo_id,
            currency,
            COUNT(*)           AS purchases,
            SUM(revenue)       AS revenue,
            AVG(revenue)       AS avg_order_value
        FROM user_events
        {where}
        GROUP BY day, promo_id, currency
        ORDER BY day DESC
        LIMIT ?
        """,
        params + [days * 10],  # rough cap
    )
