# Plugins

Sapphire plugins are self-contained extensions that add capabilities without touching core code. A plugin is a folder with a `plugin.json` manifest and optional Python/JavaScript files.

Plugins can:
- **Hook** into the chat pipeline (filter input, inject context, log responses)
- **Register tools** the AI can call (same format as built-in tools)
- **Declare voice commands** for instant actions ("stop", "reset")
- **Schedule cron tasks** that run on a timer
- **Provide a web settings UI** in the browser

Everything loads and unloads live — no restart needed.

---

## Quick Start

Minimal plugin in 2 files:

```
plugins/my-plugin/
  plugin.json
  hooks/greet.py
```

**plugin.json**:
```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Logs every chat",
  "author": "you",
  "capabilities": {
    "hooks": {
      "post_chat": "hooks/greet.py"
    }
  }
}
```

**hooks/greet.py**:
```python
import logging
logger = logging.getLogger(__name__)

def post_chat(event):
    logger.info(f"User: {event.input}")
    logger.info(f"AI: {event.response}")
```

Enable in Settings > Plugins. It loads immediately.

---

## Where Plugins Live

| Path | Band | Priority Range | Tracked |
|------|------|----------------|---------|
| `plugins/` | System | 0-99 | Yes |
| `user/plugins/` | User | 100-199 | No (gitignored) |

User plugin priorities are automatically offset into the 100-199 range.

---

## Manifest Reference

Every plugin needs a `plugin.json` in its root.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | Unique identifier (folder name) |
| `version` | string | No | — | Semver (`1.0.0`) |
| `description` | string | No | — | One-line summary |
| `author` | string | No | — | Author name |
| `url` | string | No | — | Project URL (shown in Settings) |
| `priority` | int | No | 50 | Execution order within band (lower = first) |
| `default_enabled` | bool | No | false | Auto-enable on fresh install |
| `capabilities` | object | No | — | What the plugin provides |

### Priority Bands

Lower fires first. Within each band:

| Range | Purpose |
|-------|---------|
| 0-19 | Critical intercepts (stop, security) |
| 20-49 | Input modification (translation, formatting) |
| 50-79 | Context enrichment (prompt injection, state) |
| 80-99 | Observation (logging, analytics) |

User plugins use the same ranges but shifted to 100-199.

---

## Capabilities

### hooks

Map hook names to handler files:

```json
"capabilities": {
  "hooks": {
    "post_stt": "hooks/stt_cleanup.py",
    "pre_chat": "hooks/filter.py",
    "prompt_inject": "hooks/context.py",
    "post_llm": "hooks/response_filter.py",
    "post_chat": "hooks/log.py",
    "pre_execute": "hooks/guard.py",
    "post_execute": "hooks/audit.py",
    "pre_tts": "hooks/tts_filter.py",
    "post_tts": "hooks/tts_done.py",
    "on_wake": "hooks/wake_react.py"
  }
}
```

Each handler exports a function matching the hook name (e.g. `def pre_chat(event):`), or `def handle(event):` as fallback.

### voice_commands

Voice commands are pre_chat hooks with trigger pattern matching:

