"""
Plugin route helper tests for core/routes/plugins.py.

_get_merged_plugins() and _extract_css_preview() are the pure-logic helpers
in the biggest risk file in the coverage map (10.4% coverage). Testing these
directly is cheap and covers significant production code without needing a
running server or auth context.

Run with: pytest tests/test_plugin_helpers.py -v
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Bootstrap api_fastapi first to resolve the circular import between
# core/routes/plugins.py and core/api_fastapi.py (same pattern as agents.py).
import importlib
importlib.import_module("core.api_fastapi")


# ─── _get_merged_plugins ────────────────────────────────────────────────────

class TestGetMergedPlugins:
    """Tests for _get_merged_plugins() — merges static and user plugins.json."""

    @pytest.fixture
    def setup_plugins(self, tmp_path):
        """Build a temp directory tree that mimics the real plugin JSON layout.

        Returns a helper that patches the module-level paths and returns
        the dirs for writing test files.
        """
        import core.routes.plugins as mod

        static_dir = tmp_path / "interfaces" / "web" / "static" / "core-ui"
        static_dir.mkdir(parents=True)
        user_dir = tmp_path / "user" / "webui"
        user_dir.mkdir(parents=True)

        class Dirs:
            static = static_dir
            user = user_dir
            user_json = user_dir / "plugins.json"

        return Dirs, mod

    def test_static_only_no_user_file(self, setup_plugins, monkeypatch):
        dirs, mod = setup_plugins
        static = {"enabled": ["backup"], "plugins": {"backup": {"title": "Backup"}}}
        (dirs.static / "plugins.json").write_text(json.dumps(static), encoding='utf-8')

        # STATIC_DIR points to interfaces/web/static/ — the code adds 'core-ui/plugins.json'
        monkeypatch.setattr(mod, "STATIC_DIR", dirs.static.parent)
        monkeypatch.setattr(mod, "USER_PLUGINS_JSON", dirs.user_json)

        result = mod._get_merged_plugins()
        assert "backup" in result["enabled"]
        assert "backup" in result["plugins"]

    def test_user_overrides_enabled_list(self, setup_plugins, monkeypatch):
        dirs, mod = setup_plugins
        static = {"enabled": ["backup"], "plugins": {"backup": {"title": "Backup"}}}
        user = {"enabled": ["backup", "image-gen"], "plugins": {}}
        (dirs.static / "plugins.json").write_text(json.dumps(static), encoding='utf-8')
        dirs.user_json.write_text(json.dumps(user), encoding='utf-8')

        monkeypatch.setattr(mod, "STATIC_DIR", dirs.static.parent)
        monkeypatch.setattr(mod, "USER_PLUGINS_JSON", dirs.user_json)

        result = mod._get_merged_plugins()
        assert result["enabled"] == ["backup", "image-gen"]

    def test_user_plugins_merge_with_static(self, setup_plugins, monkeypatch):
        dirs, mod = setup_plugins
        static = {"enabled": [], "plugins": {"core-a": {"title": "A"}}}
        user = {"enabled": [], "plugins": {"user-b": {"title": "B"}}}
        (dirs.static / "plugins.json").write_text(json.dumps(static), encoding='utf-8')
        dirs.user_json.write_text(json.dumps(user), encoding='utf-8')

        monkeypatch.setattr(mod, "STATIC_DIR", dirs.static.parent)
        monkeypatch.setattr(mod, "USER_PLUGINS_JSON", dirs.user_json)

        result = mod._get_merged_plugins()
        assert "core-a" in result["plugins"]
        assert "user-b" in result["plugins"]

    def test_locked_plugins_always_enabled(self, setup_plugins, monkeypatch):
        """LOCKED_PLUGINS must be enforced even when no user plugins.json exists.
        Previously xfail — fixed by extracting _enforce_locked() and calling it
        before all return paths."""
        dirs, mod = setup_plugins
        static = {"enabled": [], "plugins": {}}
        (dirs.static / "plugins.json").write_text(json.dumps(static), encoding='utf-8')
        # No user file — locked plugins should still be forced

        monkeypatch.setattr(mod, "STATIC_DIR", dirs.static.parent)
        monkeypatch.setattr(mod, "USER_PLUGINS_JSON", dirs.user_json)
        monkeypatch.setattr(mod, "LOCKED_PLUGINS", ["critical-plugin"])

        result = mod._get_merged_plugins()
        assert "critical-plugin" in result["enabled"]

    def test_corrupt_static_returns_empty_shell(self, setup_plugins, monkeypatch):
        dirs, mod = setup_plugins
        (dirs.static / "plugins.json").write_text("NOT VALID JSON", encoding='utf-8')

        monkeypatch.setattr(mod, "STATIC_DIR", dirs.static.parent)
        monkeypatch.setattr(mod, "USER_PLUGINS_JSON", dirs.user_json)

        result = mod._get_merged_plugins()
        assert result == {"enabled": [], "plugins": {}}


# ─── _extract_css_preview ───────────────────────────────────────────────────

class TestExtractCssPreview:
    """Tests for the CSS variable parser used by theme preview swatches."""

    def test_extracts_hex_colors(self, tmp_path):
        from core.routes.plugins import _extract_css_preview

        css = """
        :root {
            --bg: #1a1b2e;
            --bg-secondary: #252639;
            --text: #e1e1e6;
            --trim: #4a9eff;
            --border: #333450;
        }
        """
        css_file = tmp_path / "theme.css"
        css_file.write_text(css, encoding='utf-8')

        colors = _extract_css_preview(css_file)
        assert colors["bg"] == "#1a1b2e"
        assert colors["text"] == "#e1e1e6"
        assert colors["trim"] == "#4a9eff"
        assert colors["border"] == "#333450"
        # accent should fallback to trim when not declared
        assert colors["accent"] == "#4a9eff"

    def test_extracts_rgba_colors(self, tmp_path):
        from core.routes.plugins import _extract_css_preview

        css = ":root { --bg: rgba(26, 27, 46, 1); --text: #fff; }"
        css_file = tmp_path / "theme.css"
        css_file.write_text(css, encoding='utf-8')

        colors = _extract_css_preview(css_file)
        assert "rgba" in colors["bg"]
        assert colors["text"] == "#fff"

    def test_returns_empty_on_missing_file(self, tmp_path):
        from core.routes.plugins import _extract_css_preview

        colors = _extract_css_preview(tmp_path / "nonexistent.css")
        assert colors == {}

    def test_returns_empty_on_no_variables(self, tmp_path):
        from core.routes.plugins import _extract_css_preview

        css_file = tmp_path / "empty.css"
        css_file.write_text("body { margin: 0; }", encoding='utf-8')

        colors = _extract_css_preview(css_file)
        assert colors == {}
