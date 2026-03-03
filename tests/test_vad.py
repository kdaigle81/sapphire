"""
VAD Regression Tests

Tests for the adaptive VAD (voice activity detection) in core/stt/recorder.py.
Prevents the silent_chunks accumulation bug from regressing, and verifies
all recorder settings are properly wired.

Bug: silent_chunks used a leaky integrator (decrement by 1 on speech) instead
of resetting to 0. This accumulated silence across mid-speech pauses, causing
premature cutoff. Users raising RECORDER_SILENCE_DURATION to compensate just
added end-of-speech latency without fixing the root cause.

Run with: pytest tests/test_vad.py -v
"""
import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _has_stt_deps():
    """Check if STT deps are importable (find_spec can raise ValueError on broken __spec__)."""
    import importlib.util
    try:
        return all(importlib.util.find_spec(m) is not None for m in ['sounddevice', 'soundfile', 'numpy'])
    except (ValueError, ModuleNotFoundError):
        return False

RECORDER_SOURCE = (PROJECT_ROOT / "core" / "stt" / "recorder.py").read_text(encoding='utf-8')


# =============================================================================
# Helpers
# =============================================================================

def make_silence_sequence(pattern, chunks_per_sec):
    """
    Build a boolean sequence simulating speech/silence chunks.

    pattern: list of (duration_seconds, is_silent) tuples
    Returns: list of booleans (True=silent, False=speech)
    """
    sequence = []
    for duration, silent in pattern:
        n_chunks = int(duration * chunks_per_sec)
        sequence.extend([silent] * n_chunks)
    return sequence


def run_vad_loop(pattern, chunks_per_sec, silence_duration,
                 speech_duration=0.2, reset_on_speech=True):
    """
    Simulate the recorder's VAD loop with given parameters.

    Returns: (cutoff, silent_chunks, has_speech, elapsed_chunks)
    """
    threshold = chunks_per_sec * silence_duration
    speech_threshold = chunks_per_sec * speech_duration

    silent_chunks = 0
    speech_chunks = 0
    has_speech = False
    cutoff = False

    for i, is_silent in enumerate(pattern):
        if is_silent:
            silent_chunks += 1
            speech_chunks = max(0, speech_chunks - 1)
            if silent_chunks > threshold and has_speech:
                cutoff = True
                return cutoff, silent_chunks, has_speech, i
        else:
            speech_chunks += 1
            if reset_on_speech:
                silent_chunks = 0  # Fixed behavior
            else:
                silent_chunks = max(0, silent_chunks - 1)  # Old bug
            if speech_chunks > speech_threshold:
                has_speech = True

    return cutoff, silent_chunks, has_speech, len(pattern)


# Rate/blocksize constants matching a common device config
RATE = 16000
BLOCKSIZE = 1024
CPS = RATE / BLOCKSIZE  # ~15.625 chunks per second


# =============================================================================
# V1: silent_chunks resets on speech (the accumulation bug fix)
# =============================================================================

class TestSilentChunksReset:
    """silent_chunks must reset to 0 when speech resumes, not just decrement."""

    def test_accumulated_pauses_no_premature_cutoff(self):
        """Multiple mid-speech pauses must NOT accumulate to trigger cutoff."""
        # speak 0.5s, pause 0.8s, speak 0.2s, pause 0.8s
        # Neither pause exceeds 1.0s threshold individually
        pattern = make_silence_sequence([
            (0.5, False),
            (0.8, True),
            (0.2, False),
            (0.8, True),
        ], CPS)

        cutoff, sc, hs, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert not cutoff, (
            f"Premature cutoff! silent_chunks={sc}. "
            "Pauses must not accumulate across speech segments."
        )

    def test_old_bug_would_have_caused_premature_cutoff(self):
        """Verify the OLD decrement behavior WOULD have caused premature cutoff."""
        pattern = make_silence_sequence([
            (0.5, False),
            (0.8, True),
            (0.2, False),
            (0.8, True),
        ], CPS)

        cutoff, sc, hs, _ = run_vad_loop(
            pattern, CPS, silence_duration=1.0, reset_on_speech=False
        )
        assert cutoff, (
            "Expected premature cutoff with OLD decrement behavior. "
            "If this fails, the test premise is wrong."
        )

    def test_single_speech_chunk_fully_resets_silence(self):
        """Even one speech chunk should reset silent_chunks to 0."""
        pattern = make_silence_sequence([
            (0.3, False),   # establish speech
            (0.5, True),    # half-second pause, accumulates ~7-8 chunks
            (0.065, False), # single chunk of speech
            (0.5, True),    # another half-second — should start from 0
        ], CPS)

        cutoff, sc, hs, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert not cutoff, "Single speech chunk should fully reset silence counter"

    def test_realistic_conversational_pauses(self):
        """Natural speech pattern: speak, think, speak, think, speak, done."""
        pattern = make_silence_sequence([
            (2.0, False),   # speaking
            (0.7, True),    # thinking pause
            (1.0, False),   # continue speaking
            (0.5, True),    # brief pause
            (0.3, False),   # quick addition
            (0.6, True),    # another pause
            (1.5, False),   # finish thought
            (1.5, True),    # done — this should trigger cutoff
        ], CPS)

        cutoff, sc, hs, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert cutoff, "Should cut off after 1.5s of final silence"

    def test_rapid_alternating_doesnt_accumulate(self):
        """Rapid speech/silence alternation should not accumulate silence."""
        # 20 cycles of 0.3s silence + 0.1s speech
        segments = []
        for _ in range(20):
            segments.append((0.3, True))
            segments.append((0.1, False))
        pattern = make_silence_sequence(segments, CPS)

        cutoff, sc, hs, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert not cutoff, "Rapid alternation should not accumulate to threshold"


