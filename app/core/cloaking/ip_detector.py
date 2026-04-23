"""
IP-based bot detection.

Detection chain (in order of confidence):
  1. Exact IP match        — custom rules from DB
  2. CIDR range match      — built-in + custom rules from DB
  3. ASN match             — built-in + custom rules from DB

Performance:
  - IP networks pre-sorted by prefix length (most-specific first) so the
    first match is the tightest one.
  - All ipaddress objects built once at load/reload time.
  - Lookup is O(n) over pre-filtered IPv4 vs IPv6 lists — fast enough for
    tens of thousands of ranges; use a trie/radix tree if you need millions.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import Dict, List, Optional, Tuple, Union

from .models import CloakingDecision, DetectionSignal, IPRule, VisitorType
from .known_data import KNOWN_IP_RANGES, KNOWN_ASNS

logger = logging.getLogger(__name__)

IPAddr    = Union[IPv4Address, IPv6Address]
IPNetwork = Union[IPv4Network, IPv6Network]


@dataclass
class _CompiledIPRule:
    network:      Optional[IPNetwork]
    ip_exact:     Optional[IPAddr]
    asn:          Optional[int]
    visitor_type: VisitorType
    confidence:   float
    description:  str
    source:       str           # "builtin" | "custom"
    rule_id:      int = -1


class IPDetector:
    """
    Checks an IP address against known bot/crawler/ad-review ranges.

    Usage:
        detector = IPDetector()
        detector.load_custom_rules(db_ip_rules)   # call after DB load
        signals = detector.detect("66.249.64.1")
    """

    def __init__(self) -> None:
        self._rules: List[_CompiledIPRule] = []
        self._exact:  Dict[str, _CompiledIPRule] = {}  # ip_str → rule
        self._asn_map: Dict[int, _CompiledIPRule] = {}  # asn → rule
        self._build_builtins()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_builtins(self) -> None:
        network_rules: List[_CompiledIPRule] = []

        for cidr, vtype_str, confidence, desc in KNOWN_IP_RANGES:
            vtype = VisitorType(vtype_str)
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                network_rules.append(_CompiledIPRule(
                    network=net, ip_exact=None, asn=None,
                    visitor_type=vtype, confidence=confidence,
                    description=desc, source="builtin",
                ))
            except ValueError:
                logger.warning("Invalid builtin CIDR '%s' — skipped", cidr)

        for asn, vtype_str, confidence, desc in KNOWN_ASNS:
            vtype = VisitorType(vtype_str)
            rule = _CompiledIPRule(
                network=None, ip_exact=None, asn=asn,
                visitor_type=vtype, confidence=confidence,
                description=desc, source="builtin",
            )
            self._asn_map[asn] = rule

        # Sort networks: most specific (largest prefix) first
        network_rules.sort(key=lambda r: r.network.prefixlen, reverse=True)
        self._rules = network_rules
        logger.debug(
            "IPDetector: loaded %d builtin CIDR rules, %d ASN rules",
            len(self._rules), len(self._asn_map),
        )

    def load_custom_rules(self, rules: List[IPRule]) -> None:
        """Replace all custom rules (re-called after DB update)."""
        # Remove previous custom entries
        self._rules = [r for r in self._rules if r.source != "custom"]
        self._exact = {k: v for k, v in self._exact.items() if v.source != "custom"}
        self._asn_map = {k: v for k, v in self._asn_map.items() if v.source != "custom"}

        custom_network: List[_CompiledIPRule] = []

        for rule in rules:
            if not rule.enabled:
                continue
            vtype = rule.visitor_type
            cr = _CompiledIPRule(
                network=None, ip_exact=None, asn=None,
                visitor_type=vtype, confidence=rule.confidence,
                description=rule.description, source="custom",
                rule_id=rule.id,
            )

            if rule.ip_exact:
                try:
                    cr.ip_exact = ipaddress.ip_address(rule.ip_exact)
                    self._exact[rule.ip_exact] = cr
                except ValueError:
                    logger.warning("Invalid custom IP '%s' — skipped", rule.ip_exact)

            elif rule.cidr:
                try:
                    cr.network = ipaddress.ip_network(rule.cidr, strict=False)
                    custom_network.append(cr)
                except ValueError:
                    logger.warning("Invalid custom CIDR '%s' — skipped", rule.cidr)

            elif rule.asn is not None:
                cr.asn = rule.asn
                self._asn_map[rule.asn] = cr

        # Re-sort with custom rules mixed in
        custom_network.sort(key=lambda r: r.network.prefixlen, reverse=True)
        self._rules = custom_network + self._rules
        # Stable re-sort to keep most-specific first overall
        self._rules.sort(key=lambda r: r.network.prefixlen, reverse=True)

        logger.debug(
            "IPDetector: reloaded — %d CIDR, %d exact, %d ASN rules total",
            len(self._rules), len(self._exact), len(self._asn_map),
        )

    # ── Detect ────────────────────────────────────────────────────────────────

    def detect(self, ip_str: str, asn: Optional[int] = None) -> List[DetectionSignal]:
        """
        Return all matching signals for the given IP (and optional ASN).
        Empty list → no bot signals detected.
        """
        if not ip_str:
            return []

        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            logger.debug("IPDetector: invalid IP address '%s'", ip_str)
            return []

        signals: List[DetectionSignal] = []

        # 1. Exact match (highest priority)
        if ip_str in self._exact:
            rule = self._exact[ip_str]
            signals.append(DetectionSignal(
                source="ip_exact",
                description=rule.description,
                visitor_type=rule.visitor_type,
                confidence=rule.confidence,
                matched_value=ip_str,
            ))

        # 2. CIDR range match (stop at first / most-specific match)
        for rule in self._rules:
            try:
                if addr in rule.network:
                    signals.append(DetectionSignal(
                        source="ip_cidr",
                        description=rule.description,
                        visitor_type=rule.visitor_type,
                        confidence=rule.confidence,
                        matched_value=f"{ip_str} in {rule.network}",
                    ))
                    break   # most-specific match found; no need to continue
            except TypeError:
                continue

        # 3. ASN match
        if asn is not None and asn in self._asn_map:
            rule = self._asn_map[asn]
            signals.append(DetectionSignal(
                source="ip_asn",
                description=rule.description,
                visitor_type=rule.visitor_type,
                confidence=rule.confidence,
                matched_value=f"AS{asn}",
            ))

        return signals
