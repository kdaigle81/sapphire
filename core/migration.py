"""Data migrations for Sapphire. Run automatically on startup."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

USER_DIR = Path(__file__).parent.parent / "user"
USER_PROMPTS_DIR = USER_DIR / "prompts"


def run_all():
    """Run all pending migrations."""
    migrate_persona_to_character()
    migrate_stt_to_provider()
    migrate_tts_to_provider()


def migrate_persona_to_character():
    """Rename 'persona' component key to 'character' in user prompt JSON files.

    Affects:
    - prompt_pieces.json: components.persona -> components.character
    - prompt_pieces.json: scenario_presets.*.persona -> *.character
    - Any user-saved prompt JSON with components.persona
    """
    _migrate_prompt_pieces()
    _migrate_user_prompts()


def _migrate_prompt_pieces():
    """Migrate prompt_pieces.json persona -> character."""
    path = USER_PROMPTS_DIR / "prompt_pieces.json"
    if not path.exists():
        return

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        changed = False

        # Rename components.persona -> components.character
        components = data.get("components", {})
        if "persona" in components and "character" not in components:
            components["character"] = components.pop("persona")
            changed = True

        # Rename persona key in scenario_presets
        for preset_name, preset in data.get("scenario_presets", {}).items():
            if isinstance(preset, dict) and "persona" in preset and "character" not in preset:
                preset["character"] = preset.pop("persona")
                changed = True

        if changed:
            tmp = path.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(path)
            logger.info("Migrated prompt_pieces.json: persona -> character")
    except Exception as e:
        logger.error(f"Migration failed for prompt_pieces.json: {e}")


def _migrate_user_prompts():
    """Migrate any user-saved prompt files that have persona in components."""
    prompts_dir = USER_PROMPTS_DIR
    if not prompts_dir.exists():
        return

    for path in prompts_dir.glob("*.json"):
        if path.name in ("prompt_pieces.json", "prompt_monoliths.json", "prompt_spices.json"):
            continue

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            changed = False

            # Handle single prompt objects and collections
            prompts_to_check = []
            if isinstance(data, dict):
                if "components" in data:
                    prompts_to_check.append(data)
                else:
                    # Could be a dict of prompts
                    for v in data.values():
                        if isinstance(v, dict) and "components" in v:
                            prompts_to_check.append(v)

            for prompt in prompts_to_check:
                comps = prompt.get("components", {})
                if isinstance(comps, dict) and "persona" in comps and "character" not in comps:
                    comps["character"] = comps.pop("persona")
                    changed = True

            if changed:
                tmp = path.with_suffix('.tmp')
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                tmp.replace(path)
                logger.info(f"Migrated {path.name}: persona -> character")
        except Exception as e:
            logger.warning(f"Could not migrate {path.name}: {e}")


def migrate_stt_to_provider():
    """Migrate STT_ENABLED + STT_ENGINE → STT_PROVIDER.

    If user has STT_ENABLED in their settings but no STT_PROVIDER,
    convert: enabled=true → provider='faster_whisper', enabled=false → provider='none'.
    Removes old STT_ENABLED and STT_ENGINE keys from user settings.
    """
    settings_path = USER_DIR / "settings.json"
    if not settings_path.exists():
        return

    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        stt = data.get('stt', {})
        if not isinstance(stt, dict):
            stt = {}

        # Already migrated?
        if 'STT_PROVIDER' in stt:
            # Clean up root-level STT_ENABLED if present (legacy wizard path)
            if 'STT_ENABLED' in data or 'STT_ENGINE' in data:
                data.pop('STT_ENABLED', None)
                data.pop('STT_ENGINE', None)
                data['stt'] = stt
                tmp = settings_path.with_suffix('.tmp')
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                tmp.replace(settings_path)
                logger.info("Cleaned up root-level STT keys (already migrated)")
            return

        # Check both nested (stt.STT_ENABLED) and root-level (STT_ENABLED)
        was_enabled = stt.get('STT_ENABLED', data.get('STT_ENABLED', False))
        engine = stt.get('STT_ENGINE', data.get('STT_ENGINE', 'faster_whisper'))

        # Nothing to migrate?
        if 'STT_ENABLED' not in stt and 'STT_ENABLED' not in data and 'STT_ENGINE' not in stt:
            return

        if 'STT_PROVIDER' not in stt:
            stt['STT_PROVIDER'] = engine if was_enabled else 'none'
        stt.pop('STT_ENABLED', None)
        stt.pop('STT_ENGINE', None)
        data.pop('STT_ENABLED', None)
        data.pop('STT_ENGINE', None)
        data['stt'] = stt

        tmp = settings_path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(settings_path)
        logger.info(f"Migrated STT settings: enabled={was_enabled} engine={engine} → provider={stt['STT_PROVIDER']}")
    except Exception as e:
        logger.error(f"STT settings migration failed: {e}")


def migrate_tts_to_provider():
    """Migrate TTS_ENABLED → TTS_PROVIDER.

    If user has TTS_ENABLED but no TTS_PROVIDER,
    convert: enabled=true → provider='kokoro', enabled=false → provider='none'.
    Removes old TTS_ENABLED key from user settings.
    """
    settings_path = USER_DIR / "settings.json"
    if not settings_path.exists():
        return

    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        tts = data.get('tts', {})
        if not isinstance(tts, dict):
            tts = {}

        # Already migrated?
        if 'TTS_PROVIDER' in tts:
            # Clean up root-level TTS_ENABLED if present
            if 'TTS_ENABLED' in data:
                data.pop('TTS_ENABLED', None)
                data['tts'] = tts
                tmp = settings_path.with_suffix('.tmp')
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                tmp.replace(settings_path)
                logger.info("Cleaned up root-level TTS keys (already migrated)")
            return

        # Check both nested and root-level
        was_enabled = tts.get('TTS_ENABLED', data.get('TTS_ENABLED', False))

        # Nothing to migrate?
        if 'TTS_ENABLED' not in tts and 'TTS_ENABLED' not in data:
            return

        if 'TTS_PROVIDER' not in tts:
            tts['TTS_PROVIDER'] = 'kokoro' if was_enabled else 'none'
        tts.pop('TTS_ENABLED', None)
        data.pop('TTS_ENABLED', None)
        data['tts'] = tts

        tmp = settings_path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(settings_path)
        logger.info(f"Migrated TTS settings: enabled={was_enabled} → provider={tts['TTS_PROVIDER']}")
    except Exception as e:
        logger.error(f"TTS settings migration failed: {e}")
