# core/hooks.py — Plugin hook system for Sapphire
#
# Priority-ordered hook runner with mutable event objects.
# Plugins register handlers for named hooks; the runner fires them
# in priority order with error isolation.

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HookEvent:
    """Mutable event object passed through hook handlers.

    Handlers can mutate any field. Changes are visible to subsequent handlers.

    Fields:
        input: User's message text (mutable by pre_chat hooks)
        skip_llm: Set True to bypass LLM entirely (voice commands, cached responses)
        response: Direct response text when skip_llm is True
        context_parts: Append strings to inject into system prompt (prompt_inject hooks)
        stop_propagation: Set True to prevent lower-priority hooks from firing
        config: System config object (read-only by convention)
        metadata: Arbitrary data plugins can pass between hooks
    """
    input: str = ""
    skip_llm: bool = False
    response: Optional[str] = None
    context_parts: List[str] = field(default_factory=list)
    stop_propagation: bool = False
    config: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class HookRunner:
    """Priority-ordered hook dispatcher with error isolation.

    Priority bands:
        System plugins (0-99): Always fire first
        User plugins (100-199): Fire after system plugins
        Default priority: 50

    Guidelines within each band:
        0-19:  Critical intercepts (stop, security)
        20-49: Input modification (translation, formatting)
        50-79: Context enrichment (prompt injection, state)
        80-99: Observation (logging, analytics)
    """

    def __init__(self):
        # {hook_name: [(priority, handler, plugin_name, voice_match)]}
        self._hooks: Dict[str, List[tuple]] = {}
        self._sorted: Dict[str, bool] = {}

    def register(self, hook_name: str, handler: Callable, priority: int = 50,
                 plugin_name: str = "", voice_match: dict = None):
        """Register a handler for a hook point.

        Args:
            hook_name: Hook to register for (pre_chat, prompt_inject, etc.)
            handler: Callable that takes a HookEvent
            priority: 0-199, lower fires first
            plugin_name: For logging and unregistration
            voice_match: Optional dict with 'triggers' list and 'match' type
                         for voice command pre-filtering (exact/starts_with/contains/regex)
        """
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append((priority, handler, plugin_name, voice_match))
        self._sorted[hook_name] = False
        logger.info(f"[HOOKS] Registered {plugin_name}:{handler.__name__} on '{hook_name}' (priority {priority})")

    def unregister(self, hook_name: str, plugin_name: str):
        """Remove all handlers for a plugin from a specific hook."""
        if hook_name in self._hooks:
            before = len(self._hooks[hook_name])
            self._hooks[hook_name] = [
                h for h in self._hooks[hook_name] if h[2] != plugin_name
            ]
            removed = before - len(self._hooks[hook_name])
            if removed:
                self._sorted[hook_name] = False
                logger.info(f"[HOOKS] Unregistered {removed} handler(s) for '{plugin_name}' from '{hook_name}'")

    def unregister_plugin(self, plugin_name: str):
        """Remove all handlers for a plugin from all hooks."""
        for hook_name in list(self._hooks.keys()):
            self.unregister(hook_name, plugin_name)

    def _ensure_sorted(self, hook_name: str):
        if not self._sorted.get(hook_name, True):
            self._hooks[hook_name].sort(key=lambda h: h[0])
            self._sorted[hook_name] = True

    def _check_voice_match(self, voice_match: dict, input_text: str) -> bool:
        """Check if input matches voice command triggers.

        Returns True if no voice_match (regular hook, always fires)
        or if input matches the declared pattern.
        """
        if not voice_match:
            return True

        triggers = voice_match.get("triggers", [])
        match_type = voice_match.get("match", "exact")
        input_lower = input_text.lower().strip()

        if match_type == "exact":
            return input_lower in [t.lower() for t in triggers]
        elif match_type == "starts_with":
            return any(input_lower.startswith(t.lower()) for t in triggers)
        elif match_type == "contains":
            return any(t.lower() in input_lower for t in triggers)
        elif match_type == "regex":
            return any(re.search(t, input_text, re.IGNORECASE) for t in triggers)

        return False

    def fire(self, hook_name: str, event: HookEvent) -> HookEvent:
        """Fire all handlers for a hook in priority order.

        Each handler receives the mutable event object. Errors in individual
        handlers are logged and skipped — a buggy plugin never crashes the pipeline.

        Args:
            hook_name: Which hook to fire (pre_chat, prompt_inject, etc.)
            event: Mutable event object

        Returns:
            The (possibly mutated) event object
        """
        handlers = self._hooks.get(hook_name)
        if not handlers:
            return event

        self._ensure_sorted(hook_name)

        for priority, handler, plugin_name, voice_match in handlers:
            if not self._check_voice_match(voice_match, event.input):
                continue

            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"[HOOKS] Error in {plugin_name}:{handler.__name__} on '{hook_name}': {e}",
                    exc_info=True
                )
                continue

            if event.stop_propagation:
                logger.info(f"[HOOKS] Propagation stopped by {plugin_name} on '{hook_name}'")
                break

        return event

    def get_handlers(self, hook_name: str) -> list:
        """Get registered handlers for a hook (for debugging/introspection)."""
        self._ensure_sorted(hook_name)
        return list(self._hooks.get(hook_name, []))

    def has_handlers(self, hook_name: str) -> bool:
        """Check if any handlers are registered for a hook."""
        return bool(self._hooks.get(hook_name))

    def clear(self):
        """Remove all handlers. Used for testing."""
        self._hooks.clear()
        self._sorted.clear()


# Singleton
hook_runner = HookRunner()
