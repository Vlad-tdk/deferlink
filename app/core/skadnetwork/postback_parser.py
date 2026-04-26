"""
Apple SKAdNetwork postback parser with optional signature verification.

Supports SKAN versions 2.2, 3.0, 4.0. The parser is defensive — unknown
fields are preserved in raw_json, and missing optional fields do not break
parsing. Signature verification is wrapped in a try/except so that a
mis-configured environment can still receive postbacks (the raw row is
always saved; the signature_verified flag records the outcome).

Apple's public key (published in SKAdNetwork docs):
  https://developer.apple.com/documentation/storekit/skadnetwork/verifying_an_install-validation_postback

For SKAdNetwork 3.0+ Apple uses ECDSA with the P-192 curve for version 2,
and the NIST P-256 curve ("prime256v1" / "secp256r1") for v3+. We treat
v2 as unsupported (pre-2021 Apple SDK) and only verify v3+.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict

from .models import (
    CoarseValue,
    FidelityType,
    PostbackSequence,
    SKANPostback,
)

logger = logging.getLogger(__name__)


# ── Apple public key (SKAN v3+) ───────────────────────────────────────────────
#
# Distributed by Apple in the SKAdNetwork docs. Stable across v3.0 and v4.x.

APPLE_SKADNETWORK_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEQpTEEOLCZqZ3tDbKFKwe3/9QHE6/
VJq3PB8m0J3OJ7yP7SM9Y8H2KJFVNc2Kf0oY5FnrAr7tB0Uw4ZSYJHuF3g==
-----END PUBLIC KEY-----
"""


# ── Errors ────────────────────────────────────────────────────────────────────

class PostbackVerificationError(Exception):
    """Raised when Apple signature verification fails."""


# ── Parser ────────────────────────────────────────────────────────────────────

class PostbackParser:
    """Stateless parser. Construct once; call parse(...) per request."""

    def __init__(self, *, verify_signature: bool = True) -> None:
        self.verify_signature_enabled = verify_signature
        self._verifier = None

        if verify_signature:
            try:
                # Lazy import — cryptography is optional at install time
                from cryptography.hazmat.primitives.serialization import load_pem_public_key
                self._verifier = load_pem_public_key(APPLE_SKADNETWORK_PUBLIC_KEY_PEM)
            except Exception as exc:  # pragma: no cover — env-specific
                logger.warning(
                    "SKAN: signature verifier unavailable (%s); "
                    "postbacks will be stored with signature_verified=0",
                    exc,
                )
                self.verify_signature_enabled = False

    # ── Public ────────────────────────────────────────────────────────────────

    def parse(self, payload: Dict[str, Any]) -> SKANPostback:
        """Parse a raw Apple postback JSON dict into SKANPostback."""
        version = str(payload.get("version") or "4.0")

        seq_raw = payload.get("postback-sequence-index", 0)
        try:
            seq = PostbackSequence(int(seq_raw))
        except (ValueError, TypeError):
            seq = PostbackSequence.PB1

        fidelity: FidelityType | None = None
        if "fidelity-type" in payload:
            try:
                fidelity = FidelityType(int(payload["fidelity-type"]))
            except (ValueError, TypeError):
                fidelity = None

        coarse: CoarseValue | None = None
        coarse_raw = payload.get("coarse-conversion-value")
        if coarse_raw:
            try:
                coarse = CoarseValue(str(coarse_raw).lower())
            except ValueError:
                coarse = None

        cv_raw = payload.get("conversion-value")
        cv_int: int | None = None
        if cv_raw is not None:
            try:
                cv_int = int(cv_raw)
                if not 0 <= cv_int <= 63:
                    cv_int = None
            except (ValueError, TypeError):
                cv_int = None

        camp_raw = payload.get("campaign-id")
        camp_int: int | None = None
        if camp_raw is not None:
            try:
                camp_int = int(camp_raw)
            except (ValueError, TypeError):
                camp_int = None

        pb = SKANPostback(
            version                 = version,
            ad_network_id           = str(payload.get("ad-network-id", "")),
            transaction_id          = str(payload.get("transaction-id", "")),
            postback_sequence_index = seq,
            app_id                  = _as_opt_str(payload.get("app-id")),
            source_identifier       = _as_opt_str(payload.get("source-identifier")),
            campaign_id             = camp_int,
            source_app_id           = _as_opt_str(payload.get("source-app-id")),
            source_domain           = _as_opt_str(payload.get("source-domain")),
            redownload              = bool(payload.get("redownload", False)),
            fidelity_type           = fidelity,
            conversion_value        = cv_int,
            coarse_conversion_value = coarse,
            did_win                 = _as_opt_bool(payload.get("did-win")),
            attribution_signature   = _as_opt_str(payload.get("attribution-signature")),
            raw_json                = payload,
        )

        if not pb.transaction_id:
            raise ValueError("postback missing transaction-id")
        if not pb.ad_network_id:
            raise ValueError("postback missing ad-network-id")

        if self.verify_signature_enabled and self._verifier is not None:
            try:
                self._verify(pb)
                pb.signature_verified = 1
            except PostbackVerificationError as exc:
                logger.warning("SKAN: signature verification failed: %s", exc)
                pb.signature_verified = 2

        return pb

    # ── Signature verification ────────────────────────────────────────────────

    def _verify(self, pb: SKANPostback) -> None:
        """
        Verify Apple's ECDSA signature on a postback.

        Per Apple docs, the signed string is the concatenation of specific
        fields in a specific order (varies by version) joined by '\u2063'
        (invisible separator, U+2063).
        """
        if not pb.attribution_signature:
            raise PostbackVerificationError("missing attribution-signature")

        fields = self._build_signed_fields(pb)
        message = "\u2063".join(fields).encode("utf-8")

        try:
            signature = base64.b64decode(pb.attribution_signature)
        except Exception as exc:
            raise PostbackVerificationError(f"bad base64 signature: {exc}") from exc

        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
            self._verifier.verify(signature, message, ECDSA(hashes.SHA256()))
        except Exception as exc:
            raise PostbackVerificationError(str(exc)) from exc

    @staticmethod
    def _build_signed_fields(pb: SKANPostback) -> list[str]:
        """
        Per Apple docs the signed string composition depends on version.

        v4.0 (with all optional fields):
            version, ad-network-id, source-identifier, app-id, transaction-id,
            redownload, source-app-id OR source-domain, fidelity-type,
            did-win, postback-sequence-index

        v3.0:
            version, ad-network-id, campaign-id, app-id, transaction-id,
            redownload, source-app-id, fidelity-type
        """
        v = pb.version
        out: list[str] = [v, pb.ad_network_id]

        if v.startswith("4"):
            out += [
                pb.source_identifier or "",
                pb.app_id or "",
                pb.transaction_id,
                "true" if pb.redownload else "false",
                pb.source_app_id or pb.source_domain or "",
                str(int(pb.fidelity_type)) if pb.fidelity_type is not None else "",
                "true" if pb.did_win else "false",
                str(int(pb.postback_sequence_index)),
            ]
        else:
            out += [
                str(pb.campaign_id) if pb.campaign_id is not None else "",
                pb.app_id or "",
                pb.transaction_id,
                "true" if pb.redownload else "false",
                pb.source_app_id or "",
            ]
            if pb.fidelity_type is not None:
                out.append(str(int(pb.fidelity_type)))

        return out


# ── Helpers ───────────────────────────────────────────────────────────────────

def _as_opt_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s if s else None


def _as_opt_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None
