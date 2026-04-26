"""
6-bit Conversion Value encoding.

Layout (schema "rev3_eng2_flag1"):
    bit 5  4  3 │ 2  1 │ 0
    └─revenue─┘ └─eng─┘ flag

    revenue_bucket ∈ [0..7]  (3 bits, 8 log-scale USD buckets)
    engagement     ∈ [0..3]  (2 bits, bounce/active/deep/power)
    event_flag     ∈ [0..1]  (1 bit,  1 = real conversion event happened)

Why this layout:
  • Revenue occupies the most-significant bits so that coarse bucketing
    (low/med/high) from PB2/PB3 correlates with revenue tiers naturally.
  • Engagement is independent of revenue — FB can train on either axis.
  • event_flag separates "engaged but non-paying" from "paid but shallow".

Schema stability:
  The bit layout is part of the wire contract between SDK and backend.
  Changing it requires a new schema_name, kept forever for legacy devices.
"""

from __future__ import annotations

from typing import List, Sequence

from .models import CVComponents, DecodedCV, SKANConfig


# ── Defaults exposed to SDK ───────────────────────────────────────────────────

DEFAULT_REVENUE_BUCKETS: List[float] = [
    0.0,     # bucket 0: exactly $0 (free user)
    0.01,    # bucket 1: $0.01 – $0.99   (micro / ads)
    1.0,     # bucket 2: $1.00 – $4.99   (low)
    5.0,     # bucket 3: $5.00 – $19.99  (standard)
    20.0,    # bucket 4: $20.00 – $49.99 (mid / trial→sub)
    50.0,    # bucket 5: $50.00 – $99.99 (high)
    100.0,   # bucket 6: $100 – $299.99  (whale-track)
    300.0,   # bucket 7: $300+           (whale)
]

DEFAULT_ENGAGEMENT_THRESHOLDS = {
    "bounce_max_seconds":       30,
    "active_min_sessions":      2,
    "deep_min_sessions":        5,
    "deep_min_core_actions":    1,
    "power_requires_retention": True,
}

ENGAGEMENT_TIER_NAMES = ("bounce", "active", "deep", "power")


# ── Pure bit-packing ──────────────────────────────────────────────────────────

def encode_cv(components: CVComponents) -> int:
    """Pack (revenue, engagement, flag) → single int 0..63."""
    return (components.revenue_bucket << 3) | (components.engagement << 1) | components.event_flag


def decode_cv_bits(cv: int) -> CVComponents:
    """Unpack int 0..63 → (revenue, engagement, flag)."""
    if not 0 <= cv <= 63:
        raise ValueError(f"cv out of range: {cv}")
    return CVComponents(
        revenue_bucket=(cv >> 3) & 0b111,
        engagement   =(cv >> 1) & 0b11,
        event_flag   = cv       & 0b1,
    )


# ── High-level encoding API (used by server-side simulation and by SDK port) ──

class CVSchema:
    """
    Stateless encoder/decoder bound to a SKANConfig.

    The SDK ports (iOS/Android) implement the same logic in Swift/Kotlin,
    deriving the thresholds from the runtime config. Keeping the reference
    implementation here lets us simulate CV values and test the decoder
    without the SDK in the loop.
    """

    __slots__ = ("config",)

    def __init__(self, config: SKANConfig) -> None:
        self.config = config

    # --- Revenue -------------------------------------------------------------

    def revenue_bucket(self, usd: float) -> int:
        """Map USD amount to bucket 0..7."""
        if usd <= 0:
            return 0
        buckets = self.config.revenue_buckets_usd
        # find highest bucket whose floor ≤ usd
        chosen = 0
        for i, floor in enumerate(buckets):
            if usd >= floor:
                chosen = i
            else:
                break
        return chosen

    def revenue_range(self, bucket: int) -> tuple[float, float | None]:
        """Return (min_usd, max_usd_exclusive) for a bucket. None = open-ended."""
        buckets = self.config.revenue_buckets_usd
        if bucket < 0 or bucket >= len(buckets):
            raise ValueError(f"bucket out of range: {bucket}")
        lo = buckets[bucket]
        hi: float | None = buckets[bucket + 1] if bucket + 1 < len(buckets) else None
        return (lo, hi)

    def revenue_midpoint(self, bucket: int) -> float:
        """
        Representative USD value for a bucket — used when forwarding to CAPI.
        For open-ended whale bucket we return 2× the floor as a conservative proxy.
        """
        lo, hi = self.revenue_range(bucket)
        if hi is None:
            return lo * 2.0 if lo > 0 else 0.0
        return (lo + hi) / 2.0

    # --- Engagement ----------------------------------------------------------

    def engagement_tier(
        self,
        sessions:          int,
        total_seconds:     float,
        core_actions:      int,
        returned_next_day: bool,
        retained_day_two:  bool,
    ) -> int:
        """
        Compute engagement tier 0..3 from raw metrics.

          0 (bounce) — single short session
          1 (active) — multiple sessions OR enough time spent
          2 (deep)   — many sessions OR core action completed
          3 (power)  — retention d1+d2 AND core action
        """
        c = self.config

        if c.power_requires_retention and returned_next_day and retained_day_two and core_actions >= c.deep_min_core_actions:
            return 3

        if sessions >= c.deep_min_sessions or core_actions >= c.deep_min_core_actions:
            return 2

        if sessions >= c.active_min_sessions or total_seconds >= c.bounce_max_seconds * 4:
            return 1

        return 0

    # --- Compose -------------------------------------------------------------

    def compute_cv(
        self,
        revenue_usd:       float,
        sessions:          int,
        total_seconds:     float,
        core_actions:      int,
        returned_next_day: bool,
        retained_day_two:  bool,
        is_conversion:     bool,
    ) -> int:
        """High-level entry point — takes raw metrics, returns fine CV 0..63."""
        comp = CVComponents(
            revenue_bucket=self.revenue_bucket(revenue_usd),
            engagement   =self.engagement_tier(
                sessions=sessions,
                total_seconds=total_seconds,
                core_actions=core_actions,
                returned_next_day=returned_next_day,
                retained_day_two=retained_day_two,
            ),
            event_flag   =1 if is_conversion else 0,
        )
        return encode_cv(comp)

    # --- Decode back to human-readable ---------------------------------------

    def decode(self, cv: int) -> DecodedCV:
        comp = decode_cv_bits(cv)
        lo, hi = self.revenue_range(comp.revenue_bucket)
        return DecodedCV(
            raw_cv         = cv,
            revenue_bucket = comp.revenue_bucket,
            revenue_usd_min= lo,
            revenue_usd_max= hi,
            engagement_tier= ENGAGEMENT_TIER_NAMES[comp.engagement],
            is_conversion  = bool(comp.event_flag),
        )


# ── Module-level convenience functions ────────────────────────────────────────

def decode_cv(cv: int, config: SKANConfig | None = None) -> DecodedCV:
    """Decode a CV using either a provided config or the default schema."""
    cfg = config or SKANConfig(app_id="__default__")
    return CVSchema(cfg).decode(cv)
