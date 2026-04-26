"""
CAPI service — orchestrates config lookup, platform dispatch, persistence
to delivery log, and retry bookkeeping.

Retry strategy: on failure, schedule `next_retry_at` with exponential
backoff (1min, 5min, 30min). After 3 failed attempts the row is left
with next_retry_at = NULL and succeeded = 0. A background worker (cron
or periodic task) picks up rows where next_retry_at <= now and retries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .facebook import FacebookCAPIClient
from .models import (
    CAPIConfig,
    CAPIDeliveryResult,
    CAPIEventData,
    CAPIPlatform,
)

logger = logging.getLogger(__name__)

# Retry backoff schedule (seconds). Index = attempt number (1-based).
_RETRY_SCHEDULE = [60, 300, 1800]  # 1m, 5m, 30m
_MAX_ATTEMPTS   = 3


class CAPIService:
    """Thread-safe; construct once per process."""

    def __init__(self) -> None:
        self._facebook = FacebookCAPIClient()
        # Config cache: (app_id, platform) → CAPIConfig
        self._configs: Dict[tuple[str, str], CAPIConfig] = {}

    async def close(self) -> None:
        await self._facebook.close()

    # ── Config management ────────────────────────────────────────────────────

    def load_configs(self, conn: sqlite3.Connection) -> None:
        """Reload config cache from DB. Call after admin changes."""
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT app_id, platform, pixel_id, access_token,
                   test_event_code, api_version, enabled
            FROM capi_configs
            WHERE enabled = 1
        """)
        new_cache: Dict[tuple[str, str], CAPIConfig] = {}
        for row in cur.fetchall():
            try:
                cfg = CAPIConfig(
                    app_id          = row["app_id"],
                    platform        = CAPIPlatform(row["platform"]),
                    pixel_id        = row["pixel_id"],
                    access_token    = row["access_token"],
                    test_event_code = row["test_event_code"],
                    api_version     = row["api_version"],
                    enabled         = bool(row["enabled"]),
                )
                new_cache[(cfg.app_id, cfg.platform.value)] = cfg
            except Exception as exc:
                logger.warning("CAPIService: skipping bad config: %s", exc)

        self._configs = new_cache
        logger.info("CAPIService: loaded %d configs", len(new_cache))

    def get_config(
        self,
        app_id:   str,
        platform: CAPIPlatform = CAPIPlatform.FACEBOOK,
    ) -> Optional[CAPIConfig]:
        return self._configs.get((app_id, platform.value))

    # ── Forwarding ───────────────────────────────────────────────────────────

    async def forward(
        self,
        conn:     sqlite3.Connection,
        app_id:   str,
        event:    CAPIEventData,
        platform: CAPIPlatform = CAPIPlatform.FACEBOOK,
    ) -> CAPIDeliveryResult:
        """
        Send event to the target CAPI and persist a delivery log entry.

        Deduplication: if a prior SUCCESSFUL delivery for the same
        (app_id, platform, event_id) exists, skip and return that result.
        """
        # Dedup check
        existing = self._find_successful_delivery(conn, app_id, platform, event.event_id)
        if existing is not None:
            logger.debug(
                "CAPI dedup: event_id=%s already forwarded successfully",
                event.event_id,
            )
            return CAPIDeliveryResult(
                success=True,
                status_code=200,
                response_body="[dedup] already delivered",
                delivery_log_id=existing,
            )

        config = self.get_config(app_id, platform)
        if config is None:
            log_id = self._log_and_return(
                conn, app_id, event, platform,
                pixel_id="", payload={}, success=False,
                status_code=None, body="",
                error="no config for app/platform",
            )
            return CAPIDeliveryResult(
                success         = False,
                status_code     = None,
                response_body   = "",
                error           = "no config for app/platform",
                delivery_log_id = log_id,
            )

        payload = self._facebook._build_payload(event, test_event_code=config.test_event_code)

        if platform == CAPIPlatform.FACEBOOK:
            result = await self._facebook.send(config, event)
        else:
            result = CAPIDeliveryResult(
                success=False, status_code=None,
                response_body="",
                error=f"platform {platform.value} not implemented",
            )

        log_id = self._log_and_return(
            conn, app_id, event, platform,
            pixel_id=config.pixel_id, payload=payload,
            success=result.success,
            status_code=result.status_code,
            body=result.response_body,
            error=result.error,
        )
        result.delivery_log_id = log_id
        return result

    # ── Retry worker ─────────────────────────────────────────────────────────

    async def retry_pending(self, conn: sqlite3.Connection) -> int:
        """
        Called by a scheduled task. Picks up failed rows whose
        next_retry_at has passed and retries them.
        Returns number of rows processed.
        """
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, app_id, platform, event_name, event_id, event_source,
                   source_ref_id, payload_json, attempts
              FROM capi_delivery_log
             WHERE succeeded = 0
               AND next_retry_at IS NOT NULL
               AND next_retry_at <= CURRENT_TIMESTAMP
             ORDER BY next_retry_at ASC
             LIMIT 100
        """)
        rows = cur.fetchall()
        processed = 0

        for row in rows:
            try:
                config = self.get_config(row["app_id"], CAPIPlatform(row["platform"]))
                if config is None:
                    self._mark_permanent_failure(conn, row["id"], "no config")
                    continue

                payload_dict = json.loads(row["payload_json"])
                # We re-send the pre-built payload directly
                url = f"https://graph.facebook.com/{config.api_version}/{config.pixel_id}/events"
                params = {"access_token": config.access_token}
                try:
                    resp = await self._facebook._client.post(url, params=params, json=payload_dict)
                    success = 200 <= resp.status_code < 300
                    self._update_retry(
                        conn, row["id"],
                        success=success,
                        status_code=resp.status_code,
                        body=resp.text[:2000],
                        attempts=row["attempts"] + 1,
                        error=None if success else f"http {resp.status_code}",
                    )
                except Exception as exc:
                    self._update_retry(
                        conn, row["id"],
                        success=False,
                        status_code=None,
                        body="",
                        attempts=row["attempts"] + 1,
                        error=f"transport: {exc}",
                    )
                processed += 1
            except Exception as exc:
                logger.exception("CAPI retry row %d failed: %s", row["id"], exc)

        return processed

    # ── Persistence helpers ──────────────────────────────────────────────────

    @staticmethod
    def _find_successful_delivery(
        conn:     sqlite3.Connection,
        app_id:   str,
        platform: CAPIPlatform,
        event_id: str,
    ) -> Optional[int]:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id FROM capi_delivery_log
             WHERE app_id = ? AND platform = ? AND event_id = ? AND succeeded = 1
             LIMIT 1
            """,
            (app_id, platform.value, event_id),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None

    @staticmethod
    def _log_and_return(
        conn:        sqlite3.Connection,
        app_id:      str,
        event:       CAPIEventData,
        platform:    CAPIPlatform,
        pixel_id:    str,
        payload:     Dict[str, Any],
        success:     bool,
        status_code: Optional[int],
        body:        str,
        error:       Optional[str],
    ) -> int:
        next_retry: Optional[str] = None
        if not success:
            next_retry = (datetime.utcnow() + timedelta(seconds=_RETRY_SCHEDULE[0])).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO capi_delivery_log (
                app_id, platform, event_name, event_id, event_source,
                source_ref_id, pixel_id, payload_json,
                response_code, response_body,
                attempts, succeeded, last_error, next_retry_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                app_id, platform.value, event.event_name, event.event_id,
                event.source, event.source_ref_id, pixel_id,
                json.dumps(payload),
                status_code, body,
                1, 1 if success else 0, error, next_retry,
            ),
        )
        conn.commit()
        return cur.lastrowid

    @staticmethod
    def _update_retry(
        conn:        sqlite3.Connection,
        row_id:      int,
        success:     bool,
        status_code: Optional[int],
        body:        str,
        attempts:    int,
        error:       Optional[str],
    ) -> None:
        next_retry: Optional[str] = None
        if not success and attempts < _MAX_ATTEMPTS:
            delay = _RETRY_SCHEDULE[min(attempts - 1, len(_RETRY_SCHEDULE) - 1)]
            next_retry = (datetime.utcnow() + timedelta(seconds=delay)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        cur = conn.cursor()
        cur.execute(
            """
            UPDATE capi_delivery_log
               SET succeeded       = ?,
                   response_code   = ?,
                   response_body   = ?,
                   attempts        = ?,
                   last_error      = ?,
                   last_attempt_at = CURRENT_TIMESTAMP,
                   next_retry_at   = ?
             WHERE id = ?
            """,
            (
                1 if success else 0,
                status_code,
                body,
                attempts,
                error,
                next_retry,
                row_id,
            ),
        )
        conn.commit()

    @staticmethod
    def _mark_permanent_failure(
        conn: sqlite3.Connection, row_id: int, reason: str
    ) -> None:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE capi_delivery_log
               SET next_retry_at = NULL,
                   last_error    = ?
             WHERE id = ?
            """,
            (reason, row_id),
        )
        conn.commit()


# Module singleton
capi_service = CAPIService()
