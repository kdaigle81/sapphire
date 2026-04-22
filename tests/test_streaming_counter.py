"""Regression guard for 2026-04-22 H4 follow-up — `_is_streaming` counter.

Pre-fix: `_is_streaming` was a single bool on ChatSessionManager. H4 moved
per-stream state (cancel_flag, ephemeral, current_stream) onto each
StreamingChat instance, but this shared bool stayed. Two concurrent streams
on the same chat had the first finisher set False while the second was
still running, defeating the guards in append_messages_to_chat /
delete_chat / save-ordering. Mid-turn writes could land between a stream's
tool_call and tool_result message, breaking provider conversation pairing.

Post-fix: bool replaced with a counter. begin_streaming() increments,
end_streaming() decrements. `_is_streaming` property returns `count > 0`.
Legacy setter kept for back-compat with existing tests.
"""
import threading
import pytest


@pytest.fixture
def sm():
    """Stand up a ChatSessionManager with just the streaming-state plumbing
    (avoid full DB init which would require migration scaffolding)."""
    from core.chat.history import ChatSessionManager
    inst = ChatSessionManager.__new__(ChatSessionManager)
    inst._lock = threading.RLock()
    inst._streaming_count = 0
    return inst


def test_counter_starts_at_zero_reads_false(sm):
    assert sm._streaming_count == 0
    assert sm._is_streaming is False


def test_begin_streaming_flips_to_true(sm):
    sm.begin_streaming()
    assert sm._streaming_count == 1
    assert sm._is_streaming is True


def test_two_concurrent_streams_stay_true_until_both_end(sm):
    """The scenario H4's partial fix missed."""
    sm.begin_streaming()       # Stream A starts
    sm.begin_streaming()       # Stream B starts (same chat)
    assert sm._is_streaming is True
    assert sm._streaming_count == 2

    sm.end_streaming()         # Stream A finishes — WAS the bug: flag flipped False here
    assert sm._is_streaming is True, \
        "Counter must stay positive while stream B is still running — this is the H4 regression fix"
    assert sm._streaming_count == 1

    sm.end_streaming()         # Stream B finishes
    assert sm._is_streaming is False
    assert sm._streaming_count == 0


def test_end_streaming_floors_at_zero(sm):
    """Defensive — double-end shouldn't go negative."""
    sm.end_streaming()
    assert sm._streaming_count == 0
    sm.end_streaming()
    assert sm._streaming_count == 0


def test_legacy_setter_true_bumps_to_one(sm):
    """Back-compat: _is_streaming = True still works for existing tests."""
    sm._is_streaming = True
    assert sm._streaming_count == 1
    assert sm._is_streaming is True


def test_legacy_setter_false_resets_to_zero(sm):
    """Back-compat: _is_streaming = False resets regardless of counter state."""
    sm.begin_streaming()
    sm.begin_streaming()
    assert sm._streaming_count == 2
    sm._is_streaming = False
    # Setter is blunt — resets to 0 regardless. Tests that use this pattern
    # are simulating single-stream scenarios; they don't care about counter
    # precision. Real writers use begin/end_streaming() for correct counting.
    assert sm._streaming_count == 0
    assert sm._is_streaming is False


def test_concurrent_begin_from_threads(sm):
    """Counter must be atomic under concurrent increment from multiple threads.
    Lock covers the read-modify-write."""
    N = 50
    barrier = threading.Barrier(N)

    def runner():
        barrier.wait()
        sm.begin_streaming()

    threads = [threading.Thread(target=runner) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sm._streaming_count == N, \
        f"Atomic increment failed under thread pressure: got {sm._streaming_count}, expected {N}"
    assert sm._is_streaming is True


def test_concurrent_end_from_threads(sm):
    """Counter must also atomically decrement."""
    N = 50
    for _ in range(N):
        sm.begin_streaming()
    assert sm._streaming_count == N

    barrier = threading.Barrier(N)

    def runner():
        barrier.wait()
        sm.end_streaming()

    threads = [threading.Thread(target=runner) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sm._streaming_count == 0
    assert sm._is_streaming is False


def test_begin_end_mixed_concurrent(sm):
    """Interleaved begin + end from threads — count must land back at 0."""
    N = 100
    barrier = threading.Barrier(2 * N)

    def begin_then_end():
        barrier.wait()
        sm.begin_streaming()
        sm.end_streaming()

    def end_then_begin():
        barrier.wait()
        # Noop end (count may be 0), then begin. Some will decrement from 0
        # (floored), others will match a begin. End state depends on order
        # but final count shouldn't be negative.
        sm.end_streaming()
        sm.begin_streaming()

    threads = [threading.Thread(target=begin_then_end) for _ in range(N)]
    threads += [threading.Thread(target=end_then_begin) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Count must be non-negative. Exact value depends on interleaving of
    # begins vs ends. The key invariant: never negative.
    assert sm._streaming_count >= 0
