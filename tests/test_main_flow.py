from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Response
from starlette.requests import Request

from app.core.cloaking import CloakingAction
from app.models import FingerprintData, ResolveRequest
from app import main


def _request(
    path: str = "/dl",
    *,
    user_agent: str = "Mozilla/5.0",
    forwarded_for: str | None = None,
    real_ip: str | None = None,
) -> Request:
    headers = [(b"user-agent", user_agent.encode())]
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    if real_ip is not None:
        headers.append((b"x-real-ip", real_ip.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "query_string": b"",
        "headers": headers,
        "client": ("9.9.9.9", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


class _StubCloakEngine:
    def decide(self, **kwargs):
        return SimpleNamespace(
            action=CloakingAction.FULL_FLOW,
            visitor_type=SimpleNamespace(value="real_user"),
            confidence=0.0,
            signals=[],
        )


@pytest.mark.asyncio
async def test_create_deeplink_ignores_stale_cookie_session(monkeypatch):
    calls: list[tuple[str, str]] = []

    class StubHandler:
        def get_session(self, session_id: str):
            assert session_id == "cookie-session"
            return {"session_id": session_id, "promo_id": "OLD", "domain": "old.example"}

        def create_session(self, **kwargs):
            calls.append((kwargs["promo_id"], kwargs["domain"]))
            return "new-session"

    monkeypatch.setattr(main, "deeplink_handler", StubHandler())
    monkeypatch.setattr(main, "get_engine", lambda: _StubCloakEngine())

    response = await main.create_deeplink(
        request=_request(),
        response=Response(),
        promo_id="NEW",
        domain="new.example",
        ttl=48,
        session_id="cookie-session",
    )

    assert response.status_code == 200
    assert calls == [("NEW", "new.example")]
    assert "NEW" in response.body.decode()
    assert "new.example" in response.body.decode()


@pytest.mark.asyncio
async def test_prepare_resolve_request_strips_untrusted_devicecheck(monkeypatch):
    class StubVerifier:
        async def verify(self, token: str):
            return SimpleNamespace(status="invalid", reason="bad-token")

    req = ResolveRequest(
        fingerprint=FingerprintData(model="iPhone", device_check_token="bad-token"),
        app_scheme="myapp://open",
        fallback_url="https://example.com",
    )

    monkeypatch.setattr(main.Config, "DEVICECHECK_ENABLED", True)
    monkeypatch.setattr(main.dc_module, "get_verifier", lambda: StubVerifier())

    prepared, token = await main._prepare_resolve_request(req)

    assert token is None
    assert prepared.fingerprint.device_check_token is None
    assert req.fingerprint.device_check_token == "bad-token"


@pytest.mark.asyncio
async def test_prepare_resolve_request_keeps_verified_devicecheck(monkeypatch):
    class StubVerifier:
        async def verify(self, token: str):
            return SimpleNamespace(status="valid", reason=None)

    req = ResolveRequest(
        fingerprint=FingerprintData(model="iPhone", device_check_token="good-token"),
        app_scheme="myapp://open",
        fallback_url="https://example.com",
    )

    monkeypatch.setattr(main.Config, "DEVICECHECK_ENABLED", True)
    monkeypatch.setattr(main.dc_module, "get_verifier", lambda: StubVerifier())

    prepared, token = await main._prepare_resolve_request(req)

    assert token == "good-token"
    assert prepared.fingerprint.device_check_token == "good-token"
