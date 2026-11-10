import json
from pathlib import Path

import pytest

from gates import security_filter

CASES = [json.loads(l) for l in (Path(__file__).parent / "gate_cases.jsonl").read_text().splitlines() if l.strip()]


@pytest.mark.parametrize("case", [c for c in CASES if c["expected"] == "blocked"], ids=lambda c: c["message"][:40])
def test_security_cases_blocked(case):
    assert security_filter(case["message"]).blocked


@pytest.mark.parametrize("case", [c for c in CASES if c["expected"] != "blocked"], ids=lambda c: c["message"][:40])
def test_non_security_cases_pass_filter(case):
    assert not security_filter(case["message"]).blocked, security_filter(case["message"]).reasons


@pytest.mark.parametrize("text", [
    "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
    "token ghp_abcdefghijklmnopqrstuvwxyz0123",
    "AKIAABCDEFGHIJKLMNOP",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
    "api_key = 9f8e7d6c5b4a",
    "the router at fe80::1ff:fe23:4567:890a",
    "device aa:bb:cc:dd:ee:ff",
    "files on nas.home.arpa",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "Xk9pL2mQ7rT4vW8yZ1aB3cD5eF6gH0jK",
])
def test_patterns_block(text):
    assert security_filter(text).blocked


@pytest.mark.parametrize("text", [
    "Version 1.2.3 of the app",
    "It costs $12.50 per month for 3 users",
    "Python 3.10 or later",
    "See https://www.example.com/pricing for details",
    "A cybersecurity training idea for small businesses",
    "Call it at 9.30 on 2026-11-09",
    "Check the score 999.999.999.999",
])
def test_ordinary_text_passes(text):
    assert not security_filter(text).blocked, security_filter(text).reasons


def test_reasons_never_echo_secret():
    fr = security_filter("password: Hunter2024!")
    assert "Hunter2024" not in fr.message
