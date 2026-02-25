"""
Tests for core/plugin_loader.py — Plugin discovery and loading.

Run with: pytest tests/test_plugin_loader.py -v
"""
import pytest
import json
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.hooks import HookRunner, HookEvent
from core.plugin_loader import PluginLoader, PluginState


@pytest.fixture
def temp_dirs():
    """Create temporary plugin and state directories."""
    base = Path(tempfile.mkdtemp())
    plugins_dir = base / "plugins"
    user_plugins_dir = base / "user_plugins"
    state_dir = base / "plugin_state"
    plugins_json = base / "plugins.json"
    plugins_dir.mkdir()
    user_plugins_dir.mkdir()
    state_dir.mkdir()
    yield {
        "base": base,
        "plugins": plugins_dir,
        "user_plugins": user_plugins_dir,
        "state": state_dir,
        "plugins_json": plugins_json,
    }
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def runner():
    """Fresh HookRunner for each test."""
    return HookRunner()


def _make_plugin(plugins_dir, name, manifest, hooks_code=None):
    """Helper: create a plugin directory with manifest and optional hook code."""
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    if hooks_code:
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        for filename, code in hooks_code.items():
            (hooks_dir / filename).write_text(code, encoding="utf-8")
    return plugin_dir


# =============================================================================
# PluginState Tests
# =============================================================================

class TestPluginState:
    def test_save_and_get(self, temp_dirs):
        with patch("core.plugin_loader.PLUGIN_STATE_DIR", temp_dirs["state"]):
            state = PluginState("test_plugin")
            state.save("key1", "value1")
            assert state.get("key1") == "value1"

    def test_get_default(self, temp_dirs):
        with patch("core.plugin_loader.PLUGIN_STATE_DIR", temp_dirs["state"]):
            state = PluginState("test_plugin")
            assert state.get("missing", "default") == "default"

    def test_delete(self, temp_dirs):
        with patch("core.plugin_loader.PLUGIN_STATE_DIR", temp_dirs["state"]):
            state = PluginState("test_plugin")
            state.save("key1", "value1")
            state.delete("key1")
            assert state.get("key1") is None

    def test_clear(self, temp_dirs):
        with patch("core.plugin_loader.PLUGIN_STATE_DIR", temp_dirs["state"]):
            state = PluginState("test_plugin")
            state.save("a", 1)
            state.save("b", 2)
            state.clear()
            assert state.all() == {}

    def test_persists_to_disk(self, temp_dirs):
        with patch("core.plugin_loader.PLUGIN_STATE_DIR", temp_dirs["state"]):
            state1 = PluginState("test_plugin")
            state1.save("persisted", True)
            # New instance reads from disk
            state2 = PluginState("test_plugin")
            assert state2.get("persisted") is True

    def test_complex_values(self, temp_dirs):
        with patch("core.plugin_loader.PLUGIN_STATE_DIR", temp_dirs["state"]):
            state = PluginState("test_plugin")
            state.save("nested", {"list": [1, 2, 3], "dict": {"a": "b"}})
            result = state.get("nested")
            assert result["list"] == [1, 2, 3]
            assert result["dict"]["a"] == "b"


# =============================================================================
# Plugin Discovery Tests
# =============================================================================

