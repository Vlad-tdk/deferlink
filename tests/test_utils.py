from __future__ import annotations

from starlette.requests import Request

from app import utils


def _request(*, forwarded_for: str | None = None, real_ip: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    if real_ip is not None:
        headers.append((b"x-real-ip", real_ip.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "query_string": b"",
        "headers": headers,
        "client": ("9.9.9.9", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_generate_instruction_page_escapes_reflected_values():
    html_page = utils.generate_instruction_page(
        'evil.example"><script>alert(1)</script>',
        'PROMO"><img src=x onerror=alert(1)>',
    )

    assert "<script>alert(1)</script>" not in html_page
    assert '"><img src=x onerror=alert(1)>' not in html_page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_page
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_page


def test_get_client_ip_ignores_proxy_headers_when_untrusted(monkeypatch):
    monkeypatch.setattr(utils.Config, "TRUST_PROXY_HEADERS", False)

    ip = utils.get_client_ip(_request(forwarded_for="1.1.1.1", real_ip="2.2.2.2"))

    assert ip == "9.9.9.9"


def test_get_client_ip_respects_proxy_headers_when_trusted(monkeypatch):
    monkeypatch.setattr(utils.Config, "TRUST_PROXY_HEADERS", True)

    ip = utils.get_client_ip(_request(forwarded_for="1.1.1.1, 2.2.2.2"))

    assert ip == "1.1.1.1"
