"""
User-Agent based bot detection.

Each pattern is a case-insensitive regular expression with a confidence score.
Patterns are compiled once and matched via a single combined regex for speed
(alternation is faster than iterating N individual patterns).

Custom rules from DB are merged at reload time — no restart needed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import DetectionSignal, UARuleRecord, VisitorType
from .known_data import KNOWN_UA_PATTERNS

logger = logging.getLogger(__name__)


@dataclass
class _CompiledUARule:
    regex:        re.Pattern
    visitor_type: VisitorType
    confidence:   float
    description:  str
    source:       str   # "builtin" | "custom"
    rule_id:      int = -1


class UADetector:
    """
    Matches a User-Agent string against known bot/crawler patterns.

    Usage:
        detector = UADetector()
        detector.load_custom_rules(db_ua_rules)
        signals = detector.detect(user_agent_string)
    """

    def __init__(self) -> None:
        self._rules: List[_CompiledUARule] = []
        self._build_builtins()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_builtins(self) -> None:
        rules: List[_CompiledUARule] = []
        for pattern, vtype_str, confidence, desc in KNOWN_UA_PATTERNS:
            compiled = self._compile(pattern)
            if compiled is None:
                continue
            rules.append(_CompiledUARule(
                regex=compiled,
                visitor_type=VisitorType(vtype_str),
                confidence=confidence,
                description=desc,
                source="builtin",
            ))
        self._rules = rules
        logger.debug("UADetector: loaded %d builtin patterns", len(self._rules))

    def load_custom_rules(self, rules: List[UARuleRecord]) -> None:
        """Replace all custom rules (re-called after DB update)."""
        self._rules = [r for r in self._rules if r.source != "custom"]

        custom: List[_CompiledUARule] = []
        for rule in rules:
            if not rule.enabled:
                continue
            compiled = self._compile(rule.pattern)
            if compiled is None:
                logger.warning("Invalid custom UA pattern '%s' — skipped", rule.pattern)
                continue
            custom.append(_CompiledUARule(
                regex=compiled,
                visitor_type=rule.visitor_type,
                confidence=rule.confidence,
                description=rule.description,
                source="custom",
                rule_id=rule.id,
            ))

        # Custom rules go first (higher priority over builtins)
        self._rules = custom + self._rules
        logger.debug(
            "UADetector: reloaded — %d total patterns (%d custom)",
            len(self._rules), len(custom),
        )

    # ── Detect ────────────────────────────────────────────────────────────────

    def detect(self, user_agent: str) -> List[DetectionSignal]:
        """
        Return all matching signals.  All matching patterns are returned so
        the engine can pick the highest-confidence one.
        """
        if not user_agent:
            return []

        ua_lower = user_agent.lower()
        signals:  List[DetectionSignal] = []
        seen_vtype_confidence: dict = {}  # avoid duplicate signal types

        for rule in self._rules:
            m = rule.regex.search(ua_lower)
            if not m:
                continue

            key = (rule.visitor_type, rule.description)
            if key in seen_vtype_confidence:
                # Keep the highest confidence match per description
                if rule.confidence <= seen_vtype_confidence[key]:
                    continue
            seen_vtype_confidence[key] = rule.confidence

            signals.append(DetectionSignal(
                source="ua_regex",
                description=rule.description,
                visitor_type=rule.visitor_type,
                confidence=rule.confidence,
                matched_value=m.group(0),
            ))

        return signals

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compile(pattern: str) -> Optional[re.Pattern]:
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            logger.warning("UADetector: invalid regex '%s': %s", pattern, exc)
            return None
