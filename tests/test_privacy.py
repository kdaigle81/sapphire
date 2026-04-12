"""
Privacy whitelist tests — core/privacy.py _is_ip_in_whitelist().

If this function has a bug, network calls bypass the privacy filter and
user data leaks to the internet when privacy mode is on. The function is
pure logic (IP string + whitelist list → bool) with zero I/O, so it's
trivially cheap to test.

Run with: pytest tests/test_privacy.py -v
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.privacy import _is_ip_in_whitelist


DEFAULT_WHITELIST = [
    '127.0.0.1',
    'localhost',
    '192.168.0.0/16',
    '10.0.0.0/8',
    '172.16.0.0/12',
]


# ─── Positive matches ──────────────────────────────────────────────────────

@pytest.mark.parametrize("ip", [
    '127.0.0.1',                # exact match
    '192.168.1.100',            # in 192.168.0.0/16
    '192.168.255.255',          # edge of 192.168.0.0/16
    '10.0.0.1',                 # in 10.0.0.0/8
    '10.255.255.255',           # edge of 10.0.0.0/8
    '172.16.0.1',               # in 172.16.0.0/12
    '172.31.255.255',           # edge of 172.16.0.0/12
], ids=[
    "loopback", "192-subnet", "192-edge",
    "10-subnet", "10-edge", "172-subnet", "172-edge",
])
def test_local_ip_allowed(ip):
    assert _is_ip_in_whitelist(ip, DEFAULT_WHITELIST) is True


# ─── Negative matches ──────────────────────────────────────────────────────

@pytest.mark.parametrize("ip", [
    '8.8.8.8',                  # Google DNS — definitely not local
    '1.1.1.1',                  # Cloudflare — not local
    '172.32.0.1',               # just outside 172.16.0.0/12
    '11.0.0.1',                 # just outside 10.0.0.0/8
    '191.168.1.1',              # looks like 192.168 but isn't
], ids=[
    "google-dns", "cloudflare", "172-outside", "10-outside", "191-typo",
])
def test_public_ip_blocked(ip):
    assert _is_ip_in_whitelist(ip, DEFAULT_WHITELIST) is False


# ─── Edge cases ─────────────────────────────────────────────────────────────

def test_empty_whitelist():
    assert _is_ip_in_whitelist('127.0.0.1', []) is False

def test_invalid_ip_returns_false():
    """Invalid IP strings should return False, not crash."""
    assert _is_ip_in_whitelist('not-an-ip', DEFAULT_WHITELIST) is False

def test_hostname_entries_skipped():
    """Hostname entries (like 'localhost') are skipped by the IP checker.
    They're handled separately by is_allowed_endpoint via hostname matching."""
    # 'localhost' is in DEFAULT_WHITELIST but _is_ip_in_whitelist only does
    # IP/CIDR matching — it should skip the hostname entry gracefully.
    # This IP is NOT in any CIDR range, so result should be False.
    assert _is_ip_in_whitelist('8.8.8.8', ['localhost']) is False

def test_single_ip_exact_match():
    assert _is_ip_in_whitelist('203.0.113.50', ['203.0.113.50']) is True
    assert _is_ip_in_whitelist('203.0.113.51', ['203.0.113.50']) is False

def test_custom_cidr():
    whitelist = ['203.0.113.0/24']
    assert _is_ip_in_whitelist('203.0.113.1', whitelist) is True
    assert _is_ip_in_whitelist('203.0.113.255', whitelist) is True
    assert _is_ip_in_whitelist('203.0.114.1', whitelist) is False
