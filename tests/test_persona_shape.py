"""
Persona structure validation (Breadth-5).

Walks personas.json and asserts every persona has the keys persona_manager
expects. This would have caught the agent-persona seeding bug from Phase 5
(persona missing from existing installs because _load() early-returns when
user/personas/personas.json exists).

Why we walk the CORE personas.json (not user file): the user file is the
authoritative source after first run, but the CORE file is what ships and
what new installs seed from. If a built-in persona is malformed in core,
every new user gets the bug.

Run with: pytest tests/test_persona_shape.py -v
"""
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CORE_PERSONAS_PATH = PROJECT_ROOT / "core" / "personas" / "personas.json"


def load_core_personas():
    """Load and filter out _comment-prefixed metadata keys."""
    data = json.loads(CORE_PERSONAS_PATH.read_text(encoding='utf-8'))
    return {k: v for k, v in data.items() if not k.startswith('_')}


CORE_PERSONAS = load_core_personas()


@pytest.mark.parametrize("persona_key", sorted(CORE_PERSONAS.keys()))
def test_persona_has_top_level_required_fields(persona_key):
    """Every persona must have name, settings, and a settings dict."""
    persona = CORE_PERSONAS[persona_key]
    assert isinstance(persona, dict), f"{persona_key}: persona must be a dict"
    assert "name" in persona, f"{persona_key}: missing 'name'"
    assert "settings" in persona, f"{persona_key}: missing 'settings'"
    assert isinstance(persona["settings"], dict), \
        f"{persona_key}: 'settings' must be a dict"


@pytest.mark.parametrize("persona_key", sorted(CORE_PERSONAS.keys()))
def test_persona_settings_have_core_keys(persona_key):
    """Every persona's settings must include the bare minimum keys.

    These are the ones the chat session manager assumes will be present —
    if they're missing, you get KeyErrors at chat-spawn time.
    """
    settings = CORE_PERSONAS[persona_key]["settings"]
    required = ["prompt", "toolset"]
    for key in required:
        assert key in settings, f"{persona_key}: settings missing '{key}'"


# The "core 4" memory scopes that come from the memory plugin. Every persona
# in core/personas/personas.json declares values for these — they're the
# universally-required ones. Plugin scopes (email, bitcoin, gcal, telegram,
# discord) are NOT required by every persona — see test_known_scope_gap below.
CORE_PERSONA_SCOPE_KEYS = ('memory_scope', 'goal_scope', 'knowledge_scope', 'people_scope')


@pytest.mark.parametrize("persona_key", sorted(CORE_PERSONAS.keys()))
def test_persona_settings_have_core_memory_scopes(persona_key):
    """Every persona must declare values for the core 4 memory scopes.

    These are memory_scope, goal_scope, knowledge_scope, people_scope — the
    scopes from the memory plugin (Phase 4). If a persona is missing one of
    these, switching to that persona will leak whatever value was in the
    previous chat's scope ContextVar.

    Plugin-specific scopes (email, bitcoin, etc.) are tracked separately
    by test_known_scope_gap.
    """
    settings = CORE_PERSONAS[persona_key]["settings"]
    for key in CORE_PERSONA_SCOPE_KEYS:
        assert key in settings, \
            f"{persona_key}: settings missing core memory scope key '{key}'"


def test_agent_persona_has_all_scope_keys():
    """The agent persona must declare ALL scope keys explicitly (including plugin
    scopes set to 'none') because background agents should never silently inherit
    a chat's email/telegram/etc. scope.

    Other personas intentionally OMIT plugin scopes (email, bitcoin, gcal, telegram,
    discord) so they don't override per-chat user configuration when applied.
    """
    from core.chat.function_manager import scope_setting_keys

    agent = CORE_PERSONAS.get("agent")
    assert agent is not None
    settings = agent["settings"]
    missing = [k for k in scope_setting_keys() if k not in settings]
    assert not missing, \
        f"Agent persona missing scope keys (agents must opt out explicitly): {missing}"


def test_agent_persona_exists_in_core():
    """The 'agent' persona is required for spawn_agent to have a sane default.

    Phase 5 added this. If it's missing from core personas.json, new installs
    won't have a fallback for background agent work.
    """
    assert "agent" in CORE_PERSONAS, \
        "core personas.json missing 'agent' persona — spawn_agent default broken"
    agent = CORE_PERSONAS["agent"]
    assert agent["settings"].get("prompt") == "agent", \
        "agent persona must reference the 'agent' prompt file"
