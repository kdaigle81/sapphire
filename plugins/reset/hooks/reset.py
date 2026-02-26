# Reset plugin — clears current chat history
#
# Triggered by: "reset", "reset chat", "clear chat", "clear history"
# Bypasses LLM entirely — instant wipe + confirmation.

import logging

logger = logging.getLogger(__name__)


def pre_chat(event):
    """Clear the current chat's history."""
    system = event.metadata.get("system")

    if system and hasattr(system, "llm_chat"):
        session = system.llm_chat.session_manager
        chat_name = session.get_active_chat_name() or "chat"
        try:
            session.clear_history()
            logger.info(f"[RESET] Cleared history for '{chat_name}'")
            event.response = f"Chat '{chat_name}' has been reset."
        except Exception as e:
            logger.error(f"[RESET] Failed: {e}")
            event.response = f"Reset failed: {e}"
    else:
        event.response = "Reset failed — system not available."

    event.skip_llm = True
    event.stop_propagation = True
