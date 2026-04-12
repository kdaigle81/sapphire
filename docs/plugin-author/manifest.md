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
| `pip_dependencies` | string[] | No | `[]` | Python packages required (pip specifiers, e.g. `["telethon>=1.34", "requests"]`). Checked before loading; missing deps shown in UI with install option |
| `capabilities` | object | No | — | What the plugin provides (see below) |

## Capabilities

The `capabilities` object declares what the plugin provides:

```json
{
  "capabilities": {
    "hooks": { ... },
    "voice_commands": [ ... ],
    "tools": [ ... ],
    "scopes": [ ... ],
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
- Scopes — see below
- [Routes](routes.md)
- [Schedule](schedule.md)
- [Settings & Web UI](settings.md)
- [Providers (TTS, STT, Embedding, LLM)](providers.md)
- [Apps](APPS.md)
- [Themes](THEMES.md)
- [Daemons](daemons.md) — long-running background threads with event sources (e.g. Telegram, Discord listeners)
- Sidebar Accordion — inject custom HTML panels into the chat sidebar

### Scopes

Scopes let a plugin register data-isolation selectors that appear in the Chat Settings sidebar. Each scope creates a `ContextVar` that your tools can read to know which data partition the current chat is using.

**When to use:** If your plugin stores per-user data (memories, contacts, wallet addresses, accounts) and users might want different data sets for different chats (e.g., "work" vs "personal" email accounts).

**Declare scopes in your manifest:**

```json
{
  "capabilities": {
    "scopes": [
      {
        "key": "email",
        "label": "email",
        "endpoint": "/api/email/accounts",
        "data_key": "accounts",
        "value_field": "address",
        "name_field": "address",
        "label_template": "{address}"
      }
    ]
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `key` | Yes | Scope identifier — must be a valid Python identifier. Creates `scope_{key}` ContextVar and `{key}_scope` setting key |
| `label` | Yes | Display label in the Chat Settings sidebar dropdown header |
| `endpoint` | Yes | API endpoint that returns the list of available scope values (for the dropdown) |
| `data_key` | No | Key in the endpoint response JSON that contains the list (default: root array) |
| `value_field` | No | Field in each list item to use as the scope value |
| `name_field` | No | Field in each list item to use as the display name |
| `label_template` | No | Format string for dropdown labels (e.g., `"{name} ({count})"`) |
| `nav_target` | No | View to navigate to when the "+" button is clicked (e.g., `"mind:memories"`) |
| `default` | No | Default scope value (default: `"default"`) |

**Reading the scope in your tool code:**

```python
def _get_current_email_scope():
    from core.chat.function_manager import scope_email
    return scope_email.get()  # returns the value set in Chat Settings
```

The import resolves via `function_manager.__getattr__` — no need to import the ContextVar directly. The scope is automatically set by the chat pipeline before your tool's `execute()` is called.

**Real example:** See `plugins/memory/plugin.json` for 4 scopes (memory, goal, knowledge, people) and `plugins/email/plugin.json` for the email scope.

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
