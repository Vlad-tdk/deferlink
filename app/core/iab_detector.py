"""
In-App Browser (IAB) detection
Определение встроенных браузеров социальных сетей

Ключевой факт:
- Facebook/Instagram IAB = WKWebView → DeviceCheck недоступен
- Safari = полный доступ к cookies, SFSafariViewController shared cookie jar
- Clipboard через execCommand работает в WKWebView без user gesture
"""

import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class BrowserContext(str, Enum):
    SAFARI          = "safari"
    FACEBOOK_IAB    = "facebook_iab"
    INSTAGRAM_IAB   = "instagram_iab"
    TIKTOK_IAB      = "tiktok_iab"
    TWITTER_IAB     = "twitter_iab"
    WECHAT_IAB      = "wechat_iab"
    SNAPCHAT_IAB    = "snapchat_iab"
    GENERIC_IAB     = "generic_iab"    # WKWebView без Safari-маркера
    CHROME_IOS      = "chrome_ios"
    UNKNOWN         = "unknown"


class EscapeStrategy(str, Enum):
    NONE                    = "none"                    # Safari — эскейп не нужен
    CLIPBOARD_THEN_APPSTORE = "clipboard_then_appstore" # Clipboard → App Store
    APPSTORE_REDIRECT       = "appstore_redirect"       # Просто редирект (clipboard ненадёжен)
    UNIVERSAL_LINK          = "universal_link"          # Universal Link если приложение уже установлено


@dataclass
class BrowserDetectionResult:
    context: BrowserContext
    is_iab: bool

    # Что доступно в этом контексте
    supports_cookies: bool          # Куки работают (но не шарятся с Safari)
    clipboard_reliable: bool        # execCommand('copy') работает без user gesture
    devicecheck_supported: bool     # DeviceCheck доступен через native app (всегда False в браузере)

    # Как уходить из IAB
    escape_strategy: EscapeStrategy

    # Дополнительные сигналы
    source_app: Optional[str] = None   # "Facebook", "Instagram", ...


# ──────────────────────────────────────────────────────────────────────────────
# Детальные паттерны User-Agent
# ──────────────────────────────────────────────────────────────────────────────

_FB_PATTERNS = re.compile(
    r'(FBAN|FBAV|FBIOS|FB_IAB|FBDV|FB4A|FBBV|FBCR|FBID|FBLC|FBOP|'
    r'Messenger|MessengerForIOS|MessengerLite)',
    re.IGNORECASE
)

_INSTAGRAM_PATTERNS = re.compile(r'Instagram', re.IGNORECASE)
_TIKTOK_PATTERNS    = re.compile(r'(Musical_ly|BytedanceWebview|TikTok|musical\.ly)', re.IGNORECASE)
_TWITTER_PATTERNS   = re.compile(r'(Twitter(?:Android|iPhone)|twitterkit)', re.IGNORECASE)
_WECHAT_PATTERNS    = re.compile(r'MicroMessenger', re.IGNORECASE)
_SNAPCHAT_PATTERNS  = re.compile(r'Snapchat', re.IGNORECASE)

# WKWebView без Safari: есть AppleWebKit и Mobile, но нет слова "Safari"
# Это ловит почти любой кастомный IAB на iOS
_GENERIC_WKWEBVIEW  = re.compile(r'AppleWebKit.*Mobile(?!.*Safari)', re.IGNORECASE)