```json
"capabilities": {
  "voice_commands": [
    {
      "triggers": ["stop", "halt", "be quiet"],
      "match": "exact",
      "bypass_llm": true,
      "handler": "hooks/stop.py",
      "description": "Stop TTS and cancel generation"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `triggers` | Phrases to match (case-insensitive) |
| `match` | `exact`, `starts_with`, `contains`, or `regex` |
| `bypass_llm` | If true, gets highest priority (0-19) |
| `handler` | Path to handler file |

Multiple voice commands per plugin is fine — they're an array.

### tools

Python tool files registered with the function manager:

```json
"capabilities": {
  "tools": ["tools/my_tool.py"]
}
```

Tool files use the same format as `functions/*.py`. See [Tool File Format](#tool-file-format) below.

### schedule

Cron tasks that run a Python handler:

```json
"capabilities": {
  "schedule": [
    {
      "name": "Daily Digest",
      "cron": "0 9 * * *",
      "handler": "schedule/digest.py",
      "description": "Morning email summary",
      "enabled": true,
      "chance": 100
    }
  ]
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | Required | Display name |
| `cron` | string | `0 9 * * *` | Standard 5-field cron |
| `handler` | string | Required | Path to handler file |
| `description` | string | — | What the task does |
| `enabled` | bool | true | Whether it runs |
| `chance` | int | 100 | Percent chance to fire (1-100) |

Tasks appear in the Schedule UI and are removed when the plugin is disabled.

### web (Settings UI)

Plugins with a `web/` subdirectory can provide a settings tab:

```json
"capabilities": {
  "web": {
    "settingsUI": "plugin"
  }
}
```

Assets are served at `/plugin-web/{name}/`. See [Web Settings UI](#web-settings-ui) below.

---

## Hook Points

All hooks receive a mutable `HookEvent`. Changes persist across handlers in priority order.

| Hook | When | Key Fields | Use |
|------|------|-----------|-----|
| `post_stt` | After voice transcription | `input` (mutable) | Correct STT errors, translate, normalize |
| `pre_chat` | Before LLM | `input`, `skip_llm`, `response` | Filter input, bypass LLM |
| `prompt_inject` | System prompt build | `context_parts` | Append context strings |
| `post_llm` | After LLM, before save | `response` (mutable) | Translate, filter, style transfer |
| `post_chat` | After response saved | `input`, `response` | Logging, analytics |
| `pre_execute` | Before tool call | `function_name`, `arguments` | Modify args, block tools |
| `post_execute` | After tool call | `function_name`, `result` | Audit, react to results |
| `pre_tts` | Before speech | `tts_text`, `skip_tts` | Modify text, cancel TTS |
| `post_tts` | After playback ends | `tts_text` | Analytics, reactions, subtitles |
| `on_wake` | Wakeword detected | — | Play sounds, log, custom reactions |

### HookEvent Fields

```python
@dataclass
class HookEvent:
    input: str = ""                          # User message
    skip_llm: bool = False                   # Bypass LLM / skip execution
    response: Optional[str] = None           # Direct response (with skip_llm)
    ephemeral: bool = False                  # Don't save to history (with skip_llm)
    context_parts: List[str] = []            # System prompt injections
    stop_propagation: bool = False           # Halt lower-priority hooks
    config: Any = None                       # System config (read-only)
    metadata: Dict[str, Any] = {}            # Free-form data (system, etc.)
    function_name: Optional[str] = None      # Tool name (execute hooks)
    arguments: Optional[dict] = None         # Tool args (mutable in pre_execute)
    result: Optional[str] = None             # Tool result (post_execute)
    tts_text: Optional[str] = None           # TTS text (mutable in pre_tts)
    skip_tts: bool = False                   # Cancel TTS
```

### System Access

Handlers get the `VoiceChatSystem` instance via `event.metadata.get("system")`. This gives deep access to Sapphire's subsystems — TTS, STT, wakeword, LLM, chat history, tool manager, and more.

**Important: not all hooks populate system metadata.** Check this table before relying on it:

| Hook | `metadata["system"]`? | `config`? | Mutable Fields |
|------|-----------------------|-----------|----------------|
| `post_stt` | **Yes** | Yes | `input` (transcribed text) |
| `pre_chat` | **Yes** | Yes | `input`, `skip_llm`, `response`, `ephemeral` |
| `prompt_inject` | No | Yes | `context_parts` (list — append to it) |
| `post_llm` | **Yes** | Yes | `response` (AI's answer text) |
| `post_chat` | **Yes** | Yes | None (observational) |
| `pre_execute` | **Yes** | Yes | `arguments`, `skip_llm`, `result` |
| `post_execute` | No | Yes | None (observational) |
| `pre_tts` | No | Yes | `tts_text`, `skip_tts` |
| `post_tts` | No | Yes | None (observational) |
| `on_wake` | No | Yes | None (notification only) |

### What System Access Gives You

Through `system = event.metadata.get("system")`, plugins can control:

| Subsystem | Access | What You Can Do |
|-----------|--------|----------------|
| **TTS** | `system.tts` | `set_voice(name)`, `set_speed(float)`, `set_pitch(float)`, `speak(text)`, `speak_sync(text)`, `stop()`, `generate_audio_data(text)` |
| **STT** | `system.toggle_stt(bool)` | Enable/disable speech-to-text at runtime |
| **Wakeword** | `system.toggle_wakeword(bool)` | Enable/disable wakeword detection |
| **LLM** | `system.llm_chat` | `chat(query)` — send a message directly to the LLM |
| **System Prompt** | `system.llm_chat` | `set_system_prompt(text)`, `get_system_prompt_template()` |
| **Chat History** | `system.llm_chat.session_manager` | `get_messages()`, `list_chats()`, `create_chat(name)`, `set_active_chat(name)`, `delete_chat(name)` |
| **Tool Manager** | `system.llm_chat.function_manager` | `update_enabled_functions([toolset])`, `execute_function(name, args)`, `get_enabled_function_names()` |
| **Scopes** | `system.llm_chat.function_manager` | `set_knowledge_scope(s)`, `set_email_scope(s)`, `set_bitcoin_scope(s)`, `set_memory_scope(s)` |
| **Generation** | `system.llm_chat.streaming_chat` | `cancel_flag = True` — cancel in-progress LLM streaming |
| **Event Bus** | `from core.event_bus import publish, Events` | Broadcast events system-wide |

Always guard access with `hasattr()` checks — subsystems may be None if disabled:

```python
def pre_chat(event):
    system = event.metadata.get("system")
    if not system:
        return
    if hasattr(system, "tts") and system.tts:
        system.tts.set_voice("af_sky")
```

### Hook Examples

**post_stt — correct transcription:**
```python
def post_stt(event):
    # Fix common STT mishearings
    fixes = {"creme": "Krem", "saphire": "Sapphire", "hey i": "AI"}
    text = event.input
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    event.input = text
```

**pre_chat — block input:**
```python
def pre_chat(event):
    if "password" in event.input.lower():
        event.skip_llm = True
        event.response = "I can't help with that."
        event.stop_propagation = True
```

**prompt_inject — add context:**
```python
def prompt_inject(event):
    event.context_parts.append("The user's timezone is UTC+3.")
```

**pre_execute — block a tool:**
```python
def pre_execute(event):
    if event.function_name == "delete_memory":
        event.skip_llm = True
        event.result = "Deletion blocked by plugin."
```

**post_llm — Salty Sailor (add spice to responses):**
```python
import random
SPICE = ["hell yeah", "damn right", "no kidding"]

def post_llm(event):
    if event.response and random.random() < 0.3:
        event.response = event.response + f" ...{random.choice(SPICE)}."
```

**post_llm — clean mode (strip profanity):**
```python
SWEARS = {"damn": "darn", "hell": "heck", "ass": "butt"}

def post_llm(event):
    text = event.response or ""
    for word, clean in SWEARS.items():
        text = text.replace(word, clean)
    event.response = text
```

**pre_tts — fix pronunciation:**
```python
def pre_tts(event):
    event.tts_text = event.tts_text.replace("API", "A.P.I.")
```

**voice command handler:**
```python
def pre_chat(event):
    system = event.metadata.get("system")
    if system and hasattr(system, "tts") and system.tts:
        system.tts.stop()
    event.skip_llm = True
    event.ephemeral = True
    event.response = "Stopped."
    event.stop_propagation = True
```

---

## Tool File Format

Plugin tools use the same format as `functions/*.py`:

```python
ENABLED = True
EMOJI = '🔧'
AVAILABLE_FUNCTIONS = ['my_tool_do_thing']

TOOLS = [
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "my_tool_do_thing",
            "description": "Does the thing",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "What to do it to"
                    }
                },
                "required": ["target"]
            }
        }
    }
]

def execute(function_name, arguments, config):
    """Called by function manager.

    Args:
        function_name: Which function was called
        arguments: Dict of parameters
        config: System config

    Returns:
        (message: str, success: bool) tuple
    """
    if function_name == "my_tool_do_thing":
        target = arguments.get("target", "")
        return f"Did the thing to {target}", True
    return "Unknown function", False
```

| Export | Type | Description |
|--------|------|-------------|
| `ENABLED` | bool | Whether tool is active |
| `EMOJI` | str | Display icon |
| `AVAILABLE_FUNCTIONS` | list | Function names this file provides |
| `TOOLS` | list | OpenAI-compatible function schemas |
| `execute()` | function | Dispatcher — returns `(message, success)` |

### Tool Schema Flags

Inside each tool's schema dict, you can set:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `is_local` | bool/str | `True` | `True` = runs locally, `"endpoint"` = calls external API, `False` = network required |
| `network` | bool | `false` | Mark as network-dependent (tracked by function manager) |

```python
TOOLS = [{
    "type": "function",
    "is_local": "endpoint",   # calls Home Assistant API
    "network": True,           # needs network access
    "function": { ... }
}]
```

### Multi-Account Scope Support

Tools that support multiple accounts (email, bitcoin, etc.) can read the active scope:

```python
from core.chat.function_manager import scope_email

def execute(function_name, arguments, config):
    account = scope_email.get()  # returns active account name (ContextVar)
    creds = load_credentials(account)
    # ... use account-specific credentials
```

Available scope ContextVars: `scope_email`, `scope_bitcoin`, `scope_knowledge`, `scope_memory`, `scope_people`, `scope_rag`, `scope_goal`.

Tools are added to toolsets and the AI calls them contextually. See [TOOLS.md](TOOLS.md) for the full tools guide.

### Reading Plugin Settings from Tools

Tools can load their own settings:

```python
import json
from pathlib import Path

def _load_settings():
    path = Path("user/webui/plugins/my-plugin.json")
    if path.exists():
        return json.loads(path.read_text())
    return {}  # defaults
```

---

## Plugin State

Each plugin gets a persistent JSON key-value store at `user/plugin_state/{name}.json`:

```python
from core.plugin_loader import plugin_loader

state = plugin_loader.get_plugin_state("my-plugin")
state.get("counter", 0)        # read
state.save("counter", 42)      # write (auto-persists)
state.delete("counter")        # remove key
state.all()                    # entire dict
state.clear()                  # wipe everything
```

For heavier storage, plugins can create their own SQLite database.

---

## Schedule Handler Contract

```python
def run(event):
    """Called by continuity scheduler on cron match.

    event dict:
        system:       VoiceChatSystem instance
        config:       System config module
        task:         Task definition dict
        plugin_state: PluginState instance
    """
    system = event["system"]
    state = event["plugin_state"]

    # Do work...
    state.save("last_run", "2025-01-01")
    return "Done"  # Optional — logged to activity
```

---

## Web Settings UI

Plugins can provide a settings tab in Settings > Plugins.

### Structure

```
plugins/my-plugin/
  plugin.json              # "web": {"settingsUI": "plugin"}
  web/
    index.js               # Entry point (required)
    style.css              # Optional
```

Assets served at `/plugin-web/my-plugin/index.js`.

### index.js Contract

```javascript
import { registerPluginSettings } from '/static/shared/plugin-registry.js';
import pluginsAPI from '/static/shared/plugins-api.js';

export default {
  name: 'my-plugin',

  init(container) {
    registerPluginSettings({
      id: 'my-plugin',
      name: 'My Plugin',
      icon: '⚙️',
      helpText: 'Configure my plugin',

      render(container, settings) {
        // Build form HTML
        container.innerHTML = `
          <input type="text" id="mp-url" value="${settings.url || ''}">
        `;
      },

      load: () => pluginsAPI.getSettings('my-plugin'),
      save: (settings) => pluginsAPI.saveSettings('my-plugin', settings),

      getSettings(container) {
        // Extract form values
        return { url: container.querySelector('#mp-url').value };
      }
    });
  },

  destroy() { }
};
```

### Settings API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/webui/plugins/{name}/settings` | Read settings |
| PUT | `/api/webui/plugins/{name}/settings` | Save settings |
| DELETE | `/api/webui/plugins/{name}/settings` | Reset to defaults |

Settings are stored at `user/webui/plugins/{name}.json`.

### Available Imports

```javascript
import { showToast } from '/static/shared/toast.js';
import { showHelpModal } from '/static/shared/modal.js';
import { registerPluginSettings } from '/static/shared/plugin-registry.js';
import pluginsAPI from '/static/shared/plugins-api.js';
```

Use CSS variables for theme compatibility: `var(--bg-secondary)`, `var(--text)`, `var(--border)`, `var(--bg-hover)`.

---

## Plugin Signing & Verification

Sapphire uses ed25519 signatures to verify plugin integrity.

### Verification States

| State | Badge | Behavior |
|-------|-------|----------|
| **Signed** | Green "Signed" | Always loads |
| **Unsigned** | Yellow "Unsigned" | Blocked unless "Allow Unsigned Plugins" is on |
| **Tampered** | Red "Tampered" | Always blocked — no override |

### How It Works

Each signed plugin has a `plugin.sig` file containing:
- SHA256 hashes of every signable file (`.py`, `.json`, `.js`, `.css`, `.html`, `.md`)
- An ed25519 signature over the hash manifest

On scan, the loader verifies:
1. Signature matches the baked-in public key
2. Every file's hash matches the manifest
3. No unrecognized files were added after signing

### Sideloading (Unsigned Plugins)

`ALLOW_UNSIGNED_PLUGINS` defaults to **off**. Enable it in Settings > Plugins with the toggle. A danger dialog warns about the risks.

When enabled, unsigned plugins load with a warning. Tampered plugins are always blocked regardless of this setting.

### Signing Your Own Plugins

For plugin developers distributing through channels other than the official store:

1. Generate an ed25519 keypair
2. Hash all signable files in your plugin
3. Sign the hash manifest with your private key
4. Ship the `plugin.sig` alongside your plugin

Users install your public key to verify. The official Sapphire public key is baked into `core/plugin_verify.py`.

---

## Lifecycle

### Startup

1. `plugin_loader.scan()` reads `plugins/` and `user/plugins/`
2. Each `plugin.json` is validated and signature-checked
3. Enabled plugins get hooks, tools, voice commands, and schedules registered
4. Scheduler tasks are deferred if the scheduler hasn't initialized yet

### Live Toggle

Settings > Plugins calls `PUT /api/webui/plugins/toggle/{name}`:
- **Enable**: Loads immediately — all capabilities register
- **Disable**: Unloads immediately — hooks, tools, schedules removed

Unsigned/tampered plugins return 403 and the toggle reverts.

### Hot Reload (Dev)

`POST /api/plugins/{name}/reload` unloads and reloads a single plugin.

Set `SAPPHIRE_DEV=1` to enable file watching — plugins auto-reload when `.py` or `.json` files change (2s polling).

If reload fails, the plugin stays unloaded. No half-loaded state.

### Rescan

`POST /api/plugins/rescan` discovers new or removed plugin folders without restart. Returns `{"added": [...], "removed": [...]}`.

---

## Error Isolation

A buggy plugin never crashes the system. If a hook handler throws an exception, it's logged and skipped — the next handler fires normally. Tool execution errors are caught and returned as error messages to the AI.

---

## Complete Example

A plugin that combines multiple capabilities:

```
plugins/smart-home/
  plugin.json
  hooks/context.py
  hooks/quick_lights.py
  tools/devices.py
  schedule/lock_check.py
  web/
    index.js
```

```json
{
  "name": "smart-home",
  "version": "2.0.0",
  "description": "Full smart home integration",
  "author": "you",
  "url": "https://example.com",
  "priority": 50,
  "capabilities": {
    "hooks": {
      "prompt_inject": "hooks/context.py"
    },
    "voice_commands": [
      {
        "triggers": ["lights on", "lights off"],
        "match": "exact",
        "bypass_llm": true,
        "handler": "hooks/quick_lights.py"
      }
    ],
    "tools": ["tools/devices.py"],
    "schedule": [
      {
        "name": "Nightly Lock Check",
        "cron": "0 23 * * *",
        "handler": "schedule/lock_check.py"
      }
    ],
    "web": { "settingsUI": "plugin" }
  }
}
```

---

## Advanced Patterns

Real patterns from existing plugins that are worth knowing.

### Settings File Reading

Tools read their config from `user/webui/plugins/{name}.json`. Always merge with defaults:

```python
from pathlib import Path
import json

DEFAULTS = {"timeout": 30, "max_results": 10}

def _load_settings():
    path = Path(__file__).parent.parent.parent.parent / "user" / "webui" / "plugins" / "my-plugin.json"
    settings = DEFAULTS.copy()
    if path.exists():
        try:
            user = json.loads(path.read_text())
            settings.update(user)
        except Exception:
            pass
    return settings
```

### Privacy-First Tool Design

Never expose raw credentials (emails, keys, addresses) to the AI. Resolve at execution time:

```python
# BAD — AI sees raw email addresses
def execute(function_name, arguments, config):
    return f"Contacts: alice@example.com, bob@example.com", True

# GOOD — AI only sees names and IDs
def execute(function_name, arguments, config):
    contacts = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    return json.dumps(contacts), True

# When sending, resolve the address internally:
def _send(recipient_id):
    person = lookup_by_id(recipient_id)
    actual_email = person["email"]  # never shown to AI
```

### Command Blacklists

For tools that execute commands (SSH, shell), use regex blacklists with fallback:

```python
BLACKLIST = ["rm -rf /", "mkfs", "dd if=/dev", ":(){ :|:& };:"]

def _check_blacklist(command):
    for pattern in BLACKLIST:
        try:
            if re.search(pattern, command):
                return f"Blocked: matches '{pattern}'"
        except re.error:
            if pattern in command:  # fallback to substring
                return f"Blocked: contains '{pattern}'"
    return None  # safe
```

### Caching with Scope Keys

For tools that fetch external data, cache per-scope with TTL:

```python
_cache = {}  # scope -> {data, timestamp}
CACHE_TTL = 60

def _get_cached(scope):
    entry = _cache.get(scope)
    if entry and time.time() - entry["timestamp"] < CACHE_TTL:
        return entry["data"]
    return None

def _invalidate(scope):
    _cache.pop(scope, None)  # call after writes
```

### Web UI Style Injection

Plugin web UIs inject scoped CSS into the document head:

```javascript
function injectStyles() {
    if (document.getElementById('my-plugin-styles')) return;
    const style = document.createElement('style');
    style.id = 'my-plugin-styles';
    style.textContent = `
        .my-plugin-item {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: var(--space-md);
        }
        .my-plugin-item:hover { background: var(--bg-hover); }
    `;
    document.head.appendChild(style);
}
```

### CSRF Headers for Custom Fetches

Plugin web UIs making custom API calls need CSRF tokens:

```javascript
function csrfHeaders(extra = {}) {
    const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
    return { 'X-CSRF-Token': token, 'Content-Type': 'application/json', ...extra };
}

// Usage
const res = await fetch('/api/my-endpoint', {
    method: 'POST',
    headers: csrfHeaders(),
    body: JSON.stringify({ key: 'value' })
});
```

---

## Plugin Ideas

*Krem asked Claude to brainstorm non-obvious ways to use the plugin system. These demonstrate how deep the hooks go — plugins aren't just toggles, they can fundamentally reshape how Sapphire behaves.*

### Dynamic Voice Switcher
A `post_chat` hook that analyzes the AI's response tone and adjusts TTS voice/speed in real-time. Calm voice for empathy, faster delivery for excitement, whisper for secrets.

```python
def post_chat(event):
    system = event.metadata.get("system")
    if not system or not system.tts:
        return
    text = event.response or ""
    if any(w in text.lower() for w in ["sorry", "understand", "feel"]):
        system.tts.set_speed(0.9)
        system.tts.set_voice("af_heart")
    elif "!" in text:
        system.tts.set_speed(1.3)
```

### Custom TTS Engine Redirect
Replace Sapphire's TTS pipeline entirely. A `pre_tts` hook cancels built-in TTS, and a `post_chat` hook routes to your own engine (ElevenLabs, Bark, Coqui, etc.):

```python
# hooks/redirect_tts.py
import requests

def pre_tts(event):
    event.skip_tts = True  # cancel built-in TTS

def post_chat(event):
    system = event.metadata.get("system")
    if not system or not event.response:
        return
    # Call your own TTS server
    audio = requests.post("http://localhost:5050/tts",
                          json={"text": event.response}).content
    # Play via system audio (or your own player)
```

### Ambient Context Injection
A `prompt_inject` hook that queries external APIs and injects real-world context into every prompt — the AI "just knows" without needing a tool call:

```python
# hooks/ambient.py
import requests, time

_cache = {"data": "", "ts": 0}

def prompt_inject(event):
    now = time.time()
    if now - _cache["ts"] > 300:  # refresh every 5 min
        try:
            weather = requests.get("http://ha-server/api/states/weather.home",
                                   headers={"Authorization": "Bearer ..."}).json()
            _cache["data"] = f"Weather: {weather['state']}, {weather['attributes']['temperature']}°F"
            _cache["ts"] = now
        except Exception:
            pass
    if _cache["data"]:
        event.context_parts.append(_cache["data"])
```

### Voice Macros
Voice commands that chain multiple system actions. Say "goodnight" and it dims lights, sets DND, and changes the AI's voice to a whisper:

```json
{
  "capabilities": {
    "voice_commands": [{
      "triggers": ["goodnight", "good night"],
      "match": "exact",
      "bypass_llm": true,
      "handler": "hooks/goodnight.py"
    }]
  }
}
```

```python
# hooks/goodnight.py
import requests

def pre_chat(event):
    system = event.metadata.get("system")
    if system and system.tts:
        system.tts.set_voice("af_heart")
        system.tts.set_speed(0.8)

    # Call Home Assistant scene
    try:
        requests.post("http://ha:8123/api/services/scene/turn_on",
                       json={"entity_id": "scene.goodnight"},
                       headers={"Authorization": "Bearer ..."})
    except Exception:
        pass

    event.skip_llm = True
    event.ephemeral = True
    event.response = "Goodnight. Lights dimmed, quiet mode on."
    event.stop_propagation = True
```

### Tool Guardrails
A `pre_execute` hook that validates tool arguments before execution. Block dangerous SSH commands, cap Bitcoin sends, enforce email whitelists:

```python
# hooks/guardrails.py
MAX_BTC_SEND = 0.01  # satoshi safety net

def pre_execute(event):
    if event.function_name == "send_bitcoin":
        amount = event.arguments.get("amount", 0)
        if amount > MAX_BTC_SEND:
            event.skip_llm = True
            event.result = f"Blocked: {amount} BTC exceeds limit of {MAX_BTC_SEND}"
            return

    if event.function_name == "ssh_execute":
        cmd = event.arguments.get("command", "")
        if "sudo" in cmd:
            event.arguments["command"] = cmd.replace("sudo ", "")  # silently strip sudo
```

### Conversation Summarizer
A `post_chat` hook that auto-generates summaries every N turns by calling the LLM directly:

```python
# hooks/summarizer.py
from core.plugin_loader import plugin_loader

def post_chat(event):
    system = event.metadata.get("system")
    if not system:
        return
    state = plugin_loader.get_plugin_state("summarizer")
    turn_count = (state.get("turns", 0) + 1)
    state.save("turns", turn_count)

    if turn_count % 10 == 0:  # every 10 turns
        messages = system.llm_chat.session_manager.get_messages()
        last_10 = [m["content"] for m in messages[-20:] if isinstance(m.get("content"), str)]
        summary_prompt = f"Summarize this conversation excerpt:\n\n{'\\n'.join(last_10)}"
        summary = system.llm_chat.chat(summary_prompt)
        state.save("last_summary", summary)
```

### Privacy Filter
A `pre_tts` hook that strips PII before speech — phone numbers, addresses, and emails are redacted from audio output but remain in the text response:

```python
# hooks/privacy_tts.py
import re

PII_PATTERNS = [
    (r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[phone]'),      # phone numbers
    (r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', '[email]'),          # emails
    (r'\b\d{1,5}\s+[\w\s]+(?:St|Ave|Blvd|Dr|Ln)\b', '[address]'),  # street addresses
]

def pre_tts(event):
    text = event.tts_text or ""
    for pattern, replacement in PII_PATTERNS:
        text = re.sub(pattern, replacement, text)
    event.tts_text = text
```

### Smart Argument Rewriting
A `pre_execute` hook can silently fix or enhance tool arguments before they execute:

```python
def pre_execute(event):
    # Auto-expand relative paths for SSH
    if event.function_name == "ssh_execute":
        cmd = event.arguments.get("command", "")
        if cmd.startswith("cd ~/"):
            event.arguments["command"] = cmd.replace("~/", "/home/user/")

    # Auto-add context to knowledge saves
    if event.function_name == "save_knowledge":
        if not event.arguments.get("source"):
            event.arguments["source"] = "auto-added by plugin"
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/webui/plugins` | List all plugins with metadata |
| PUT | `/api/webui/plugins/toggle/{name}` | Enable/disable (live) |
| POST | `/api/plugins/rescan` | Discover new/removed plugins |
| POST | `/api/plugins/{name}/reload` | Hot-reload (dev) |
| GET | `/api/webui/plugins/{name}/settings` | Read plugin settings |
| PUT | `/api/webui/plugins/{name}/settings` | Save plugin settings |
| DELETE | `/api/webui/plugins/{name}/settings` | Reset plugin settings |
| GET | `/plugin-web/{name}/{path}` | Serve plugin web assets |

### Plugin List Response

```json
{
  "plugins": [
    {
      "name": "ssh",
      "enabled": true,
      "locked": false,
      "title": "SSH",
      "settingsUI": "plugin",
      "verified": true,
      "verify_msg": "verified",
      "version": "1.0.0",
      "author": "sapphire",
      "url": "https://sapphireblue.dev"
    }
  ],
  "locked": ["setup-wizard", "backup", "continuity"]
}
```

---

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
  email/
  bitcoin/
  homeassistant/
  image-gen/
  toolmaker/

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

---

## Web UI Shared Modules

Plugin web UIs can import these modules from `/static/shared/`:

| Module | Key Exports | Purpose |
|--------|------------|---------|
| `plugin-registry.js` | `registerPluginSettings(config)`, `unregisterPluginSettings(id)` | Register/remove settings tabs |
| `plugins-api.js` | `listPlugins()`, `getSettings(name)`, `saveSettings(name, data)`, `resetSettings(name)`, `togglePlugin(name)` | Plugin backend API wrapper (auto-injects CSRF) |
| `toast.js` | `showToast(msg, type, duration)`, `showActionToast(msg, label, callback, type, duration)` | Non-blocking notifications (`info`, `success`, `warning`, `error`) |
| `modal.js` | `showModal(title, fields, onSave, opts)`, `showConfirm(msg, onConfirm)`, `showPrompt(title, label, default)`, `showHelpModal(title, text)`, `escapeHtml(str)` | Dialogs with auto form serialization |
| `danger-confirm.js` | `showDangerConfirm(config)`, `showDangerBanner(container, msg)` | High-stakes type-to-confirm gates |
| `fetch.js` | `fetchWithTimeout(url, opts, timeout)`, `sessionId` | Pre-configured fetch with CSRF, 401 redirect, timeout |

### Modal Field Types

`showModal()` accepts an array of field objects:

| Type | Properties | Notes |
|------|-----------|-------|
| `text` | `id`, `label`, `value`, `readonly` | Single-line input |
| `number` | `id`, `label`, `value`, `readonly` | Numeric input |
| `textarea` | `id`, `label`, `value`, `rows` | Multi-line (default 6 rows) |
| `select` | `id`, `label`, `options`, `labels`, `value` | Dropdown (`labels` optional) |
| `checkboxes` | `id`, `label`, `options` (object), `selected` (array) | Multi-select, returns array of keys |
| `html` | `value` | Raw HTML, skipped in serialization |

### CSS Variables

Use CSS variables for theme compatibility. Key variables:

```css
/* Backgrounds */
--bg: #121212          --bg-secondary: #1a1a1a   --bg-tertiary: #2c2c2c
--bg-hover: #383838

