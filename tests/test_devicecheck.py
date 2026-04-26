from __future__ import annotations

import pytest

from app.core.devicecheck import DeviceCheckVerifier


@pytest.mark.asyncio
async def test_empty_devicecheck_token_is_invalid():
    verifier = DeviceCheckVerifier()
    result = await verifier.verify("")
    assert result.valid is False
    assert result.status == "invalid"


@pytest.mark.asyncio
async def test_degraded_devicecheck_is_indeterminate_not_valid():
    verifier = DeviceCheckVerifier()
    result = await verifier.verify("base64-token")
    assert result.valid is False
    assert result.status == "indeterminate"
    assert result.reason == "degraded_mode"