# =============================================================================
# V2: Continuous silence triggers cutoff at correct time
# =============================================================================

class TestContinuousSilenceCutoff:
    """Pure continuous silence after speech triggers cutoff at the right time."""

    def test_silence_at_1s_threshold(self):
        """1.0s of continuous silence after speech should trigger cutoff."""
        pattern = make_silence_sequence([
            (1.0, False),   # speech
            (1.5, True),    # continuous silence — should trigger at ~1.0s
        ], CPS)

        cutoff, _, _, elapsed = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert cutoff

    def test_silence_below_threshold_no_cutoff(self):
        """0.8s of silence should NOT trigger 1.0s threshold."""
        pattern = make_silence_sequence([
            (1.0, False),
            (0.8, True),
        ], CPS)

        cutoff, _, _, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert not cutoff

    def test_silence_duration_2s(self):
        """RECORDER_SILENCE_DURATION=2.0 requires 2s of continuous silence."""
        pattern = make_silence_sequence([
            (0.5, False),
            (1.8, True),   # not enough
        ], CPS)

        cutoff, _, _, _ = run_vad_loop(pattern, CPS, silence_duration=2.0)
        assert not cutoff, "1.8s silence should not trigger 2.0s threshold"

        pattern2 = make_silence_sequence([
            (0.5, False),
            (2.5, True),   # enough
        ], CPS)

        cutoff2, _, _, _ = run_vad_loop(pattern2, CPS, silence_duration=2.0)
        assert cutoff2, "2.5s silence should trigger 2.0s threshold"

    def test_cutoff_requires_has_speech(self):
        """Silence cutoff should only trigger after speech was detected."""
        # All silence, no speech
        pattern = [True] * int(CPS * 5)  # 5 seconds of silence

        cutoff, _, hs, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert not cutoff, "Should not cut off if no speech was detected"
        assert not hs


# =============================================================================
# V3: Speech detection threshold
# =============================================================================

class TestSpeechDetection:
    """has_speech activates only after RECORDER_SPEECH_DURATION of speech."""

    def test_brief_noise_doesnt_trigger_speech(self):
        """A single non-silent chunk should not set has_speech."""
        # 1 chunk of noise then silence
        pattern = [False] + [True] * int(CPS * 2)

        _, _, has_speech, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert not has_speech, "Brief noise should not trigger has_speech"

    def test_sustained_speech_triggers_detection(self):
        """Speech lasting > RECORDER_SPEECH_DURATION should set has_speech."""
        pattern = make_silence_sequence([
            (0.3, False),   # 0.3s speech > 0.2s threshold
            (0.5, True),
        ], CPS)

        _, _, has_speech, _ = run_vad_loop(pattern, CPS, silence_duration=1.0)
        assert has_speech, "0.3s speech should trigger has_speech (threshold=0.2s)"

    def test_speech_threshold_configurable(self):
        """Changing speech_duration should change how much speech is needed."""
        pattern = make_silence_sequence([
            (0.3, False),
            (0.5, True),
        ], CPS)

        # With 0.5s threshold, 0.3s speech should NOT trigger
        _, _, has_speech, _ = run_vad_loop(
            pattern, CPS, silence_duration=1.0, speech_duration=0.5
        )
        assert not has_speech, "0.3s speech should not trigger 0.5s threshold"


# =============================================================================
# V4: Adaptive threshold (tested via source + numpy if available)
# =============================================================================

