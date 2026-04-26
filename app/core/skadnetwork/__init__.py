"""
SKAdNetwork module — public API.

Usage:
    from app.core.skadnetwork import (
        CVSchema, encode_cv, decode_cv,
        PostbackParser, CampaignDecoder,
        skan_service,
    )
"""
from .models import (
    CoarseValue,
    CVComponents,
    DecodedCV,
    DecoderRule,
    FidelityType,
    PostbackSequence,
    SKANConfig,
    SKANPostback,
)
from .cv_schema import (
    CVSchema,
    DEFAULT_REVENUE_BUCKETS,
    DEFAULT_ENGAGEMENT_THRESHOLDS,
    encode_cv,
    decode_cv,
)
from .postback_parser import (
    PostbackParser,
    PostbackVerificationError,
)
from .campaign_decoder import CampaignDecoder
from .service import SKANService, skan_service

__all__ = [
    "CoarseValue",
    "CVComponents",
    "CVSchema",
    "CampaignDecoder",
    "DecodedCV",
    "DecoderRule",
    "DEFAULT_ENGAGEMENT_THRESHOLDS",
    "DEFAULT_REVENUE_BUCKETS",
    "FidelityType",
    "PostbackParser",
    "PostbackSequence",
    "PostbackVerificationError",
    "SKANConfig",
    "SKANPostback",
    "SKANService",
    "decode_cv",
    "encode_cv",
    "skan_service",
]
