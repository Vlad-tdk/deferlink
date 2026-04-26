"""
Data types for CAPI forwarding.

CAPIEventData and CAPIUserData mirror Facebook's Conversions API fields
but are platform-agnostic. Platform-specific clients (facebook.py, future
tiktok.py) map these to their concrete payload shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CAPIPlatform(str, Enum):
    FACEBOOK = "facebook"
    TIKTOK   = "tiktok"
    GOOGLE   = "google"
    SNAP     = "snap"


@dataclass
class CAPIConfig:
    """Per-app + platform credentials."""
    app_id:          str
    platform:        CAPIPlatform
    pixel_id:        str            # Facebook "Dataset ID" / pixel id
    access_token:    str            # CAPI access token (long-lived)
    test_event_code: Optional[str] = None  # Facebook test event code
    api_version:     str = "v21.0"
    enabled:         bool = True


@dataclass
class CAPIUserData:
    """
    PII fields Facebook can match on. All are optional — Facebook uses
    whatever is provided and hashes them server-side if not already hashed.

    For SKAN-sourced events most of these are unavailable (Apple doesn't
    leak user identifiers). We rely on client_ip_address + client_user_agent
    as the minimal match set, plus external_id if the SDK has one.
    """
    client_ip_address:  Optional[str] = None
    client_user_agent:  Optional[str] = None
    external_id:        Optional[str] = None   # app_user_id (hashed or raw)
    fbp:                Optional[str] = None   # fb browser cookie
    fbc:                Optional[str] = None   # fb click id
    em:                 Optional[str] = None   # email (hash)
    ph:                 Optional[str] = None   # phone (hash)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.client_ip_address: out["client_ip_address"] = self.client_ip_address
        if self.client_user_agent: out["client_user_agent"] = self.client_user_agent
        if self.external_id:       out["external_id"]       = self.external_id
        if self.fbp:               out["fbp"]               = self.fbp
        if self.fbc:               out["fbc"]               = self.fbc
        if self.em:                out["em"]                = self.em
        if self.ph:                out["ph"]                = self.ph
        return out


@dataclass
class CAPIEventData:
    """
    A single CAPI event ready to be forwarded.

    event_id is the deduplication key. For SKAN-sourced events we use
    the Apple transaction_id; for SDK-sourced events we use the event_id
    already generated client-side (UUID).
    """
    event_name:      str                 # "Purchase", "Lead", "CompleteRegistration"
    event_id:        str                 # dedup key
    event_time:      int                 # unix timestamp (seconds)
    event_source_url: Optional[str] = None
    action_source:   str = "app"         # "website" | "email" | "app" | ...
    user_data:       CAPIUserData = field(default_factory=CAPIUserData)
    value:           Optional[float] = None
    currency:        Optional[str] = None
    custom_data:     Dict[str, Any] = field(default_factory=dict)

    # Internal — origin tracking for delivery log
    source:          str = "manual"      # "sdk" | "skan" | "manual"
    source_ref_id:   Optional[int] = None


@dataclass
class CAPIDeliveryResult:
    """Outcome of a single forward attempt."""
    success:       bool
    status_code:   Optional[int]
    response_body: str
    error:         Optional[str] = None
    delivery_log_id: Optional[int] = None