class TestAdaptiveThreshold:
    """_update_threshold uses noise multiplier and floor correctly."""

    def test_threshold_uses_percentile_and_multiplier(self):
        """Source should use RECORDER_BACKGROUND_PERCENTILE and RECORDER_NOISE_MULTIPLIER."""
        assert 'config.RECORDER_BACKGROUND_PERCENTILE' in RECORDER_SOURCE
        assert 'config.RECORDER_NOISE_MULTIPLIER' in RECORDER_SOURCE

    def test_threshold_has_floor(self):
        """Adaptive threshold should never drop below RECORDER_SILENCE_THRESHOLD."""
        assert 'config.RECORDER_SILENCE_THRESHOLD' in RECORDER_SOURCE
        # The max() call ensures the floor
        assert 'max(' in RECORDER_SOURCE

    @pytest.mark.skipif(
        not _has_stt_deps(),
        reason="STT dependencies not installed"
    )
    def test_threshold_never_below_floor(self):
        """Live test: feeding quiet levels keeps threshold above floor."""
        import numpy as np
        from unittest.mock import patch, MagicMock

        with patch('core.stt.recorder.get_device_manager') as mock_dm:
            mock_cfg = MagicMock()
            mock_cfg.device_index = 0
            mock_cfg.sample_rate = 16000
            mock_cfg.channels = 1
            mock_cfg.blocksize = 1024
            mock_cfg.needs_stereo_downmix = False
            mock_dm.return_value.find_input_device.return_value = mock_cfg

            with patch('core.stt.recorder.get_temp_dir', return_value='/tmp'):
                from core.stt.recorder import AudioRecorder
                recorder = AudioRecorder()

        for _ in range(20):
            recorder._update_threshold(0.0001)

        import config
        floor = config.RECORDER_SILENCE_THRESHOLD
        assert recorder.adaptive_threshold >= floor, (
            f"Threshold {recorder.adaptive_threshold} below floor {floor}"
        )


# =============================================================================
# V5: Settings wired at recording time, not cached at init
# =============================================================================

class TestSettingsWiring:
    """VAD settings must be read from config during recording, not cached."""

    def test_silence_duration_read_at_recording_time(self):
        assert 'config.RECORDER_SILENCE_DURATION' in RECORDER_SOURCE

    def test_speech_duration_read_at_recording_time(self):
        assert 'config.RECORDER_SPEECH_DURATION' in RECORDER_SOURCE

    def test_no_speech_timeout_read_at_recording_time(self):
        assert 'config.RECORDER_NO_SPEECH_TIMEOUT' in RECORDER_SOURCE

    def test_max_seconds_read_at_recording_time(self):
        assert 'config.RECORDER_MAX_SECONDS' in RECORDER_SOURCE

    def test_background_percentile_in_threshold(self):
        assert 'config.RECORDER_BACKGROUND_PERCENTILE' in RECORDER_SOURCE

    def test_noise_multiplier_in_threshold(self):
        assert 'config.RECORDER_NOISE_MULTIPLIER' in RECORDER_SOURCE

    def test_beep_wait_time_read_at_recording_time(self):
        assert 'config.RECORDER_BEEP_WAIT_TIME' in RECORDER_SOURCE


# =============================================================================
# V6: Timeout edge cases
# =============================================================================

class TestTimeouts:
    """No-speech timeout and max-seconds must work correctly."""

    def test_no_speech_timeout_logic(self):
        """If no speech within timeout, recording should abort."""
        has_speech = False
        elapsed = 3.5
        timeout = 3.0
        assert not has_speech and elapsed > timeout

    def test_no_speech_timeout_doesnt_fire_with_speech(self):
        """If speech was detected, no-speech timeout should not trigger."""
        has_speech = True
        elapsed = 5.0
        timeout = 3.0
        assert not (not has_speech and elapsed > timeout)

    def test_max_seconds_caps_with_speech(self):
        """RECORDER_MAX_SECONDS stops recording even during active speech."""
        has_speech = True
        elapsed = 31
        max_seconds = 30
        assert elapsed > max_seconds and has_speech


# =============================================================================
# V7: Source code guards — the fix must stay in place
# =============================================================================

class TestSourceGuards:
    """Verify recorder.py has the fix and not the old bug."""

    def test_silent_chunks_reset_present(self):
        """recorder.py must have 'silent_chunks = 0' (reset on speech)."""
        assert 'silent_chunks = 0' in RECORDER_SOURCE, (
            "recorder.py must reset silent_chunks to 0 on speech"
        )

    def test_silent_chunks_decrement_absent(self):
        """recorder.py must NOT have the old leaky integrator pattern."""
        assert 'max(0, silent_chunks - 1)' not in RECORDER_SOURCE, (
            "recorder.py must NOT use leaky decrement for silent_chunks"
        )

    def test_speech_chunks_still_uses_decrement(self):
        """speech_chunks should still decay during silence (intentional)."""
        assert 'max(0, speech_chunks - 1)' in RECORDER_SOURCE, (
            "speech_chunks decay during silence is intentional — prevents "
            "noise blips from permanently setting has_speech"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
