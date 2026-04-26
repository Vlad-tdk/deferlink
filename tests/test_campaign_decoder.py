"""
Tests for the per-campaign CV → CAPI decoder.
"""

from __future__ import annotations

import json

import pytest

from app.core.skadnetwork.campaign_decoder import CampaignDecoder
from app.core.skadnetwork.models import (
    CoarseValue,
    PostbackSequence,
    SKANPostback,
)


def _pb(*, cv=None, coarse=None, source_id="1234", campaign_id=None,
        seq=PostbackSequence.PB1, app_id="com.test.app") -> SKANPostback:
    return SKANPostback(
        version="4.0",
        ad_network_id="com.example",
        transaction_id="tx-x",
        postback_sequence_index=seq,
        app_id=app_id,
        source_identifier=source_id,
        campaign_id=campaign_id,
        conversion_value=cv,
        coarse_conversion_value=coarse,
    )


@pytest.fixture
def decoder() -> CampaignDecoder:
    d = CampaignDecoder()
    d.load([{
        "source_identifier": "1234",
        "campaign_id":       None,
        "app_id":            "com.test.app",
        "enabled":           1,
        "decoder_json": json.dumps([
            {"cv_min": 0,  "cv_max": 20, "capi_event": "Lead",
             "forward": True, "value_multiplier": 1.0, "currency": "USD"},
            {"cv_min": 21, "cv_max": 41, "capi_event": "Purchase",
             "forward": True, "value_multiplier": 1.0, "currency": "USD"},
            {"cv_min": 42, "cv_max": 63, "capi_event": "Purchase",
             "forward": True, "value_multiplier": 2.0, "currency": "USD"},
        ]),
    }])
    return d


# ── Basic matching ───────────────────────────────────────────────────────────

class TestDecode:
    def test_low_cv_lead(self, decoder):
        out = decoder.decode(_pb(cv=10))
        assert out is not None
        assert out.capi_event == "Lead"

    def test_mid_cv_purchase(self, decoder):
        out = decoder.decode(_pb(cv=30))
        assert out is not None
        assert out.capi_event == "Purchase"

    def test_high_cv_doubled_value(self, decoder):
        # cv=63 → revenue bucket 7, midpoint=600, multiplier=2 → 1200
        out = decoder.decode(_pb(cv=63))
        assert out is not None
        assert out.value == 1200.0

    def test_first_match_wins(self, decoder):
        # Boundary cv=20 → first rule wins (Lead), even though no other rule
        # would match.
        out = decoder.decode(_pb(cv=20))
        assert out.capi_event == "Lead"

    def test_unknown_campaign_returns_none(self, decoder):
        out = decoder.decode(_pb(cv=10, source_id="9999"))
        assert out is None

    def test_no_cv_no_coarse_returns_none(self, decoder):
        out = decoder.decode(_pb(cv=None, coarse=None))
        assert out is None


# ── Coarse → synthetic fine CV ───────────────────────────────────────────────

class TestCoarse:
    def test_coarse_low_maps_to_lead(self, decoder):
        out = decoder.decode(_pb(cv=None, coarse=CoarseValue.LOW,
                                 seq=PostbackSequence.PB2))
        assert out is not None
        assert out.capi_event == "Lead"

    def test_coarse_medium_maps_to_purchase(self, decoder):
        out = decoder.decode(_pb(cv=None, coarse=CoarseValue.MEDIUM,
                                 seq=PostbackSequence.PB2))
        assert out is not None
        assert out.capi_event == "Purchase"

    def test_coarse_high_maps_to_high_purchase(self, decoder):
        out = decoder.decode(_pb(cv=None, coarse=CoarseValue.HIGH,
                                 seq=PostbackSequence.PB3))
        assert out is not None
        assert out.capi_event == "Purchase"
        # High coarse → cv=63 → bucket 7 midpoint × 2 = 1200
        assert out.value == 1200.0


# ── forward=False silences ───────────────────────────────────────────────────

def test_forward_false_silences_range():
    d = CampaignDecoder()
    d.load([{
        "source_identifier": "5678",
        "campaign_id":       None,
        "app_id":            "com.test.app",
        "enabled":           1,
        "decoder_json": json.dumps([
            {"cv_min": 0, "cv_max": 5, "capi_event": "Spam",
             "forward": False, "currency": "USD"},
            {"cv_min": 6, "cv_max": 63, "capi_event": "Purchase",
             "forward": True, "currency": "USD"},
        ]),
    }])
    assert d.decode(_pb(cv=3, source_id="5678")) is None
    assert d.decode(_pb(cv=10, source_id="5678")).capi_event == "Purchase"


# ── Loader ────────────────────────────────────────────────────────────────────

def test_loader_skips_disabled():
    d = CampaignDecoder()
    d.load([{
        "source_identifier": "1234",
        "campaign_id":       None,
        "app_id":            "com.test.app",
        "enabled":           0,           # disabled
        "decoder_json":      json.dumps([
            {"cv_min": 0, "cv_max": 63, "capi_event": "Purchase",
             "forward": True, "currency": "USD"},
        ]),
    }])
    assert d.decode(_pb(cv=10)) is None


def test_loader_falls_back_to_legacy_campaign_id():
    d = CampaignDecoder()
    d.load([{
        "source_identifier": None,
        "campaign_id":       42,
        "app_id":            "com.test.app",
        "enabled":           1,
        "decoder_json":      json.dumps([
            {"cv_min": 0, "cv_max": 63, "capi_event": "Purchase",
             "forward": True, "currency": "USD"},
        ]),
    }])
    out = d.decode(_pb(cv=5, source_id=None, campaign_id=42))
    assert out is not None
    assert out.capi_event == "Purchase"


def test_loader_skips_malformed_rules():
    d = CampaignDecoder()
    d.load([
        {"source_identifier": "good", "app_id": "com.test.app", "enabled": 1,
         "decoder_json": json.dumps([
             {"cv_min": 0, "cv_max": 63, "capi_event": "Purchase",
              "forward": True, "currency": "USD"},
         ])},
        {"source_identifier": "bad", "app_id": "com.test.app", "enabled": 1,
         "decoder_json": "{not valid json"},
    ])
    assert d.has_campaign("com.test.app", "good")
    assert not d.has_campaign("com.test.app", "bad")


def test_decoders_are_scoped_per_app_id():
    d = CampaignDecoder()
    d.load([
        {
            "source_identifier": "1234",
            "campaign_id": None,
            "app_id": "com.app.one",
            "enabled": 1,
            "decoder_json": json.dumps([
                {"cv_min": 0, "cv_max": 63, "capi_event": "Lead", "forward": True, "currency": "USD"},
            ]),
        },
        {
            "source_identifier": "1234",
            "campaign_id": None,
            "app_id": "com.app.two",
            "enabled": 1,
            "decoder_json": json.dumps([
                {"cv_min": 0, "cv_max": 63, "capi_event": "Purchase", "forward": True, "currency": "USD"},
            ]),
        },
    ])

    assert d.decode(_pb(cv=10, app_id="com.app.one")).capi_event == "Lead"
    assert d.decode(_pb(cv=10, app_id="com.app.two")).capi_event == "Purchase"
