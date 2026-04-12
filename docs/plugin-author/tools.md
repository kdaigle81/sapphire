# Plugin Tools

Plugin tools are registered with the function manager and the AI calls them like any built-in tool. The format is the same across all plugins (see `plugins/memory/tools/` for examples of core tools, or `plugins/email/tools/` for a plugin tool).

For simple tool creation without a full plugin, see [TOOLMAKER.md](../TOOLMAKER.md).

---

## Tool File Format

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

### Required Exports

| Export | Type | Description |
|--------|------|-------------|
| `ENABLED` | bool | Whether tool is active |
| `EMOJI` | str | Display icon |
| `AVAILABLE_FUNCTIONS` | list | Function names this file provides |
| `TOOLS` | list | OpenAI-compatible function schemas |
| `execute()` | function | Dispatcher — returns `(message, success)` |

### Manifest Declaration

```json
"capabilities": {
  "tools": ["tools/my_tool.py"]
}
```

---

## Schema Flags

Inside each tool's schema dict:

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

---

## Multi-Account Scope Support

Tools that support multiple accounts (email, bitcoin, etc.) can read the active scope:

```python
from core.chat.function_manager import scope_email

def execute(function_name, arguments, config):
    account = scope_email.get()  # returns active account name (ContextVar)
    creds = load_credentials(account)
    # ... use account-specific credentials
```

Available scope ContextVars: `scope_email`, `scope_bitcoin`, `scope_knowledge`, `scope_memory`, `scope_people`, `scope_rag`, `scope_goal`.

---

## Reading Plugin Settings

Tools can load their own plugin's settings:

```python
import json
from pathlib import Path

def _load_settings():
    path = Path("user/webui/plugins/my-plugin.json")
    if path.exists():
        return json.loads(path.read_text())
    return {}
```

Or via the plugin loader (merges with manifest defaults):

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

PluginState is thread-safe — daemon threads, continuity tasks, and API handlers can all read/write the same plugin's state concurrently without data loss.

For heavier storage, plugins can create their own SQLite database.

---

## Advanced Patterns

### Privacy-First Design

Never expose raw credentials (emails, keys, addresses) to the AI. Resolve at execution time:

```python
# BAD — AI sees raw email addresses
def execute(function_name, arguments, config):
    return f"Contacts: alice@example.com, bob@example.com", True

# GOOD — AI only sees names and IDs
def execute(function_name, arguments, config):
    contacts = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    return json.dumps(contacts), True
```

### Command Blacklists

For tools that execute commands (SSH, shell):

```python
BLACKLIST = ["rm -rf /", "mkfs", "dd if=/dev", ":(){ :|:& };:"]

def _check_blacklist(command):
    for pattern in BLACKLIST:
        try:
            if re.search(pattern, command):
                return f"Blocked: matches '{pattern}'"
        except re.error:
            if pattern in command:
                return f"Blocked: contains '{pattern}'"
    return None
```

### Caching with Scope Keys

For tools that fetch external data, cache per-scope with TTL:

```python
_cache = {}
CACHE_TTL = 60

def _get_cached(scope):
    entry = _cache.get(scope)
    if entry and time.time() - entry["timestamp"] < CACHE_TTL:
        return entry["data"]
    return None

def _invalidate(scope):
    _cache.pop(scope, None)
```

Tools are added to toolsets and the AI calls them contextually. See [TOOLS.md](../TOOLS.md) for the user-facing tools guide.
