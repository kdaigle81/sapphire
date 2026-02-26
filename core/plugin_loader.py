# core/plugin_loader.py — Plugin discovery, loading, and lifecycle
#
# Scans plugins/ and user/plugins/ for plugin.json manifests.
# Registers hooks, voice commands, and (later) tools/web/schedule.

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from core.hooks import hook_runner

logger = logging.getLogger(__name__)

# Plugin search paths (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent
SYSTEM_PLUGINS_DIR = PROJECT_ROOT / "plugins"
USER_PLUGINS_DIR = PROJECT_ROOT / "user" / "plugins"
PLUGIN_STATE_DIR = PROJECT_ROOT / "user" / "plugin_state"

# Where enabled/disabled state is stored
USER_PLUGINS_JSON = PROJECT_ROOT / "user" / "webui" / "plugins.json"
STATIC_PLUGINS_JSON = PROJECT_ROOT / "interfaces" / "web" / "static" / "plugins" / "plugins.json"


class PluginState:
    """Simple JSON key-value store for plugin data.

    Each plugin gets its own file at user/plugin_state/{name}.json.
    Authors who need more can bring their own SQLite.
    """

    def __init__(self, plugin_name: str):
        self._name = plugin_name
        self._path = PLUGIN_STATE_DIR / f"{plugin_name}.json"
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[PLUGIN-STATE] Failed to load {self._path}: {e}")
        return {}

    def _save(self):
        PLUGIN_STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def save(self, key: str, value):
        self._data[key] = value
        self._save()

    def delete(self, key: str):
        self._data.pop(key, None)
        self._save()

    def all(self) -> dict:
        return dict(self._data)

    def clear(self):
        self._data = {}
        self._save()


