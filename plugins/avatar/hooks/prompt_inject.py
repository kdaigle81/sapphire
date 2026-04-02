"""Inject avatar animation instructions into the system prompt."""

import json
import struct
from pathlib import Path

USER_AVATAR_DIR = Path(__file__).parent.parent.parent.parent / "user" / "avatar"


def _get_active_model():
    """Get active model filename from plugin state."""
    try:
        from core.plugin_loader import plugin_loader
        state = plugin_loader.get_plugin_state("avatar")
        return state.get("active_model", "sapphire.glb")
    except Exception:
        return "sapphire.glb"


def _get_track_names(glb_path):
    """Extract animation track names from a GLB file."""
    if not glb_path.exists():
        return []
    try:
        with open(glb_path, 'rb') as f:
            _magic, _version, _length = struct.unpack('<III', f.read(12))
            chunk_len, _chunk_type = struct.unpack('<II', f.read(8))
            gltf = json.loads(f.read(chunk_len).decode('utf-8'))
            return [a.get('name', f'track_{i}') for i, a in enumerate(gltf.get('animations', []))]
    except Exception:
        return []


def prompt_inject(event):
    # Check if prompt injection is enabled
    try:
        from core.plugin_loader import plugin_loader
        state = plugin_loader.get_plugin_state("avatar")
        if not state.get("inject_prompt", True):
            return
    except Exception:
        pass

    model = _get_active_model()
    glb_path = USER_AVATAR_DIR / model
    tracks = _get_track_names(glb_path)
    if not tracks:
        return

    track_list = ', '.join(tracks)
    event.context_parts.append(
        f"\n[Avatar]\n"
        f"You have a 3D animated avatar visible to the user. "
        f"You can trigger animations by including <<avatar: trackname>> in your responses. "
        f"Available tracks: {track_list}. "
        f"Use these naturally to express yourself — wave when greeting, "
        f"show happy when celebrating, use attention when something catches your interest. "
        f"The tags are visible in chat as part of your expression. Don't overuse them."
    )
