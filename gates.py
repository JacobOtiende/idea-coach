"""Gate 1 (local security filter) and Gate 2 (scope gate).

Gate 1 runs in plain Python before any API call and blocks the whole message.
It only recognizes patterns; descriptions of real networks, systems,
vulnerabilities, incidents, customer data, and employer systems remain the
user's responsibility.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

REJECT_LINE = "That's outside Idea Coach. If it connects to an idea, tell me what problem it's solving."
BLOCK_LINE = (
    "Blocked before anything was sent: this message looks like it contains {reasons}. "
    "Nothing was sent or saved. Remove it and try again."
)

# (label, pattern). Labels are shown to the user; matched text never is.
_CREDENTIAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("a private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("an API key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{16,}")),
    ("an API key", re.compile(r"\btvly-[A-Za-z0-9_\-]{12,}")),
    ("an AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("a token", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}")),
    ("a bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]{20,}")),
    ("a password", re.compile(
        r"(?i)\b(?:password|passwd|pwd|passcode|secret|api[_\- ]?key|access[_\- ]?token|client[_\- ]?secret)"
        r"\s*[:=]\s*\S{4,}")),
    ("a connection string with a password", re.compile(r"[a-z][a-z0-9+\-.]*://[^\s:/@]+:[^\s@/]+@", re.I)),
]

_INTERNAL_HOST = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+(?:local|internal|corp|lan|intranet|localdomain|home\.arpa)\b",
    re.I,
)
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IPV6 = re.compile(r"(?<![0-9A-Fa-f:.])[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:.]*(?![0-9A-Fa-f:])")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
# Long mixed strings that look like generated secrets.
_HIGH_ENTROPY = re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9+/_\-]*\d)(?=[A-Za-z0-9+/_\-]*[a-z])"
                           r"(?=[A-Za-z0-9+/_\-]*[A-Z])[A-Za-z0-9+/_\-]{32,}(?![A-Za-z0-9])")


@dataclass
class FilterResult:
    blocked: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        return BLOCK_LINE.format(reasons=", ".join(self.reasons))


def _valid_ipv4(s: str) -> bool:
    try:
        ipaddress.IPv4Address(s)
        return True
    except ValueError:
        return False


def _valid_ipv6(s: str) -> bool:
    try:
        ipaddress.IPv6Address(s)
        return True
    except ValueError:
        return False


def security_filter(text: str) -> FilterResult:
    reasons: list[str] = []
    for label, pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(text) and label not in reasons:
            reasons.append(label)
    if any(_valid_ipv4(m) for m in _IPV4.findall(text)) or any(_valid_ipv6(m) for m in _IPV6.findall(text)):
        reasons.append("an IP address")
    if _MAC.search(text):
        reasons.append("a hardware address")
    if _INTERNAL_HOST.search(text):
        reasons.append("an internal hostname")
    if "a token" not in reasons and _HIGH_ENTROPY.search(text):
        reasons.append("a long secret-like string")
    return FilterResult(blocked=bool(reasons), reasons=reasons)
