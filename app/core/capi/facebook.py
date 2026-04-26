"""
Facebook Conversions API client.

Docs: https://developers.facebook.com/docs/marketing-api/conversions-api

Endpoint:
    POST https://graph.facebook.com/{api_version}/{pixel_id}/events
        ?access_token=...

Payload shape:
    {
      "data": [
        {
          "event_name":    "Purchase",
          "event_time":    1700000000,
          "event_id":      "uuid-for-dedup",
          "action_source": "app",
          "user_data":     { ... },
          "custom_data":   { "value": 9.99, "currency": "USD", ... }
        }
      ],
      "test_event_code": "TEST12345"    // optional, for dashboard verification
    }
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import httpx

from .models import CAPIConfig, CAPIDeliveryResult, CAPIEventData, CAPIUserData

logger = logging.getLogger(__name__)

FB_GRAPH_BASE = "https://graph.facebook.com"


class FacebookCAPIClient:
    """
    Stateless client. Construct once; call send(...) per event (or batch).
    Uses an httpx.AsyncClient with connection pooling.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_connections: int   = 20,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=max_connections),
        )

    async def close(self) -> None:
        await self._client.aclose()

    # ── Send ─────────────────────────────────────────────────────────────────

    async def send(
        self,
        config: CAPIConfig,
        event:  CAPIEventData,
    ) -> CAPIDeliveryResult:
        """Send a single event. Batching is handled upstream if needed."""
        url = f"{FB_GRAPH_BASE}/{config.api_version}/{config.pixel_id}/events"

        payload = self._build_payload(event, test_event_code=config.test_event_code)
        params  = {"access_token": config.access_token}

        try:
            resp = await self._client.post(url, params=params, json=payload)
        except Exception as exc:
            logger.warning("Facebook CAPI transport error: %s", exc)
            return CAPIDeliveryResult(
                success=False,
                status_code=None,
                response_body="",
                error=f"transport: {exc}",
            )

        body = resp.text[:2000]  # cap — avoid huge logs on unusual errors
        success = 200 <= resp.status_code < 300

        if not success:
            logger.info(
                "Facebook CAPI non-2xx (%d) for event %s: %s",
                resp.status_code, event.event_name, body,
            )

        return CAPIDeliveryResult(
            success     = success,
            status_code = resp.status_code,
            response_body = body,
            error       = None if success else f"http {resp.status_code}",
        )

    # ── Payload construction ─────────────────────────────────────────────────

    def _build_payload(
        self,
        event: CAPIEventData,
        *,
        test_event_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Facebook requires certain user_data fields to be SHA-256 hashed
        (em, ph, external_id). Client IP and UA are NOT hashed.
        Hashing is idempotent — a value that already looks like a 64-char
        hex digest is left alone.
        """
        user_data = self._hash_user_data(event.user_data)

        fb_event: Dict[str, Any] = {
            "event_name":    event.event_name,
            "event_time":    event.event_time,
            "event_id":      event.event_id,
            "action_source": event.action_source,
            "user_data":     user_data,
        }

        if event.event_source_url:
            fb_event["event_source_url"] = event.event_source_url

        custom_data: Dict[str, Any] = dict(event.custom_data)
        if event.value is not None:
            custom_data["value"] = event.value
        if event.currency:
            custom_data["currency"] = event.currency
        if custom_data:
            fb_event["custom_data"] = custom_data

        payload: Dict[str, Any] = {"data": [fb_event]}
        if test_event_code:
            payload["test_event_code"] = test_event_code

        return payload

    @staticmethod
    def _hash_user_data(ud: CAPIUserData) -> Dict[str, Any]:
        """
        Lower-case + SHA-256 for PII fields, per Facebook CAPI spec.
        Skipped for already-hashed values (64 hex chars).
        """
        def _hash(v: Optional[str]) -> Optional[str]:
            if v is None:
                return None
            v = v.strip().lower()
            if not v:
                return None
            if len(v) == 64 and all(c in "0123456789abcdef" for c in v):
                return v
            return hashlib.sha256(v.encode("utf-8")).hexdigest()

        out: Dict[str, Any] = {}
        # Plain fields (not hashed)
        if ud.client_ip_address: out["client_ip_address"] = ud.client_ip_address
        if ud.client_user_agent: out["client_user_agent"] = ud.client_user_agent
        if ud.fbp:               out["fbp"] = ud.fbp
        if ud.fbc:               out["fbc"] = ud.fbc
        # Hashed fields
        if ud.em:          out["em"]          = _hash(ud.em)
        if ud.ph:          out["ph"]          = _hash(ud.ph)
        if ud.external_id: out["external_id"] = _hash(ud.external_id)
        return out
