"""
Rate limiter tests for core/auth.py — check_rate_limit().

Security-critical: if the rate limiter fails, login brute-force is unguarded.
The function is a simple sliding-window counter on a module-level dict, so
we can test it directly without any FastAPI machinery.

The only trick is that it uses time.time() internally and has a pruning
mechanism on a 5-minute cycle. We mock time to test window expiry precisely.

Run with: pytest tests/test_auth_rate_limit.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def clean_rate_state():
    """Reset rate limit state between tests.

    PYTEST PRIMER — autouse
    ───────────────────────
    `autouse=True` means every test in this module uses this fixture
    automatically — no need to name it as a parameter. Useful for global
    setup/teardown in a single file.
    """
    import core.auth as auth
    auth._rate_limits.clear()
    auth._last_prune = 0.0
    yield
    auth._rate_limits.clear()


def test_allows_requests_under_limit():
    from core.auth import check_rate_limit, RATE_LIMIT_MAX
    ip = "10.0.0.1"
    for _ in range(RATE_LIMIT_MAX - 1):
        assert check_rate_limit(ip) is False  # not limited


def test_blocks_at_limit():
    from core.auth import check_rate_limit, RATE_LIMIT_MAX
    ip = "10.0.0.2"
    for _ in range(RATE_LIMIT_MAX):
        check_rate_limit(ip)
    # Next request should be blocked
    assert check_rate_limit(ip) is True


def test_different_ips_are_independent():
    from core.auth import check_rate_limit, RATE_LIMIT_MAX
    for _ in range(RATE_LIMIT_MAX):
        check_rate_limit("10.0.0.3")
    # Different IP should not be limited
    assert check_rate_limit("10.0.0.4") is False


def test_window_expiry_resets_count():
    """After RATE_LIMIT_WINDOW seconds, old entries should expire and the
    IP should be allowed again."""
    from core.auth import check_rate_limit, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW
    import time as real_time

    ip = "10.0.0.5"
    base_time = 1000000.0

    # Fill up the limit at base_time
    with patch('core.auth.time') as mock_time:
        mock_time.time.return_value = base_time
        for _ in range(RATE_LIMIT_MAX):
            check_rate_limit(ip)
        assert check_rate_limit(ip) is True  # blocked

    # Jump forward past the window
    with patch('core.auth.time') as mock_time:
        mock_time.time.return_value = base_time + RATE_LIMIT_WINDOW + 1
        assert check_rate_limit(ip) is False  # expired, allowed again
