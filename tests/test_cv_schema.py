"""
Tests for the 6-bit CV schema.

The bit layout is part of the on-device wire contract — if any of these
tests break, the SDK port and backend will desync.
"""

from __future__ import annotations

import pytest

from app.core.skadnetwork.cv_schema import (
    CVSchema,
    DEFAULT_REVENUE_BUCKETS,
    decode_cv,
    decode_cv_bits,
    encode_cv,
)
from app.core.skadnetwork.models import CVComponents, SKANConfig


# ── Bit packing ──────────────────────────────────────────────────────────────

class TestBitPacking:
    def test_encode_zero(self):
        assert encode_cv(CVComponents(0, 0, 0)) == 0

    def test_encode_max(self):
        assert encode_cv(CVComponents(7, 3, 1)) == 63

    def test_encode_layout(self):
        # revenue=3 (011), engagement=3 (11), flag=1 → 0b011 11 1 == 31
        assert encode_cv(CVComponents(3, 3, 1)) == 0b011_11_1

    def test_encode_revenue_only(self):
        # revenue=5 → 0b101 00 0 == 40
        assert encode_cv(CVComponents(5, 0, 0)) == 0b101_00_0

    def test_round_trip_all_64(self):
        for cv in range(64):
            comp = decode_cv_bits(cv)
            assert encode_cv(comp) == cv

    def test_decode_out_of_range(self):
        with pytest.raises(ValueError):
            decode_cv_bits(64)
        with pytest.raises(ValueError):
            decode_cv_bits(-1)

    def test_components_validation(self):
        with pytest.raises(ValueError):
            CVComponents(8, 0, 0)
        with pytest.raises(ValueError):
            CVComponents(0, 4, 0)
        with pytest.raises(ValueError):
            CVComponents(0, 0, 2)


# ── Revenue bucket ───────────────────────────────────────────────────────────

class TestRevenueBucket:
    @pytest.fixture
    def schema(self):
        return CVSchema(SKANConfig(app_id="test"))

    def test_zero(self, schema):
        assert schema.revenue_bucket(0) == 0
        assert schema.revenue_bucket(-5) == 0

    def test_micro(self, schema):
        assert schema.revenue_bucket(0.50) == 1   # $0.01..$0.99 floor

    def test_low(self, schema):
        assert schema.revenue_bucket(2.99) == 2   # $1..$4.99

    def test_standard(self, schema):
        assert schema.revenue_bucket(9.99) == 3   # $5..$19.99

    def test_mid(self, schema):
        assert schema.revenue_bucket(35) == 4

    def test_whale_open_ended(self, schema):
        assert schema.revenue_bucket(10_000) == 7

    def test_boundary_inclusivity(self, schema):
        # Exactly on the floor → that bucket
        for i, floor in enumerate(DEFAULT_REVENUE_BUCKETS):
            if floor > 0:
                assert schema.revenue_bucket(floor) == i


# ── Engagement tier ──────────────────────────────────────────────────────────

class TestEngagement:
    @pytest.fixture
    def schema(self):
        return CVSchema(SKANConfig(app_id="test"))

    def test_bounce(self, schema):
        assert schema.engagement_tier(
            sessions=1, total_seconds=5, core_actions=0,
            returned_next_day=False, retained_day_two=False,
        ) == 0

    def test_active_by_sessions(self, schema):
        assert schema.engagement_tier(
            sessions=2, total_seconds=10, core_actions=0,
            returned_next_day=False, retained_day_two=False,
        ) == 1

    def test_active_by_time(self, schema):
        # bounce_max_seconds=30, threshold = 30*4 = 120
        assert schema.engagement_tier(
            sessions=1, total_seconds=150, core_actions=0,
            returned_next_day=False, retained_day_two=False,
        ) == 1

    def test_deep_by_sessions(self, schema):
        assert schema.engagement_tier(
            sessions=5, total_seconds=10, core_actions=0,
            returned_next_day=False, retained_day_two=False,
        ) == 2

    def test_deep_by_core_action(self, schema):
        assert schema.engagement_tier(
            sessions=1, total_seconds=10, core_actions=1,
            returned_next_day=False, retained_day_two=False,
        ) == 2

    def test_power_requires_retention(self, schema):
        # Has core action + retention → power
        assert schema.engagement_tier(
            sessions=2, total_seconds=10, core_actions=1,
            returned_next_day=True, retained_day_two=True,
        ) == 3
        # Core action but no retention → only deep
        assert schema.engagement_tier(
            sessions=2, total_seconds=10, core_actions=1,
            returned_next_day=True, retained_day_two=False,
        ) == 2


# ── Compose ──────────────────────────────────────────────────────────────────

class TestComposeCV:
    def test_paid_whale_with_power(self):
        cv = CVSchema(SKANConfig(app_id="x")).compute_cv(
            revenue_usd=500, sessions=8, total_seconds=600, core_actions=3,
            returned_next_day=True, retained_day_two=True, is_conversion=True,
        )
        # whale=7, power=3, flag=1 → encode(7,3,1)=63
        assert cv == 63

    def test_free_bounce_no_event(self):
        cv = CVSchema(SKANConfig(app_id="x")).compute_cv(
            revenue_usd=0, sessions=1, total_seconds=5, core_actions=0,
            returned_next_day=False, retained_day_two=False, is_conversion=False,
        )
        assert cv == 0

    def test_engaged_free_user(self):
        # active engagement, no revenue, no purchase
        cv = CVSchema(SKANConfig(app_id="x")).compute_cv(
            revenue_usd=0, sessions=3, total_seconds=200, core_actions=0,
            returned_next_day=False, retained_day_two=False, is_conversion=False,
        )
        # encode(0, 1, 0) = 2
        assert cv == 2


# ── Decode for humans ────────────────────────────────────────────────────────

class TestDecode:
    def test_decode_max(self):
        d = decode_cv(63)
        assert d.revenue_bucket == 7
        assert d.revenue_usd_max is None    # open-ended whale tier
        assert d.engagement_tier == "power"
        assert d.is_conversion is True

    def test_decode_zero(self):
        d = decode_cv(0)
        assert d.revenue_bucket == 0
        assert d.engagement_tier == "bounce"
        assert d.is_conversion is False

    def test_revenue_midpoint_open_ended(self):
        s = CVSchema(SKANConfig(app_id="x"))
        # bucket 7 floor = $300, midpoint = 600 (2× floor)
        assert s.revenue_midpoint(7) == 600.0

    def test_revenue_midpoint_finite(self):
        s = CVSchema(SKANConfig(app_id="x"))
        # bucket 3 = [5, 20) → midpoint 12.5
        assert s.revenue_midpoint(3) == 12.5
