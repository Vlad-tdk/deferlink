"""
Tests for the Apple SKAdNetwork postback parser.

We cover SKAN v3 + v4 happy paths and a handful of malformed inputs.
Signature verification is exercised through the public flag — we don't
mock Apple's key, we just check the parser stays robust when verification
is off.
"""

from __future__ import annotations

import pytest

from app.core.skadnetwork.models import (
    CoarseValue,
    FidelityType,
    PostbackSequence,
)
from app.core.skadnetwork.postback_parser import PostbackParser


@pytest.fixture
def parser() -> PostbackParser:
    # Sig verification off — Apple key isn't going to verify a synthetic
    # payload, and we'd rather test the data-shape behaviour here.
    return PostbackParser(verify_signature=False)


# ── Happy paths ───────────────────────────────────────────────────────────────

def test_parse_skan4_pb1(parser):
    payload = {
        "version":                 "4.0",
        "ad-network-id":           "com.example.adnetwork",
        "transaction-id":          "tx-001",
        "source-identifier":       "1234",
        "app-id":                  123456789,
        "postback-sequence-index": 0,
        "redownload":              False,
        "fidelity-type":           1,
        "conversion-value":        42,
        "did-win":                 True,
    }
    pb = parser.parse(payload)

    assert pb.version == "4.0"
    assert pb.transaction_id == "tx-001"
    assert pb.app_id == "123456789"
    assert pb.source_identifier == "1234"
    assert pb.postback_sequence_index == PostbackSequence.PB1
    assert pb.fidelity_type == FidelityType.CLICK_THROUGH
    assert pb.conversion_value == 42
    assert pb.did_win is True
    assert pb.is_pb1 is True
    assert pb.campaign_key == "1234"


def test_parse_skan4_pb2_coarse(parser):
    payload = {
        "version":                 "4.0",
        "ad-network-id":           "com.example.adnetwork",
        "transaction-id":          "tx-002",
        "source-identifier":       "5678",
        "postback-sequence-index": 1,
        "coarse-conversion-value": "medium",
        "did-win":                 True,
    }
    pb = parser.parse(payload)
    assert pb.coarse_conversion_value == CoarseValue.MEDIUM
    assert pb.conversion_value is None
    assert pb.postback_sequence_index == PostbackSequence.PB2
    assert pb.is_pb1 is False


def test_parse_skan3_legacy_campaign(parser):
    payload = {
        "version":        "3.0",
        "ad-network-id":  "com.example.adnetwork",
        "transaction-id": "tx-003",
        "campaign-id":    42,
        "app-id":         "999",
        "redownload":     True,
        "conversion-value": 7,
    }
    pb = parser.parse(payload)
    assert pb.campaign_id == 42
    assert pb.source_identifier is None
    assert pb.campaign_key == "42"
    assert pb.redownload is True


# ── Defensive parsing ────────────────────────────────────────────────────────

def test_missing_transaction_id_raises(parser):
    with pytest.raises(ValueError, match="transaction-id"):
        parser.parse({
            "version":       "4.0",
            "ad-network-id": "x",
        })


def test_missing_ad_network_id_raises(parser):
    with pytest.raises(ValueError, match="ad-network-id"):
        parser.parse({
            "version":        "4.0",
            "transaction-id": "tx",
        })


def test_invalid_cv_silently_dropped(parser):
    payload = {
        "version":          "4.0",
        "ad-network-id":    "x",
        "transaction-id":   "tx-cv",
        "conversion-value": "not-a-number",
    }
    pb = parser.parse(payload)
    assert pb.conversion_value is None


def test_cv_out_of_range_dropped(parser):
    pb = parser.parse({
        "version":          "4.0",
        "ad-network-id":    "x",
        "transaction-id":   "tx-cv2",
        "conversion-value": 999,
    })
    assert pb.conversion_value is None


def test_invalid_coarse_dropped(parser):
    pb = parser.parse({
        "version":                 "4.0",
        "ad-network-id":           "x",
        "transaction-id":          "tx-coarse",
        "coarse-conversion-value": "extreme",   # not a valid value
    })
    assert pb.coarse_conversion_value is None


def test_invalid_sequence_falls_back_to_pb1(parser):
    pb = parser.parse({
        "version":                 "4.0",
        "ad-network-id":           "x",
        "transaction-id":          "tx-seq",
        "postback-sequence-index": "garbage",
    })
    assert pb.postback_sequence_index == PostbackSequence.PB1


def test_did_win_string_forms(parser):
    for v, expected in [("true", True), ("false", False), ("1", True),
                        ("0", False), ("yes", True), ("no", False)]:
        pb = parser.parse({
            "version":        "4.0",
            "ad-network-id":  "x",
            "transaction-id": f"tx-{v}",
            "did-win":        v,
        })
        assert pb.did_win is expected, f"did-win={v}"


def test_signature_verified_zero_when_disabled(parser):
    pb = parser.parse({
        "version":               "4.0",
        "ad-network-id":         "x",
        "transaction-id":        "tx-no-sig",
        "attribution-signature": "abc==",
    })
    # Verification disabled → flag stays at default 0 (not checked)
    assert pb.signature_verified == 0
