"""
CloakingEngine — orchestrates all detectors and produces a CloakingDecision.

Scoring model
─────────────
Each detector returns a list of DetectionSignal objects with confidence 0–1.
The engine aggregates them into a single score using the following rules:

  1. Any SINGLE signal with confidence ≥ HARD_THRESHOLD (0.90) is enough to
     classify the visitor as that type immediately (e.g. Googlebot UA = 0.99).

  2. Otherwise, scores are combined via Bayesian-style accumulation:
       combined = 1 − ∏(1 − cᵢ)  for all signals of the same visitor_type
     This prevents any single weak signal from dominating.

  3. If combined ≥ SOFT_THRESHOLD (0.65) → classified.

  4. Behavioral signals alone can only push to "suspicious", never to "bot"
     or "ad_review" — those require at least one IP or UA signal.

  5. Default: REAL_USER with confidence = 1 − highest_suspicious_score.

Action mapping (configurable via CloakingConfig):
  bot        → SEO_PAGE
  ad_review  → COMPLIANT_PAGE
  suspicious → SUSPICIOUS_FLOW  (logs, but doesn't block)
  real_user  → FULL_FLOW
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .behavior_detector import BehaviorDetector
from .ip_detector import IPDetector
from .models import (
    CloakingAction,
    CloakingDecision,
    DetectionSignal,
    IPRule,
    UARuleRecord,
    VisitorType,
)
from .ua_detector import UADetector

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

HARD_THRESHOLD  = 0.88   # single signal sufficient for classification
SOFT_THRESHOLD  = 0.65   # combined score needed for classification
BOT_SUSPICION_BOOST = 0.15  # behavioral signals add this to final confidence
                             # when IP or UA already fire

# When multiple visitor types exceed threshold, use this priority.
# ad_review is the most actionable; bot is next; suspicious is weakest.
_TYPE_PRIORITY = {
    VisitorType.AD_REVIEW:  3,
    VisitorType.BOT:        2,
    VisitorType.SUSPICIOUS: 1,
    VisitorType.REAL_USER:  0,
}


@dataclass
class CloakingConfig:
    """Maps visitor types to actions. Override per-deployment."""
    action_map: Dict[VisitorType, CloakingAction] = field(default_factory=lambda: {
        VisitorType.REAL_USER:  CloakingAction.FULL_FLOW,
        VisitorType.BOT:        CloakingAction.SEO_PAGE,
        VisitorType.AD_REVIEW:  CloakingAction.COMPLIANT_PAGE,
        VisitorType.SUSPICIOUS: CloakingAction.SUSPICIOUS_FLOW,
    })
    # Minimum confidence to act on "suspicious" classification (avoid false positives)
    suspicious_min_confidence: float = 0.70


class CloakingEngine:
    """
    Thread-safe; safe to use as a module-level singleton.
    Call reload_rules() whenever DB rules change.
    """

    def __init__(self, config: Optional[CloakingConfig] = None) -> None:
        self._config      = config or CloakingConfig()
        self._ip_detector = IPDetector()
        self._ua_detector = UADetector()
        self._bh_detector = BehaviorDetector()

    # ── Rule management ───────────────────────────────────────────────────────

    def reload_rules(
        self,
        ip_rules: List[IPRule],
        ua_rules: List[UARuleRecord],
    ) -> None:
        """Hot-reload custom rules from DB without restarting."""
        self._ip_detector.load_custom_rules(ip_rules)
        self._ua_detector.load_custom_rules(ua_rules)
        logger.info(
            "CloakingEngine: rules reloaded — %d IP, %d UA custom rules",
            len([r for r in ip_rules if r.enabled]),
            len([r for r in ua_rules if r.enabled]),
        )

    # ── Main decision ─────────────────────────────────────────────────────────

    def decide(
        self,
        ip:          str,
        user_agent:  str,
        headers:     Optional[Dict[str, str]] = None,
        cookies:     Optional[Dict[str, str]] = None,
        referer:     Optional[str] = None,
        asn:         Optional[int] = None,
    ) -> CloakingDecision:
        """
        Produce a CloakingDecision from all available signals.

        All parameters except ip and user_agent are optional — the engine
        degrades gracefully when header/cookie data is unavailable.
        """
        all_signals: List[DetectionSignal] = []

        # 1. IP signals
        ip_signals = self._ip_detector.detect(ip, asn=asn)
        all_signals.extend(ip_signals)

        # 2. UA signals
        ua_signals = self._ua_detector.detect(user_agent)
        all_signals.extend(ua_signals)

        # 3. Behavioral signals (only if header data provided)
        bh_signals: List[DetectionSignal] = []
        if headers is not None:
            bh_signals = self._bh_detector.detect(
                headers=headers,
                cookies=cookies or {},
                referer=referer,
            )
            all_signals.extend(bh_signals)

        # 4. Aggregate and classify
        visitor_type, confidence = self._classify(
            ip_signals=ip_signals,
            ua_signals=ua_signals,
            bh_signals=bh_signals,
        )

        # 5. Map to action
        action = self._resolve_action(visitor_type, confidence)

        decision = CloakingDecision(
            visitor_type=visitor_type,
            action=action,
            confidence=round(confidence, 4),
            signals=all_signals,
            ip=ip,
            user_agent=user_agent,
        )

        if decision.is_bot:
            logger.info("CloakingEngine: %s", decision.summary())
        else:
            logger.debug("CloakingEngine: %s", decision.summary())

        return decision

    # ── Classification logic ──────────────────────────────────────────────────

    def _classify(
        self,
        ip_signals: List[DetectionSignal],
        ua_signals: List[DetectionSignal],
        bh_signals: List[DetectionSignal],
    ) -> tuple[VisitorType, float]:

        # Separate behavioral from authoritative signals
        auth_signals = ip_signals + ua_signals  # IP and UA are authoritative

        if not auth_signals and not bh_signals:
            return VisitorType.REAL_USER, 0.0

        # --- Build per-type score map via Bayesian accumulation ---
        scores: Dict[VisitorType, float] = {}
        for sig in auth_signals:
            vt   = sig.visitor_type
            prev = scores.get(vt, 0.0)
            scores[vt] = 1.0 - (1.0 - prev) * (1.0 - sig.confidence)

        # --- Find all types that exceed HARD threshold ---
        hard_types = {
            vt: sc for vt, sc in scores.items() if sc >= HARD_THRESHOLD
        }
        if hard_types:
            # Among hard-threshold types, pick by priority then by score
            best_type = max(
                hard_types,
                key=lambda vt: (_TYPE_PRIORITY.get(vt, 0), hard_types[vt]),
            )
            boost = self._behavioral_boost(bh_signals)
            return best_type, min(1.0, hard_types[best_type] + boost)

        # --- Soft threshold ---
        soft_types = {
            vt: sc for vt, sc in scores.items() if sc >= SOFT_THRESHOLD
        }
        if soft_types:
            best_type = max(
                soft_types,
                key=lambda vt: (_TYPE_PRIORITY.get(vt, 0), soft_types[vt]),
            )
            boost = self._behavioral_boost(bh_signals)
            return best_type, min(1.0, soft_types[best_type] + boost)

        # --- Behavioral signals alone: cap at SUSPICIOUS ---
        if bh_signals:
            bh_score = self._combine_scores(bh_signals)
            if bh_score >= self._config.suspicious_min_confidence:
                return VisitorType.SUSPICIOUS, bh_score

        return VisitorType.REAL_USER, 0.0

    @staticmethod
    def _combine_scores(signals: List[DetectionSignal]) -> float:
        """Bayesian accumulation of confidence scores."""
        score = 0.0
        for s in signals:
            score = 1.0 - (1.0 - score) * (1.0 - s.confidence)
        return score

    @staticmethod
    def _behavioral_boost(bh_signals: List[DetectionSignal]) -> float:
        """
        Translate behavioral signal count to a small confidence boost.
        Capped at BOT_SUSPICION_BOOST so behavior can't flip a decision alone.
        """
        if not bh_signals:
            return 0.0
        raw = sum(s.confidence for s in bh_signals) / len(bh_signals)
        return min(BOT_SUSPICION_BOOST, raw * 0.3)

    def _resolve_action(
        self,
        visitor_type: VisitorType,
        confidence:   float,
    ) -> CloakingAction:
        if (
            visitor_type == VisitorType.SUSPICIOUS
            and confidence < self._config.suspicious_min_confidence
        ):
            return CloakingAction.FULL_FLOW

        return self._config.action_map.get(visitor_type, CloakingAction.FULL_FLOW)


# ── Module-level singleton ────────────────────────────────────────────────────

_engine: Optional[CloakingEngine] = None


def get_engine() -> CloakingEngine:
    global _engine
    if _engine is None:
        _engine = CloakingEngine()
    return _engine


def init_engine(config: Optional[CloakingConfig] = None) -> CloakingEngine:
    global _engine
    _engine = CloakingEngine(config=config)
    return _engine