class TestPluginDiscovery:
    def test_scan_finds_system_plugins(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "test-plugin", {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "Test plugin"
        })
        # Enable it
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["test-plugin"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            assert "test-plugin" in loader.get_plugin_names()

    def test_scan_finds_user_plugins(self, temp_dirs, runner):
        _make_plugin(temp_dirs["user_plugins"], "user-plugin", {
            "name": "user-plugin",
            "version": "1.0.0",
            "description": "User plugin"
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["user-plugin"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            info = loader.get_plugin_info("user-plugin")
            assert info is not None
            assert info["band"] == "user"

    def test_scan_skips_dirs_without_manifest(self, temp_dirs, runner):
        (temp_dirs["plugins"] / "no-manifest").mkdir()
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            assert len(loader.get_plugin_names()) == 0

    def test_scan_skips_bad_manifest(self, temp_dirs, runner):
        bad_dir = temp_dirs["plugins"] / "bad-plugin"
        bad_dir.mkdir()
        (bad_dir / "plugin.json").write_text("not json!!!", encoding="utf-8")
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            assert len(loader.get_plugin_names()) == 0

    def test_disabled_plugin_found_but_not_loaded(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "disabled-plugin", {
            "name": "disabled-plugin",
            "version": "1.0.0"
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": []}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            assert "disabled-plugin" in loader.get_plugin_names()
            assert "disabled-plugin" not in loader.get_loaded_plugins()

    def test_missing_plugins_dir_no_error(self, temp_dirs, runner):
        missing = temp_dirs["base"] / "nonexistent"
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", missing), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()  # should not raise
            assert len(loader.get_plugin_names()) == 0


# =============================================================================
# Hook Loading Tests
# =============================================================================

class TestHookLoading:
    def test_loads_hook_handler(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "hook-test", {
            "name": "hook-test",
            "version": "1.0.0",
            "capabilities": {
                "hooks": {
                    "pre_chat": "hooks/intercept.py"
                }
            }
        }, hooks_code={
            "intercept.py": "def pre_chat(event): event.metadata['reached'] = True"
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["hook-test"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            event = HookEvent()
            runner.fire("pre_chat", event)
            assert event.metadata.get("reached") is True

    def test_voice_command_registers_as_pre_chat(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "stop", {
            "name": "stop",
            "version": "1.0.0",
            "priority": 1,
            "capabilities": {
                "voice_commands": [{
                    "triggers": ["stop", "halt"],
                    "match": "exact",
                    "bypass_llm": True,
                    "handler": "hooks/stop.py"
                }]
            }
        }, hooks_code={
            "stop.py": (
                "def pre_chat(event):\n"
                "    event.skip_llm = True\n"
                "    event.response = 'Stopped.'\n"
                "    event.stop_propagation = True\n"
            )
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["stop"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()

            # "stop" should trigger
            event = HookEvent(input="stop")
            runner.fire("pre_chat", event)
            assert event.skip_llm is True
            assert event.response == "Stopped."

            # "hello" should not trigger
            event2 = HookEvent(input="hello")
            runner.fire("pre_chat", event2)
            assert event2.skip_llm is False

    def test_missing_handler_file_no_crash(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "bad-handler", {
            "name": "bad-handler",
            "version": "1.0.0",
            "capabilities": {
                "hooks": {
                    "pre_chat": "hooks/nonexistent.py"
                }
            }
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["bad-handler"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()  # should not raise
            assert not runner.has_handlers("pre_chat")

    def test_broken_handler_code_no_crash(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "broken", {
            "name": "broken",
            "version": "1.0.0",
            "capabilities": {
                "hooks": {
                    "pre_chat": "hooks/broken.py"
                }
            }
        }, hooks_code={
            "broken.py": "this is not valid python!!!"
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["broken"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()  # should not raise
            assert not runner.has_handlers("pre_chat")


# =============================================================================
# Unload / Reload Tests
# =============================================================================

class TestUnloadReload:
    def test_unload_removes_hooks(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "unload-test", {
            "name": "unload-test",
            "version": "1.0.0",
            "capabilities": {
                "hooks": {
                    "pre_chat": "hooks/test.py"
                }
            }
        }, hooks_code={
            "test.py": "def pre_chat(event): event.metadata['active'] = True"
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["unload-test"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            assert runner.has_handlers("pre_chat")

            loader.unload_plugin("unload-test")
            assert not runner.has_handlers("pre_chat")

    def test_reload_refreshes_handler(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "reload-test", {
            "name": "reload-test",
            "version": "1.0.0",
            "capabilities": {
                "hooks": {
                    "pre_chat": "hooks/test.py"
                }
            }
        }, hooks_code={
            "test.py": "def pre_chat(event): event.metadata['version'] = 1"
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["reload-test"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()

            # Verify v1
            event = HookEvent()
            runner.fire("pre_chat", event)
            assert event.metadata["version"] == 1

            # Update handler code
            hooks_dir = temp_dirs["plugins"] / "reload-test" / "hooks"
            (hooks_dir / "test.py").write_text(
                "def pre_chat(event): event.metadata['version'] = 2"
            )

            # Reload
            loader.reload_plugin("reload-test")

            event2 = HookEvent()
            runner.fire("pre_chat", event2)
            assert event2.metadata["version"] == 2


# =============================================================================
# Priority Band Tests
# =============================================================================

class TestPriorityBands:
    def test_system_before_user(self, temp_dirs, runner):
        """System plugins should always fire before user plugins."""
        order = []
        _make_plugin(temp_dirs["user_plugins"], "user-hook", {
            "name": "user-hook",
            "version": "1.0.0",
            "priority": 1,
            "capabilities": {
                "hooks": {"pre_chat": "hooks/h.py"}
            }
        }, hooks_code={
            "h.py": "def pre_chat(event): event.metadata.setdefault('order', []).append('user')"
        })
        _make_plugin(temp_dirs["plugins"], "sys-hook", {
            "name": "sys-hook",
            "version": "1.0.0",
            "priority": 99,
            "capabilities": {
                "hooks": {"pre_chat": "hooks/h.py"}
            }
        }, hooks_code={
            "h.py": "def pre_chat(event): event.metadata.setdefault('order', []).append('system')"
        })
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["sys-hook", "user-hook"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            event = HookEvent()
            runner.fire("pre_chat", event)
            # System (priority 99) should fire before user (priority 1+100=101)
            assert event.metadata["order"] == ["system", "user"]


# =============================================================================
# Query Method Tests
# =============================================================================

class TestQueryMethods:
    def test_get_all_plugin_info(self, temp_dirs, runner):
        _make_plugin(temp_dirs["plugins"], "alpha", {"name": "alpha", "version": "1.0.0"})
        _make_plugin(temp_dirs["plugins"], "beta", {"name": "beta", "version": "2.0.0"})
        temp_dirs["plugins_json"].write_text(
            json.dumps({"enabled": ["alpha"]}), encoding="utf-8"
        )
        loader = PluginLoader()
        with patch("core.plugin_loader.SYSTEM_PLUGINS_DIR", temp_dirs["plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_DIR", temp_dirs["user_plugins"]), \
             patch("core.plugin_loader.USER_PLUGINS_JSON", temp_dirs["plugins_json"]), \
             patch("core.plugin_loader.hook_runner", runner):
            loader.scan()
            all_info = loader.get_all_plugin_info()
            assert len(all_info) == 2
            names = {p["name"] for p in all_info}
            assert names == {"alpha", "beta"}
            alpha = [p for p in all_info if p["name"] == "alpha"][0]
            assert alpha["enabled"] is True
            assert alpha["loaded"] is True
            beta = [p for p in all_info if p["name"] == "beta"][0]
            assert beta["enabled"] is False
            assert beta["loaded"] is False

    def test_get_plugin_info_missing(self, temp_dirs, runner):
        loader = PluginLoader()
        assert loader.get_plugin_info("nonexistent") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
