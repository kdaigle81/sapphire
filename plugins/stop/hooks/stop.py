# Stop plugin — halts TTS and cancels LLM generation
#
# Triggered by exact voice commands: "stop", "halt", "be quiet", "shut up"
# Bypasses LLM entirely for instant response.

import logging
from core.event_bus import publish, Events

logger = logging.getLogger(__name__)


def pre_chat(event):
    """Cancel TTS playback and streaming generation."""
    system = event.metadata.get("system")

    if system:
        # Stop TTS playback (server-side)
        if hasattr(system, "tts") and system.tts:
            try:
                system.tts.stop()
                logger.info("[STOP] TTS stopped")
            except Exception as e:
                logger.warning(f"[STOP] TTS stop failed: {e}")

        # Broadcast to web UI clients to stop browser TTS
        publish(Events.TTS_STOPPED)

        # Cancel streaming generation
        if hasattr(system, "llm_chat") and system.llm_chat:
            streaming = getattr(system.llm_chat, "streaming_chat", None)
            if streaming:
                streaming.cancel_flag = True
                logger.info("[STOP] Generation cancelled")

    event.skip_llm = True
    event.ephemeral = True
    event.response = "Stopped."
    event.stop_propagation = True
