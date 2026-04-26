"""
Data types for the SKAdNetwork module.

All dataclasses here are pure data — no side effects, no I/O. The service
layer (`service.py`) is responsible for persistence and orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional


# ── Enums ──────────────────────────────────────────────────────────────────────

class CoarseValue(str, Enum):
    """SKAN 4.0 coarse conversion value (PB1/PB2/PB3)."""
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class FidelityType(IntEnum):
    """Apple `fidelity-type` field — how the impression was served."""
    VIEW_THROUGH  = 0  # StoreKit-rendered ad view
    CLICK_THROUGH = 1  # explicit tap on the ad


class PostbackSequence(IntEnum):
    """
    SKAN 4 multi-postback windows:
        0 → PB1, days 0–2  (fine CV available)
        1 → PB2, days 3–7  (coarse only)
        2 → PB3, days 8–35 (coarse only)
    """
    PB1 = 0
    PB2 = 1
    PB3 = 2


# ── CV encoding / decoding ────────────────────────────────────────────────────

@dataclass(frozen=True)
class CVComponents:
    """Decomposed fine conversion-value (0..63)."""

    revenue_bucket: int   # 0..7  (3 bits)
    engagement:    int    # 0..3  (2 bits)
    event_flag:    int    # 0..1  (1 bit)

    def __post_init__(self) -> None:
        if not 0 <= self.revenue_bucket <= 7:
            raise ValueError(f"revenue_bucket out of range: {self.revenue_bucket}")
        if not 0 <= self.engagement <= 3:
            raise ValueError(f"engagement out of range: {self.engagement}")
        if not 0 <= self.event_flag <= 1:
            raise ValueError(f"event_flag out of range: {self.event_flag}")


@dataclass(frozen=True)
class DecodedCV:
    """Human-readable form of a CV; returned from decode_cv()."""

    raw_cv:             int
    revenue_bucket:     int
    revenue_usd_min:    float
    revenue_usd_max:    Optional[float]  # None = open-ended (whale tier)
    engagement_tier:    str              # "bounce" | "active" | "deep" | "power"
    is_conversion:      bool             # event_flag == 1


# ── Postback data ─────────────────────────────────────────────────────────────

@dataclass
class SKANPostback:
    """Parsed Apple postback (SKAN 2, 3 or 4)."""

    version:                 str                      # "4.0"
    ad_network_id:           str
    transaction_id:          str                      # unique per postback
    postback_sequence_index: PostbackSequence
    app_id:                  Optional[str] = None
    source_identifier:       Optional[str] = None     # SKAN 4+ (4-digit string)
    campaign_id:             Optional[int] = None     # legacy SKAN 2/3 (0-99)
    source_app_id:           Optional[str] = None
    source_domain:           Optional[str] = None
    redownload:              bool = False
    fidelity_type:           Optional[FidelityType] = None
    conversion_value:        Optional[int] = None     # 0..63
    coarse_conversion_value: Optional[CoarseValue] = None
    did_win:                 Optional[bool] = None
    attribution_signature:   Optional[str] = None
    raw_json:                Dict[str, Any] = field(default_factory=dict)
    signature_verified:      int = 0                  # 0=not checked, 1=ok, 2=failed

    @property
    def is_pb1(self) -> bool:
        return self.postback_sequence_index == PostbackSequence.PB1

    @property
    def campaign_key(self) -> str:
        """
        Canonical campaign key — tries SKAN 4 source_identifier first,
        falls back to legacy campaign_id. Used by CampaignDecoder lookup.
        """
        if self.source_identifier:
            return self.source_identifier
        if self.campaign_id is not None:
            return str(self.campaign_id)
        return ""


# ── CV schema configuration ───────────────────────────────────────────────────

@dataclass
class SKANConfig:
    """
    Per-app CV encoding parameters. Delivered to SDK via GET /skan/config
    and cached client-side. Changing values here does NOT change the schema
    layout — only thresholds and bucket edges.
    """

    app_id:                   str
    schema_version:           int = 1
    schema_name:              str = "rev3_eng2_flag1"

    # Revenue buckets — 8 ascending USD thresholds (index == bucket code).
    # Bucket N means revenue in [thresholds[N], thresholds[N+1]).
    # thresholds[7] is the "open-ended" floor (whale tier).
    revenue_buckets_usd:      List[float] = field(
        default_factory=lambda: [0.0, 0.01, 1.0, 5.0, 20.0, 50.0, 100.0, 300.0]
    )

    # Engagement thresholds
    bounce_max_seconds:       int = 30
    active_min_sessions:      int = 2
    deep_min_sessions:        int = 5
    deep_min_core_actions:    int = 1
    power_requires_retention: bool = True

    conversion_window_hours:  int = 48
    cache_ttl_seconds:        int = 86400


# ── Campaign decoder ──────────────────────────────────────────────────────────

@dataclass
class DecoderRule:
    """
    One rule inside a CampaignDecoder. Matches an inclusive CV range
    and emits a CAPI event with optional dynamic value computation.
    """

    cv_min:            int                          # inclusive 0..63
    cv_max:            int                          # inclusive 0..63
    capi_event:        str                          # e.g. "Purchase", "Lead"
    forward:           bool = True                  # false = silence this range
    static_value:      Optional[float] = None       # fixed CAPI value, USD
    value_multiplier:  float = 1.0                  # × midpoint(revenue_bucket)
    currency:          str = "USD"
    description:       str = ""

    def matches(self, cv: int) -> bool:
        return self.cv_min <= cv <= self.cv_max

    def __post_init__(self) -> None:
        if not 0 <= self.cv_min <= 63:
            raise ValueError(f"cv_min out of range: {self.cv_min}")
        if not 0 <= self.cv_max <= 63:
            raise ValueError(f"cv_max out of range: {self.cv_max}")
        if self.cv_min > self.cv_max:
            raise ValueError(f"cv_min > cv_max: {self.cv_min} > {self.cv_max}")
