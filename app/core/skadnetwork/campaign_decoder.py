"""
Per-campaign decoder: (campaign, CV) → CAPI event instruction.

A decoder is an ordered list of rules. The first matching rule wins.
If no rule matches, the postback is silently ignored (do not forward).

Decoder is stored per campaign, keyed by either:
  • source_identifier (SKAN 4 4-digit string), or
  • campaign_id       (legacy SKAN 2/3 int 0-99)

CampaignDecoder is *in-memory* cache rebuilt on every admin change.
Persistence lives in `skan_campaign_decoders` table.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from .cv_schema import CVSchema
from .models import DecoderRule, SKANConfig, SKANPostback

logger = logging.getLogger(__name__)


@dataclass
class CAPIEventInstruction:
    """Output of decoding one postback — what to send to CAPI."""
    capi_event: str
    value:      Optional[float]
    currency:   str
    rule_description: str = ""


class CampaignDecoder:
    """
    Look up decoder rules by campaign_key (source_identifier or campaign_id),
    returning the CAPI event instruction for a given postback's CV.
    """

    __slots__ = ("_by_key", "_default_schema")

    def __init__(self) -> None:
        # (app_id, campaign_key) → ordered list of rules
        self._by_key: Dict[tuple[str, str], List[DecoderRule]] = {}
        # Fallback schema used when decoder needs to compute revenue midpoint
        self._default_schema = CVSchema(SKANConfig(app_id="__default__"))

    # ── Rule management ──────────────────────────────────────────────────────

    def load(self, rows: List[Dict]) -> None:
        """
        Replace all rules from DB rows.

        Each row must contain 'source_identifier' or 'campaign_id' plus
        'decoder_json' (a JSON list of rules). Disabled rows are skipped.
        """
        new_map: Dict[tuple[str, str], List[DecoderRule]] = {}
        for row in rows:
            if not row.get("enabled"):
                continue

            campaign_key = row.get("source_identifier") or (
                str(row["campaign_id"]) if row.get("campaign_id") is not None else None
            )
            app_id = row.get("app_id")
            if not app_id or not campaign_key:
                continue

            try:
                rules_data = json.loads(row["decoder_json"])
                rules = [DecoderRule(**r) for r in rules_data]
                new_map[(str(app_id), str(campaign_key))] = rules
            except Exception as exc:
                logger.warning(
                    "CampaignDecoder: skipping bad decoder for %s/%s: %s",
                    app_id, campaign_key, exc,
                )

        self._by_key = new_map
        logger.info("CampaignDecoder: loaded %d decoders", len(new_map))

    def has_campaign(self, app_id: str, campaign_key: str) -> bool:
        return (app_id, campaign_key) in self._by_key

    # ── Decoding ─────────────────────────────────────────────────────────────

    def decode(
        self,
        pb: SKANPostback,
        schema: Optional[CVSchema] = None,
    ) -> Optional[CAPIEventInstruction]:
        """
        Produce a CAPI instruction for a postback.

        Returns None if no rule applies (postback not forwarded).

        For PB1 (fine CV available) — matches on conversion_value.
        For PB2/PB3 (coarse only) — maps coarse values to synthetic CV points:
            low    → cv=0
            medium → cv=31
            high   → cv=63
          and looks up the matching rule.
        """
        cv = self._resolve_cv(pb)
        if cv is None:
            return None

        campaign_key = pb.campaign_key
        if not pb.app_id or not campaign_key:
            return None

        rules = self._by_key.get((pb.app_id, campaign_key))
        if not rules:
            return None

        for rule in rules:
            if rule.matches(cv):
                if not rule.forward:
                    return None

                value = self._compute_value(cv, rule, schema)
                return CAPIEventInstruction(
                    capi_event      = rule.capi_event,
                    value           = value,
                    currency        = rule.currency,
                    rule_description= rule.description,
                )

        return None

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_cv(pb: SKANPostback) -> Optional[int]:
        if pb.conversion_value is not None:
            return pb.conversion_value
        if pb.coarse_conversion_value is None:
            return None
        # Map coarse → synthetic fine CV for rule matching
        from .models import CoarseValue
        return {
            CoarseValue.LOW:    0,
            CoarseValue.MEDIUM: 31,
            CoarseValue.HIGH:   63,
        }.get(pb.coarse_conversion_value)

    def _compute_value(
        self,
        cv: int,
        rule: DecoderRule,
        schema: Optional[CVSchema],
    ) -> Optional[float]:
        if rule.static_value is not None:
            return rule.static_value

        # Dynamic: derive revenue midpoint from the CV's revenue bucket
        s = schema or self._default_schema
        decoded = s.decode(cv)
        mid = s.revenue_midpoint(decoded.revenue_bucket)
        return round(mid * rule.value_multiplier, 2) if mid else None
