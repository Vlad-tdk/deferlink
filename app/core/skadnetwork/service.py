"""
High-level SKAdNetwork service — orchestrates persistence, decoding,
and CAPI forwarding.

Module-level singleton `skan_service`. Call `skan_service.load_rules()`
after DB changes to hot-reload decoders and configs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .campaign_decoder import CampaignDecoder, CAPIEventInstruction
from .cv_schema import CVSchema
from .models import SKANConfig, SKANPostback
from .postback_parser import PostbackParser

logger = logging.getLogger(__name__)


class SKANService:
    """Thread-safe; safe as module-level singleton."""

    def __init__(self, *, verify_signatures: bool = True) -> None:
        self._parser  = PostbackParser(verify_signature=verify_signatures)
        self._decoder = CampaignDecoder()
        self._cv_configs: Dict[str, SKANConfig] = {}   # app_id → config

    # ── Hot-reload ───────────────────────────────────────────────────────────

    def load_rules(self, conn: sqlite3.Connection) -> None:
        """Reload both decoders and CV configs from the database."""
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # --- Decoders ---
        cur.execute("""
            SELECT id, source_identifier, campaign_id, app_id,
                   decoder_json, enabled
            FROM skan_campaign_decoders
        """)
        decoder_rows = [dict(r) for r in cur.fetchall()]
        self._decoder.load(decoder_rows)

        # --- CV configs per app ---
        cur.execute("""
            SELECT app_id, schema_version, schema_name,
                   revenue_buckets_json,
                   bounce_max_seconds, active_min_sessions,
                   deep_min_sessions, deep_min_core_actions,
                   power_requires_retention,
                   conversion_window_hours, cache_ttl_seconds
            FROM skan_cv_configs
        """)
        configs: Dict[str, SKANConfig] = {}
        for r in cur.fetchall():
            try:
                buckets = json.loads(r["revenue_buckets_json"])
            except Exception:
                from .cv_schema import DEFAULT_REVENUE_BUCKETS
                buckets = DEFAULT_REVENUE_BUCKETS
            configs[r["app_id"]] = SKANConfig(
                app_id                  = r["app_id"],
                schema_version          = r["schema_version"],
                schema_name             = r["schema_name"],
                revenue_buckets_usd     = buckets,
                bounce_max_seconds      = r["bounce_max_seconds"],
                active_min_sessions     = r["active_min_sessions"],
                deep_min_sessions       = r["deep_min_sessions"],
                deep_min_core_actions   = r["deep_min_core_actions"],
                power_requires_retention= bool(r["power_requires_retention"]),
                conversion_window_hours = r["conversion_window_hours"],
                cache_ttl_seconds       = r["cache_ttl_seconds"],
            )
        self._cv_configs = configs

        logger.info(
            "SKANService: loaded %d decoders, %d CV configs",
            len(decoder_rows), len(configs),
        )

    # ── Config access ────────────────────────────────────────────────────────

    def get_config(self, app_id: str) -> SKANConfig:
        """Return per-app config or a default if unset."""
        return self._cv_configs.get(app_id) or SKANConfig(app_id=app_id)

    def schema_for(self, app_id: str) -> CVSchema:
        return CVSchema(self.get_config(app_id))

    # ── Postback ingestion ───────────────────────────────────────────────────

    def ingest_postback(
        self,
        payload:     Dict[str, Any],
        conn:        sqlite3.Connection,
    ) -> Tuple[SKANPostback, int, Optional[CAPIEventInstruction]]:
        """
        Parse, persist and decode one Apple postback.

        Returns:
            (parsed_postback, db_row_id, capi_instruction_or_none)
        """
        pb = self._parser.parse(payload)
        row_id = self._persist(pb, conn)
        self._update_distribution(pb, conn)

        instruction: Optional[CAPIEventInstruction] = None
        if pb.app_id:
            schema = self.schema_for(pb.app_id)
            instruction = self._decoder.decode(pb, schema=schema)

        return pb, row_id, instruction

    # ── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _persist(pb: SKANPostback, conn: sqlite3.Connection) -> int:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO skan_postbacks (
                    version, ad_network_id, source_identifier, campaign_id,
                    transaction_id, app_id, source_app_id, source_domain,
                    redownload, fidelity_type,
                    conversion_value, coarse_conversion_value,
                    postback_sequence_index, did_win,
                    attribution_signature, signature_verified, raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    pb.version,
                    pb.ad_network_id,
                    pb.source_identifier,
                    pb.campaign_id,
                    pb.transaction_id,
                    pb.app_id,
                    pb.source_app_id,
                    pb.source_domain,
                    1 if pb.redownload else 0,
                    int(pb.fidelity_type) if pb.fidelity_type is not None else None,
                    pb.conversion_value,
                    pb.coarse_conversion_value.value if pb.coarse_conversion_value else None,
                    int(pb.postback_sequence_index),
                    (1 if pb.did_win else 0) if pb.did_win is not None else None,
                    pb.attribution_signature,
                    pb.signature_verified,
                    json.dumps(pb.raw_json),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate transaction_id — return existing row id
            conn.rollback()
            cur.execute(
                "SELECT id FROM skan_postbacks WHERE transaction_id = ?",
                (pb.transaction_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else -1

    @staticmethod
    def _update_distribution(pb: SKANPostback, conn: sqlite3.Connection) -> None:
        """Update aggregated CV-distribution stats (skan_cv_distribution)."""
        if pb.conversion_value is None or not pb.app_id:
            return

        today = datetime.utcnow().strftime("%Y-%m-%d")
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO skan_cv_distribution
                    (date, app_id, source_identifier, campaign_id,
                     conversion_value, postback_count)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(date, app_id, source_identifier,
                            campaign_id, conversion_value)
                DO UPDATE SET postback_count = postback_count + 1
                """,
                (
                    today,
                    pb.app_id,
                    pb.source_identifier,
                    pb.campaign_id,
                    pb.conversion_value,
                ),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("SKAN distribution update failed: %s", exc)
            conn.rollback()

    # ── Forwarding state ─────────────────────────────────────────────────────

    @staticmethod
    def mark_forwarded(
        conn:    sqlite3.Connection,
        row_id:  int,
        status:  int,              # 1 = ok, 2 = failed
        error:   Optional[str] = None,
    ) -> None:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE skan_postbacks
               SET capi_forwarded    = ?,
                   capi_forwarded_at = CURRENT_TIMESTAMP,
                   capi_last_error   = ?
             WHERE id = ?
            """,
            (status, error, row_id),
        )
        conn.commit()


# ── Module singleton ──────────────────────────────────────────────────────────

skan_service = SKANService()