def detect_browser(user_agent: str) -> BrowserDetectionResult:
    """
    Определить контекст браузера по User-Agent.

    Returns:
        BrowserDetectionResult с полной информацией о контексте и стратегии эскейпа.
    """
    ua = user_agent or ""

    # ── Facebook / Messenger ──────────────────────────────────────────────────
    if _FB_PATTERNS.search(ua):
        return BrowserDetectionResult(
            context=BrowserContext.FACEBOOK_IAB,
            is_iab=True,
            supports_cookies=True,
            clipboard_reliable=True,   # execCommand работает в FB WKWebView
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.CLIPBOARD_THEN_APPSTORE,
            source_app="Facebook"
        )

    # ── Instagram ─────────────────────────────────────────────────────────────
    if _INSTAGRAM_PATTERNS.search(ua):
        return BrowserDetectionResult(
            context=BrowserContext.INSTAGRAM_IAB,
            is_iab=True,
            supports_cookies=True,
            clipboard_reliable=True,
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.CLIPBOARD_THEN_APPSTORE,
            source_app="Instagram"
        )

    # ── TikTok ────────────────────────────────────────────────────────────────
    if _TIKTOK_PATTERNS.search(ua):
        return BrowserDetectionResult(
            context=BrowserContext.TIKTOK_IAB,
            is_iab=True,
            supports_cookies=True,
            clipboard_reliable=False,   # TikTok блокирует execCommand
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.APPSTORE_REDIRECT,
            source_app="TikTok"
        )

    # ── Twitter ───────────────────────────────────────────────────────────────
    if _TWITTER_PATTERNS.search(ua):
        return BrowserDetectionResult(
            context=BrowserContext.TWITTER_IAB,
            is_iab=True,
            supports_cookies=True,
            clipboard_reliable=True,
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.CLIPBOARD_THEN_APPSTORE,
            source_app="Twitter"
        )

    # ── WeChat ────────────────────────────────────────────────────────────────
    if _WECHAT_PATTERNS.search(ua):
        return BrowserDetectionResult(
            context=BrowserContext.WECHAT_IAB,
            is_iab=True,
            supports_cookies=True,
            clipboard_reliable=False,
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.APPSTORE_REDIRECT,
            source_app="WeChat"
        )

    # ── Snapchat ──────────────────────────────────────────────────────────────
    if _SNAPCHAT_PATTERNS.search(ua):
        return BrowserDetectionResult(
            context=BrowserContext.SNAPCHAT_IAB,
            is_iab=True,
            supports_cookies=True,
            clipboard_reliable=False,
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.APPSTORE_REDIRECT,
            source_app="Snapchat"
        )

    # ── Chrome for iOS ────────────────────────────────────────────────────────
    # CriOS — маркер Chrome на iOS (WKWebView внутри, но не IAB)
    if re.search(r'CriOS', ua):
        return BrowserDetectionResult(
            context=BrowserContext.CHROME_IOS,
            is_iab=False,
            supports_cookies=True,
            clipboard_reliable=True,
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.NONE,
            source_app="Chrome"
        )

    # ── Real Safari ───────────────────────────────────────────────────────────
    # Safari: содержит "Safari" И "Mobile Safari" / "Version/", НЕ содержит CriOS/FBiOS/etc.
    if re.search(r'Safari', ua) and not re.search(r'Chrome|CriOS|FxiOS', ua):
        return BrowserDetectionResult(
            context=BrowserContext.SAFARI,
            is_iab=False,
            supports_cookies=True,
            clipboard_reliable=True,
            devicecheck_supported=True,  # Нативный DeviceCheck доступен после открытия приложения
            escape_strategy=EscapeStrategy.NONE,
            source_app=None
        )

    # ── Generic WKWebView IAB ─────────────────────────────────────────────────
    if _GENERIC_WKWEBVIEW.search(ua):
        return BrowserDetectionResult(
            context=BrowserContext.GENERIC_IAB,
            is_iab=True,
            supports_cookies=True,
            clipboard_reliable=False,
            devicecheck_supported=False,
            escape_strategy=EscapeStrategy.APPSTORE_REDIRECT,
            source_app=None
        )

    return BrowserDetectionResult(
        context=BrowserContext.UNKNOWN,
        is_iab=False,
        supports_cookies=True,
        clipboard_reliable=False,
        devicecheck_supported=False,
        escape_strategy=EscapeStrategy.APPSTORE_REDIRECT,
        source_app=None
    )


def should_escape_to_safari(result: BrowserDetectionResult) -> bool:
    """Нужно ли применять стратегию эскейпа из IAB?"""
    return result.is_iab and result.escape_strategy != EscapeStrategy.NONE
