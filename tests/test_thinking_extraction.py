"""
Tests for thinking block extraction / reconstruction in core/chat/history.py.

_extract_thinking_from_content() parses <think> tags from LLM responses and
_reconstruct_thinking_content() is its inverse. These are used by the history
system to separate reasoning from visible content for display.

The regex in _extract_thinking is non-trivial — it handles:
  - Standard <think>...</think> tags
  - <seed:think>...</seed:think> variants
  - Orphan close tags (thinking at start of content)
  - Orphan open tags (thinking at end, still running)
  - Empty/None input

Run with: pytest tests/test_thinking_extraction.py -v
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.chat.history import _extract_thinking_from_content, _reconstruct_thinking_content


class TestExtractThinking:
    """Each test exercises a different branch in the regex logic."""

    def test_standard_think_tags(self):
        content = "<think>Let me reason about this.</think>The answer is 42."
        clean, thinking = _extract_thinking_from_content(content)
        assert "Let me reason" in thinking
        assert clean == "The answer is 42."
        assert "<think" not in clean

    def test_seed_think_tags(self):
        content = "<seed:think>Reasoning here</seed:think>Visible answer."
        clean, thinking = _extract_thinking_from_content(content)
        assert "Reasoning here" in thinking
        assert clean == "Visible answer."

    def test_multiple_think_blocks(self):
        content = (
            "<think>First thought</think>Middle text "
            "<think>Second thought</think>Final answer"
        )
        clean, thinking = _extract_thinking_from_content(content)
        assert "First thought" in thinking
        assert "Second thought" in thinking
        assert "<think" not in clean
        assert "Middle text" in clean
        assert "Final answer" in clean

    def test_orphan_close_tag(self):
        """Content that starts with thinking (close tag but no open tag).
        Happens when reasoning bleeds into the start of a response."""
        content = "Still thinking...</think>Here's the real answer."
        clean, thinking = _extract_thinking_from_content(content)
        assert "Still thinking" in thinking
        assert "real answer" in clean

    def test_orphan_open_tag(self):
        """Content that ends with an unclosed think tag (still reasoning)."""
        content = "Some answer.<think>I'm still working on this"
        clean, thinking = _extract_thinking_from_content(content)
        assert "still working" in thinking
        assert "Some answer" in clean

    def test_empty_input(self):
        clean, thinking = _extract_thinking_from_content("")
        assert clean == ""
        assert thinking == ""

    def test_none_input(self):
        clean, thinking = _extract_thinking_from_content(None)
        assert clean is None
        assert thinking == ""

    def test_no_thinking_present(self):
        content = "Just a normal response with no thinking."
        clean, thinking = _extract_thinking_from_content(content)
        assert clean == content
        assert thinking == ""

    def test_thinking_only_no_content(self):
        content = "<think>All reasoning, no visible answer.</think>"
        clean, thinking = _extract_thinking_from_content(content)
        assert "All reasoning" in thinking
        assert clean == ""


class TestReconstructThinking:
    def test_with_both_thinking_and_content(self):
        result = _reconstruct_thinking_content("The answer.", "My reasoning")
        assert result.startswith("<think>My reasoning</think>")
        assert "The answer." in result

    def test_with_thinking_only(self):
        result = _reconstruct_thinking_content("", "Just thinking")
        assert "<think>Just thinking</think>" in result

    def test_without_thinking(self):
        result = _reconstruct_thinking_content("Normal response", "")
        assert result == "Normal response"

    def test_none_content_no_thinking(self):
        result = _reconstruct_thinking_content(None, "")
        assert result == ""


class TestRoundTrip:
    """The big one: extract → reconstruct should preserve the thinking content.

    PYTEST PRIMER — parametrize for round-trips
    ────────────────────────────────────────────
    When testing an encode/decode pair, parametrize lets you write ONE test
    that covers many shapes of input. If a new edge case appears, add one
    line to the list instead of a whole new test method.
    """

    @pytest.mark.parametrize("content,thinking", [
        ("The answer is 42.", "Let me think about math."),
        ("", "Only thinking, no answer."),
        ("Multiple paragraphs.\n\nSecond paragraph.", "Deep reasoning\nAcross lines"),
    ], ids=["normal", "thinking-only", "multiline"])
    def test_reconstruct_then_extract_preserves_thinking(self, content, thinking):
        reconstructed = _reconstruct_thinking_content(content, thinking)
        extracted_content, extracted_thinking = _extract_thinking_from_content(reconstructed)
        assert extracted_thinking.strip() == thinking.strip()
        assert extracted_content.strip() == content.strip()