/* Text */
--text: #e0e0e0        --text-secondary: #ccc    --text-muted: #888

/* Borders */
--border: #333         --border-light: #444

/* Semantic */
--success: #4caf50     --warning: #ff9800        --error: #ef5350
--accent-blue: #4a9eff --trim: #4a9eff           /* user-configurable accent */

/* Spacing (density-aware) */
--space-xs: 4px   --space-sm: 8px   --space-md: 12px   --space-lg: 16px

/* Radius */
--radius-sm: 4px  --radius-md: 6px  --radius-lg: 8px

/* Fonts */
--font-sm: 11px   --font-base: 13px --font-md: 14px    --font-lg: 16px
```

---

## For Sapphire (AI Self-Reference)

When creating or modifying plugins:

- Plugin = folder in `plugins/{name}/` with `plugin.json` manifest
- `plugin.json` requires `name` field, everything else optional
- Hooks = Python functions receiving mutable `HookEvent` object
- Tools = `TOOLS` list + `execute(function_name, arguments, config)` returning `(str, bool)`
- Tool schema supports `is_local` (bool or `"endpoint"`) and `network: true` flags
- Voice commands = pre_chat hooks with trigger matching, `bypass_llm: true` for instant response
- Schedule = cron tasks calling `run(event)` handler, event has `system`, `config`, `task`, `plugin_state`
- Web settings = `web/index.js` using `registerPluginSettings()`, served at `/plugin-web/{name}/`
- State = `plugin_loader.get_plugin_state(name)` for persistent key-value storage
- System access = `event.metadata.get("system")` in `pre_chat`, `post_chat`, `pre_execute` hooks
- `prompt_inject`, `post_execute`, `pre_tts` do NOT get system metadata — only `config`
- System gives access to: `tts` (voice/speed/pitch/speak/stop), `toggle_stt()`, `toggle_wakeword()`, `llm_chat` (chat/history/prompt), `function_manager` (tools/scopes)
- Enable/disable live via `PUT /api/webui/plugins/toggle/{name}`
- All 10 hooks: `post_stt`, `pre_chat`, `prompt_inject`, `post_llm`, `post_chat`, `pre_execute`, `post_execute`, `pre_tts`, `post_tts`, `on_wake`
- `post_stt` fires only for voice input (after STT transcription, before chat pipeline)
- `post_llm` fires after LLM response, before history save + TTS — mutate `response` to filter/translate/style
- `post_tts` fires after playback completes or is stopped (daemon thread, observational)
- `on_wake` fires when wakeword detected, before recording starts (notification only, must return fast)
- Error isolation: exceptions logged and skipped, never crash pipeline
- Signing: ed25519 signatures in `plugin.sig`, tampered = always blocked, unsigned = blocked unless sideloading enabled
- Settings stored at `user/webui/plugins/{name}.json`, read via `GET /api/webui/plugins/{name}/settings`
- Settings files are in `user/` (gitignored) — never tracked by git
- Multi-account tools use ContextVar scopes: `scope_email`, `scope_bitcoin`, `scope_knowledge`, etc.
- Web UI modules available: `plugin-registry.js`, `plugins-api.js`, `toast.js`, `modal.js`, `danger-confirm.js`, `fetch.js`
- CSS variables for theming: `--bg`, `--text`, `--border`, `--trim`, `--success`, `--error`, etc.
- Always guard system access with `hasattr()` checks — subsystems may be None if disabled