class PluginLoader:
    """Discovers, validates, and loads plugins from plugins/ and user/plugins/."""

    def __init__(self):
        # {plugin_name: {manifest, path, enabled, band, state}}
        self._plugins: Dict[str, dict] = {}
        self._function_manager = None  # Set via scan() for plugin tool loading

    def scan(self, function_manager=None):
        """Discover all plugins and load enabled ones.

        Args:
            function_manager: Optional FunctionManager for plugin tool registration.
        """
        self._function_manager = function_manager
        self._plugins.clear()
        enabled_list = self._get_enabled_list()

        # System plugins (priority band 0-99)
        self._scan_dir(SYSTEM_PLUGINS_DIR, band="system", enabled_list=enabled_list)

        # User plugins (priority band 100-199)
        self._scan_dir(USER_PLUGINS_DIR, band="user", enabled_list=enabled_list)

        # Load enabled plugins
        loaded = 0
        for name, info in self._plugins.items():
            if info["enabled"]:
                self._load_plugin(name)
                loaded += 1

        logger.info(f"[PLUGINS] Scan complete: {len(self._plugins)} found, {loaded} loaded")

    def _scan_dir(self, directory: Path, band: str, enabled_list: list):
        """Scan a directory for plugin.json manifests."""
        if not directory.exists():
            return

        for child in sorted(directory.iterdir()):
            if not child.is_dir():
                continue
            manifest_path = child / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[PLUGINS] Bad manifest in {child.name}: {e}")
                continue

            name = manifest.get("name", child.name)
            if not self._validate_manifest(name, manifest):
                continue

            self._plugins[name] = {
                "manifest": manifest,
                "path": child,
                "enabled": name in enabled_list,
                "band": band,
                "loaded": False,
            }
            logger.debug(f"[PLUGINS] Found: {name} ({band}, enabled={name in enabled_list})")

    def _validate_manifest(self, name: str, manifest: dict) -> bool:
        """Basic manifest validation."""
        if "name" not in manifest:
            logger.warning(f"[PLUGINS] {name}: manifest missing 'name' field")
            return False
        return True

    def _get_enabled_list(self) -> list:
        """Read enabled plugins from user/webui/plugins.json."""
        for path in (USER_PLUGINS_JSON, STATIC_PLUGINS_JSON):
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return data.get("enabled", [])
                except Exception as e:
                    logger.warning(f"[PLUGINS] Failed to read {path}: {e}")
        return []

    def _load_plugin(self, name: str):
        """Load an enabled plugin — register hooks, voice commands."""
        info = self._plugins.get(name)
        if not info:
            return

        manifest = info["manifest"]
        plugin_dir = info["path"]
        band = info["band"]
        base_priority = manifest.get("priority", 50)

        # Offset user plugins into 100-199 band
        if band == "user":
            base_priority = min(base_priority + 100, 199)

        capabilities = manifest.get("capabilities", {})

        # Register hooks
        hooks = capabilities.get("hooks", {})
        for hook_name, handler_path in hooks.items():
            handler_func = self._load_handler(plugin_dir, handler_path, hook_name)
            if handler_func:
                hook_runner.register(
                    hook_name, handler_func,
                    priority=base_priority,
                    plugin_name=name
                )

        # Register voice commands as auto-wired pre_chat hooks
        voice_commands = capabilities.get("voice_commands", [])
        for vc in voice_commands:
            handler_path = vc.get("handler")
            handler_func = self._load_handler(plugin_dir, handler_path, "pre_chat")
            if handler_func:
                voice_match = {
                    "triggers": vc.get("triggers", []),
                    "match": vc.get("match", "exact"),
                }
                # Voice commands that bypass LLM get highest priority in their band
                vc_priority = base_priority if not vc.get("bypass_llm") else min(base_priority, 19)
                if band == "user" and vc.get("bypass_llm"):
                    vc_priority = min(base_priority, 119)

                hook_runner.register(
                    "pre_chat", handler_func,
                    priority=vc_priority,
                    plugin_name=name,
                    voice_match=voice_match
                )

        # Register tools with FunctionManager
        tool_paths = capabilities.get("tools", [])
        if tool_paths and self._function_manager:
            self._function_manager.register_plugin_tools(name, plugin_dir, tool_paths)

        info["loaded"] = True
        logger.info(f"[PLUGINS] Loaded: {name} (priority {base_priority}, {band})")

    def _load_handler(self, plugin_dir: Path, handler_path: str, hook_name: str):
        """Import a Python handler from a plugin directory.

        Args:
            plugin_dir: Plugin root (e.g., plugins/stop/)
            handler_path: Relative path (e.g., "hooks/stop.py")
            hook_name: The hook this handler is for (used as function name to look up)

        Returns:
            Callable or None
        """
        if not handler_path:
            return None

        full_path = plugin_dir / handler_path
        if not full_path.exists():
            logger.warning(f"[PLUGINS] Handler not found: {full_path}")
            return None

        try:
            source = full_path.read_text(encoding="utf-8")
            namespace = {"__file__": str(full_path), "__name__": f"plugin_{plugin_dir.name}_{full_path.stem}"}
            exec(compile(source, str(full_path), "exec"), namespace)

            # Look for a function matching the hook name (e.g., pre_chat, prompt_inject)
            handler = namespace.get(hook_name)
            if handler and callable(handler):
                return handler

            # Fallback: look for a generic 'handle' function
            handler = namespace.get("handle")
            if handler and callable(handler):
                return handler

            logger.warning(f"[PLUGINS] No '{hook_name}' or 'handle' function in {full_path}")
            return None

        except Exception as e:
            logger.error(f"[PLUGINS] Failed to load handler {full_path}: {e}", exc_info=True)
            return None

    def unload_plugin(self, name: str):
        """Unload a plugin — deregister all hooks and tools."""
        hook_runner.unregister_plugin(name)
        if self._function_manager:
            self._function_manager.unregister_plugin_tools(name)
        if name in self._plugins:
            self._plugins[name]["loaded"] = False
        logger.info(f"[PLUGINS] Unloaded: {name}")

    def reload_plugin(self, name: str):
        """Unload and reload a plugin."""
        self.unload_plugin(name)
        if name in self._plugins and self._plugins[name]["enabled"]:
            self._load_plugin(name)

    # ── Query methods ──

    def get_plugin_names(self) -> List[str]:
        """All discovered plugin names."""
        return list(self._plugins.keys())

    def get_enabled_plugins(self) -> List[str]:
        """Names of enabled plugins."""
        return [n for n, info in self._plugins.items() if info["enabled"]]

    def get_loaded_plugins(self) -> List[str]:
        """Names of currently loaded plugins."""
        return [n for n, info in self._plugins.items() if info.get("loaded")]

    def get_plugin_info(self, name: str) -> Optional[dict]:
        """Get plugin info dict (manifest, path, enabled, band)."""
        info = self._plugins.get(name)
        if not info:
            return None
        return {
            "name": name,
            "manifest": info["manifest"],
            "path": str(info["path"]),
            "enabled": info["enabled"],
            "band": info["band"],
            "loaded": info.get("loaded", False),
        }

    def get_all_plugin_info(self) -> List[dict]:
        """Get info for all discovered plugins."""
        return [self.get_plugin_info(n) for n in self._plugins]

    def get_plugin_state(self, name: str) -> PluginState:
        """Get the PluginState helper for a plugin."""
        return PluginState(name)


# Singleton
plugin_loader = PluginLoader()
