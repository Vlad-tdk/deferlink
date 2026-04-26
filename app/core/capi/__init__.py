"""
Conversions API module — public API.

Only Facebook is implemented in v1. TikTok / Google / Snap are reserved
slots in the DB schema for future extension.
"""
from .models import (
    CAPIConfig,
    CAPIDeliveryResult,
    CAPIPlatform,
    CAPIUserData,
    CAPIEventData,
)
from .facebook import FacebookCAPIClient
from .service import CAPIService, capi_service

__all__ = [
    "CAPIConfig",
    "CAPIDeliveryResult",
    "CAPIEventData",
    "CAPIPlatform",
    "CAPIService",
    "CAPIUserData",
    "FacebookCAPIClient",
    "capi_service",
]
