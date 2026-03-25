"""GLB/GLTF animation track extraction — pure Python, no deps."""

import json
import struct
from pathlib import Path


def extract_tracks(glb_path):
    """Extract animation track info from a GLB file.

    Returns list of dicts: [{"name": str, "duration": float, "channels": int}]
    """
    path = Path(glb_path)
    if not path.exists():
        return []

    try:
        with open(path, 'rb') as f:
            magic, version, length = struct.unpack('<III', f.read(12))
            if magic != 0x46546C67:  # 'glTF'
                return []

            chunk_len, chunk_type = struct.unpack('<II', f.read(8))
            gltf = json.loads(f.read(chunk_len).decode('utf-8'))
    except Exception:
        return []

    tracks = []
    for i, anim in enumerate(gltf.get('animations', [])):
        name = anim.get('name', f'track_{i}')
        channels = len(anim.get('channels', []))

        # Duration from sampler input accessor max values
        max_time = 0
        for s in anim.get('samplers', []):
            acc_idx = s.get('input')
            if acc_idx is not None and acc_idx < len(gltf.get('accessors', [])):
                acc = gltf['accessors'][acc_idx]
                if 'max' in acc:
                    max_time = max(max_time, acc['max'][0])

        tracks.append({
            'name': name,
            'duration': round(max_time, 2),
            'channels': channels,
        })

    return tracks


def get_model_info(glb_path):
    """Get basic model info: meshes, materials, skeleton, tracks."""
    path = Path(glb_path)
    if not path.exists():
        return None

    try:
        with open(path, 'rb') as f:
            magic, version, length = struct.unpack('<III', f.read(12))
            if magic != 0x46546C67:
                return None

            chunk_len, chunk_type = struct.unpack('<II', f.read(8))
            gltf = json.loads(f.read(chunk_len).decode('utf-8'))
    except Exception:
        return None

    skins = gltf.get('skins', [])
    return {
        'meshes': len(gltf.get('meshes', [])),
        'materials': len(gltf.get('materials', [])),
        'textures': len(gltf.get('textures', [])),
        'joints': len(skins[0].get('joints', [])) if skins else 0,
        'tracks': extract_tracks(glb_path),
    }


# Common animation name patterns for auto-mapping
AUTO_MAP = {
    'idle':        ['idle', 'stand', 'standing', 'rest', 'default', 'breathe', 'breathing'],
    'thinking':    ['thinking', 'think', 'ponder', 'concentrate', 'focus'],
    'typing':      ['typing', 'type', 'keyboard', 'defaultanim', 'compose', 'writing'],
    'listening':   ['listening', 'listen', 'hear', 'attentive', 'look', 'lookaround'],
    'speaking':    ['speaking', 'speak', 'talk', 'talking', 'say', 'attention'],
    'toolcall':    ['action', 'use', 'grab', 'reach', 'attention2', 'interact'],
    'happy':       ['happy', 'joy', 'celebrate', 'cheer', 'smile', 'excited', 'victory'],
    'wakeword':    ['alert', 'surprise', 'startle', 'notice', 'attention'],
    'wave':        ['wave', 'greet', 'greeting', 'hello', 'hi', 'bye', 'farewell'],
    'user_typing': ['curious', 'notice', 'perk', 'attentive'],
    'reading':     ['read', 'reading', 'look_down', 'study'],
}


def auto_map_tracks(track_names):
    """Attempt to map avatar states to track names by common patterns.

    Returns dict of {state: track_name} for matches found.
    """
    lower_map = {t.lower(): t for t in track_names}
    result = {}

    for state, patterns in AUTO_MAP.items():
        for pattern in patterns:
            if pattern in lower_map:
                result[state] = lower_map[pattern]
                break

    return result


def build_default_config(track_names):
    """Build a default config for a newly uploaded model."""
    mapped = auto_map_tracks(track_names)

    # Default track map — fill unmapped states with idle or first track
    fallback = mapped.get('idle', track_names[0] if track_names else 'idle')
    track_map = {}
    for state in ['idle', 'thinking', 'typing', 'listening', 'speaking', 'toolcall', 'happy', 'wakeword', 'user_typing', 'reading']:
        track_map[state] = mapped.get(state, fallback)

    # Default idle pool — include idle + any mapped tracks at low weights
    idle_pool = []
    idle_track = track_map.get('idle', fallback)
    idle_pool.append({'track': idle_track, 'weight': 60, 'oneshot': False})

    # Add a few variety tracks if they exist
    for name in track_names:
        if name == idle_track:
            continue
        lower = name.lower()
        if lower in ('defaultanim', 'default'):
            idle_pool.append({'track': name, 'weight': 20, 'oneshot': False})
        elif lower in ('wave', 'greet', 'greeting'):
            idle_pool.append({'track': name, 'weight': 3, 'oneshot': True})
        elif lower in ('happy', 'joy', 'smile'):
            idle_pool.append({'track': name, 'weight': 4, 'oneshot': True})

    greeting = mapped.get('wave', None)

    return {
        'track_map': track_map,
        'idle_pool': idle_pool,
        'greeting_track': greeting,
        'camera': {'x': 0, 'y': 1.3, 'z': 4.4},
        'target': {'x': 0, 'y': 1.1, 'z': 0},
    }
