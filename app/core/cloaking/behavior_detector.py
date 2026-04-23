"""
Behavioral / header-based bot detection.

Unlike IP/UA detectors this one is probabilistic — each signal is weak on its
own, but combined they can push the confidence over threshold.

Signals examined:
  - Accept header      (bots often send minimal or absent Accept)
  - Accept-Language    (real browsers always send this)
  - Accept-Encoding    (bots may omit gzip/br)
  - Referer            (bots usually have none on first visit)
  - Cookie presence    (real users accumulate cookies; bots rarely have them)
  - Connection         (bots often use "close", browsers "keep-alive")
  - Cache-Control      (bots skip "no-cache")
  - Sec-Fetch-*        (browsers always send these; bots never do)
  - DNT                (robots don't need privacy)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .models import DetectionSignal, VisitorType

logger = logging.getLogger(__name__)

# Confidence weights for each behavioral signal
_WEIGHTS: Dict[str, float] = {
    "no_accept_language":    0.50,   # very strong — real browsers always send this
    "no_sec_fetch_site":     0.45,   # Sec-Fetch-* only sent by Chromium family + Firefox
    "no_accept":             0.30,
    "minimal_accept":        0.25,
    "no_accept_encoding":    0.25,
    "connection_close":      0.15,
    "no_referer":            0.10,   # weak — many real users have no referer
    "no_cookies":            0.10,   # weak alone
}


class BehaviorDetector:
    """
    Analyses HTTP request headers for bot-like behaviour.

    Usage:
        detector = BehaviorDetector()
        signals = detector.detect(headers, cookies, referer)
    """

    def detect(
        self,
        headers:  Dict[str, str],
        cookies:  Dict[str, str],
        referer:  Optional[str] = None,
    ) -> List[DetectionSignal]:
        """
        headers  — dict of lower-cased header names → values
        cookies  — dict of cookie names present in the request
        referer  — value of the Referer header (optional, can pass separately)
        """
        signals: List[DetectionSignal] = []

        accept_language = headers.get("accept-language", "")
        accept          = headers.get("accept", "")
        accept_encoding = headers.get("accept-encoding", "")
        connection      = headers.get("connection", "")
        sec_fetch_site  = headers.get("sec-fetch-site", "")
        ref             = referer or headers.get("referer", "")

        # 1. No Accept-Language — almost no real browser does this
        if not accept_language.strip():
            signals.append(self._signal(
                "no_accept_language",
                "No Accept-Language header (unusual for real browsers)",
                _WEIGHTS["no_accept_language"],
            ))

        # 2. No Sec-Fetch-Site — Chromium/Firefox always send Sec-Fetch-*
        if not sec_fetch_site.strip():
            signals.append(self._signal(
                "no_sec_fetch_site",
                "No Sec-Fetch-Site header (absent in non-browser HTTP clients)",
                _WEIGHTS["no_sec_fetch_site"],
            ))

        # 3. No Accept header at all
        if not accept.strip():
            signals.append(self._signal(
                "no_accept",
                "No Accept header",
                _WEIGHTS["no_accept"],
            ))
        elif accept.strip() == "*/*":
            # curl, wget, many bots send just "*/*"
            signals.append(self._signal(
                "minimal_accept",
                "Minimal Accept header (*/*) — typical of HTTP clients",
                _WEIGHTS["minimal_accept"],
            ))

        # 4. No Accept-Encoding — browsers always negotiate compression
        if not accept_encoding.strip():
            signals.append(self._signal(
                "no_accept_encoding",
                "No Accept-Encoding header",
                _WEIGHTS["no_accept_encoding"],
            ))

        # 5. Connection: close — bots often don't bother with keep-alive
        if "close" in connection.lower() and "keep-alive" not in connection.lower():
            signals.append(self._signal(
                "connection_close",
                "Connection: close (browsers prefer keep-alive)",
                _WEIGHTS["connection_close"],
            ))

        # 6. No Referer on a non-direct visit (weak signal by itself)
        if not ref.strip():
            signals.append(self._signal(
                "no_referer",
                "No Referer header",
                _WEIGHTS["no_referer"],
            ))

        # 7. No cookies at all
        if not cookies:
            signals.append(self._signal(
                "no_cookies",
                "No cookies present (first visit or bot)",
                _WEIGHTS["no_cookies"],
            ))

        return signals

    @staticmethod
    def _signal(key: str, description: str, confidence: float) -> DetectionSignal:
        return DetectionSignal(
            source="behavior",
            description=description,
            visitor_type=VisitorType.SUSPICIOUS,   # behavior alone → suspicious
            confidence=confidence,
            matched_value=key,
        )
