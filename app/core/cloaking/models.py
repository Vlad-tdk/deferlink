"""
Cloaking models — all data types used across the cloaking subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ── Visitor classification ────────────────────────────────────────────────────

class VisitorType(str, Enum):
    REAL_USER   = "real_user"    # genuine human — show full flow
    BOT         = "bot"          # search / social crawler — show SEO page
    AD_REVIEW   = "ad_review"    # ad network reviewer — show compliant page
    SUSPICIOUS  = "suspicious"   # inconclusive signals — configurable action


class CloakingAction(str, Enum):
    FULL_FLOW       = "full_flow"       # normal DeferLink deep-link flow
    SEO_PAGE        = "seo_page"        # OG/meta-tags landing for crawlers
    COMPLIANT_PAGE  = "compliant_page"  # ad-review-safe landing
    BLOCK           = "block"           # 403 / empty response
    SUSPICIOUS_FLOW = "suspicious_flow" # same as full_flow but logged


# ── Individual signal ─────────────────────────────────────────────────────────

@dataclass
class DetectionSignal:
    """A single piece of evidence contributing to the final decision."""
    source:      str            # "ip_cidr" | "ip_asn" | "ua_regex" | "behavior"
    description: str            # human-readable explanation
    visitor_type: VisitorType
    confidence:  float          # 0.0 – 1.0
    matched_value: str = ""     # what exactly triggered this signal


# ── Final decision ────────────────────────────────────────────────────────────

@dataclass
class CloakingDecision:
    visitor_type: VisitorType
    action:       CloakingAction
    confidence:   float                       # 0.0 – 1.0, aggregated
    signals:      List[DetectionSignal] = field(default_factory=list)
    ip:           Optional[str] = None
    user_agent:   Optional[str] = None

    @property
    def is_bot(self) -> bool:
        return self.visitor_type in (VisitorType.BOT, VisitorType.AD_REVIEW)

    def top_signal(self) -> Optional[DetectionSignal]:
        return max(self.signals, key=lambda s: s.confidence, default=None)

    def summary(self) -> str:
        top = self.top_signal()
        reason = top.description if top else "no signals"
        return (
            f"visitor={self.visitor_type.value} "
            f"action={self.action.value} "
            f"confidence={self.confidence:.2f} "
            f"reason='{reason}'"
        )


# ── Rule records (mirroring DB rows) ─────────────────────────────────────────

@dataclass
class IPRule:
    id:           int
    cidr:         Optional[str]    # "31.13.24.0/21"
    ip_exact:     Optional[str]    # "1.2.3.4"
    asn:          Optional[int]    # 32934
    visitor_type: VisitorType
    confidence:   float
    description:  str
    enabled:      bool


@dataclass
class UARuleRecord:
    id:           int
    pattern:      str              # regex pattern
    visitor_type: VisitorType
    confidence:   float
    description:  str
    enabled:      bool
