# Manifest Reference

Every plugin needs a `plugin.json` in its root folder.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | Unique identifier (must match folder name) |
| `version` | string | No | — | Semver (`1.0.0`) |
| `description` | string | No | — | One-line summary |
| `author` | string | No | — | Author name |
| `url` | string | No | — | Project URL (shown in Settings) |
| `icon` | string | No | — | Emoji icon shown in Settings UI and plugin lists |
| `emoji` | string | No | — | Alias for `icon` (legacy — prefer `icon`) |
| `display_name` | string | No | — | Human-friendly name (used as label fallback in apps) |
| `short_name` | string | No | — | Short title for Settings UI (falls back to `description`) |
| `priority` | int | No | 50 | Execution order within band (lower = first) |
| `default_enabled` | bool | No | false | Auto-enable on fresh install |
| `managed_hide` | bool | No | false | Hide plugin entirely in managed/resale mode |
| `settingsUI` | string\|null | No | `"auto"` | Controls settings panel: `"auto"` (from manifest schema), `"plugin"` (custom JS), `"core"` (hardcoded), or `null` (none) |
| `capabilities` | object | No | — | What the plugin provides (see below) |

## Capabilities

The `capabilities` object declares what the plugin provides:

```json
{
  "capabilities": {
    "hooks": { ... },
    "voice_commands": [ ... ],
    "tools": [ ... ],
    "routes": [ ... ],
    "schedule": [ ... ],
    "settings": [ ... ],
    "providers": { ... },
    "web": { ... },
    "daemon": { ... },
    "app": { ... },
    "themes": [ ... ],
    "sidebar_accordion": { ... }
  }
}
```

Each capability is documented in its own guide:
- [Hooks & Voice Commands](hooks.md)
- [Tools](tools.md)
- [Routes](routes.md)
- [Schedule](schedule.md)
- [Settings & Web UI](settings.md)
- [Providers (TTS, STT, Embedding, LLM)](providers.md)
- [Apps](APPS.md)
- [Themes](THEMES.md)
- [Daemons](daemons.md) — long-running background threads with event sources (e.g. Telegram, Discord listeners)
- Sidebar Accordion — inject custom HTML panels into the chat sidebar

## Priority Bands

Lower fires first. Within each band:

| Range | Purpose |
|-------|---------|
| 0-19 | Critical intercepts (stop, security) |
| 20-49 | Input modification (translation, formatting) |
| 50-79 | Context enrichment (prompt injection, state) |
| 80-99 | Observation (logging, analytics) |

User plugins use the same ranges but shifted to 100-199.

## Directory Structure

```
plugins/                          # System plugins (0-99)
  voice-commands/
    plugin.json
    plugin.sig
    hooks/stop.py
    hooks/reset.py
  ssh/
    plugin.json
    plugin.sig
    tools/ssh_tool.py
    web/index.js

user/
  plugins/                        # User plugins (100-199)
    my-plugin/
      plugin.json
      hooks/handler.py
  plugin_state/                   # Per-plugin JSON state
    ssh.json
  webui/
    plugins.json                  # Enabled list: {"enabled": [...]}
    plugins/                      # Per-plugin settings
      ssh.json
      image-gen.json
```
