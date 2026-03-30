# Daemons

Daemons are long-running background processes that listen for external events and feed them into Sapphire's task scheduler. When an event arrives (new Telegram message, incoming email, etc.), the daemon emits it and the scheduler fires any matching tasks.

## How It Works

```
Daemon thread (your code)
  → listens for external events (polling, websocket, etc.)
  → calls plugin_loader.emit_daemon_event(source_name, json_payload)
    → scheduler finds tasks matching that source
    → task executes (LLM chat with event data as context)
    → if auto-reply: reply_handler routes response back to source
```

## Manifest Declaration

```json
{
  "capabilities": {
    "daemon": {
      "entry": "daemon.py",
      "event_sources": [
        {
          "name": "my_event",
          "label": "My Event",
          "description": "When something happens in my service",
          "filter_fields": [
            {"key": "sender", "label": "Sender Name"},
            {"key": "channel", "label": "Channel"}
          ],
          "task_fields": [
            {
              "key": "account",
              "type": "select",
              "label": "Account",
              "required": true,
              "dynamic": "/api/plugin/my-plugin/accounts",
              "help": "Which account to monitor"
            },
            {
              "key": "auto_reply",
              "type": "boolean",
              "label": "Auto-reply",
              "default": false
            }
          ]
        }
      ]
    }
  }
}
```

### Manifest Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `entry` | string | Yes | Path to daemon module (relative to plugin dir) |
| `event_sources` | array | No | Event types this daemon can emit |

### Event Source Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique event identifier (used in `emit_daemon_event`) |
| `label` | string | Yes | Human-readable name (shown in Schedule UI) |
| `description` | string | No | Tooltip/help text |
| `filter_fields` | array | No | Fields users can filter on when creating tasks |
| `task_fields` | array | No | Per-task configuration fields shown in Schedule UI |

### Filter Fields

Filter fields let users narrow which events trigger their task. Each filter is matched against the event payload JSON.

```json
{"key": "username", "label": "Username"}
```

The scheduler ANDs all filters — every filter must match for the task to fire.

### Task Fields

Task fields are per-task configuration shown in the Schedule UI when creating a daemon task. They support these types:

| Type | Description | Extra Properties |
|------|-------------|-----------------|
| `select` | Dropdown | `options` (static) or `dynamic` (API URL for async loading) |
| `boolean` | Toggle | `default` |

The `dynamic` property fetches options from an API endpoint at render time — useful for account lists that change.

---

## Daemon Module

Your `daemon.py` must export `start()` and `stop()`:

```python
# daemon.py — Minimal daemon skeleton

import logging
import threading

logger = logging.getLogger(__name__)

_thread = None
_stop_event = threading.Event()
_plugin_loader = None


def start(plugin_loader, settings):
    """Called by plugin_loader when the plugin loads."""
    global _thread, _plugin_loader
    _plugin_loader = plugin_loader
    _stop_event.clear()

    _thread = threading.Thread(target=_run, daemon=True, name="my-daemon")
    _thread.start()

    # Register reply handler if you support auto-reply
    plugin_loader.register_reply_handler("my-plugin", _reply_handler)
    logger.info("[MY-PLUGIN] Daemon started")


def stop():
    """Called by plugin_loader when the plugin unloads."""
    global _thread
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    _thread = None
    logger.info("[MY-PLUGIN] Daemon stopped")
```

### start(plugin_loader, settings)

| Param | Type | Description |
|-------|------|-------------|
| `plugin_loader` | `PluginLoader` | The plugin loader instance — used for emitting events and reading state |
| `settings` | `dict` | Plugin settings (merged manifest defaults + user overrides) |

Called once when the plugin loads. If the scheduler isn't ready yet (early boot), the call is deferred automatically — you don't need to handle this.

### stop()

Called when the plugin unloads (toggle off, hot-reload, shutdown). Clean up threads, close connections.

---

## Emitting Events

When your daemon detects something interesting, emit an event:

```python
import json

def _run():
    while not _stop_event.is_set():
        events = poll_my_service()
        for event in events:
            payload = json.dumps({
                "account": "main",
                "sender": event.sender,
                "channel": event.channel,
                "text": event.text,
            })
            _plugin_loader.emit_daemon_event("my_event", payload)
        _stop_event.wait(60)  # poll interval
```

**`emit_daemon_event(source_name, event_data)`**

| Param | Type | Description |
|-------|------|-------------|
| `source_name` | `str` | Must match an `event_sources[].name` from your manifest |
| `event_data` | `str` | JSON string — the event payload passed to matching tasks |

The payload keys should include anything declared in your `filter_fields` so the scheduler can match filters. Include enough context for the LLM to understand what happened.

---

## Reply Handlers

If your daemon supports auto-reply (sending the AI's response back to the source platform), register a reply handler in `start()`:

```python
plugin_loader.register_reply_handler("my-plugin", _reply_handler)
```

The handler is called when an event-triggered task completes:

```python
def _reply_handler(task, event_data, response_text):
    """Route LLM response back to the source.

    Args:
        task: The task dict that was triggered
        event_data: The original event payload (dict, already parsed)
        response_text: The LLM's response text
    """
    channel = event_data.get("channel")
    send_to_my_service(channel, response_text)
```

The reply handler name in `register_reply_handler` must match your plugin name, and the source name must be registered by your plugin — the system uses this to look up the correct handler.

---

## Account-Aware Daemons

If your daemon manages multiple accounts, use `active_daemon_accounts()` to only connect accounts that have active tasks:

```python
active = plugin_loader.active_daemon_accounts("my_event")
# Returns: {"account1", "account2"} — only accounts with enabled daemon tasks
```

This avoids connecting to accounts nobody is listening on.

---

## Lifecycle

1. Plugin loads → `start(plugin_loader, settings)` called
2. If scheduler not ready → start is deferred until scheduler registers
3. Daemon thread runs, polling/listening for events
4. Event detected → `emit_daemon_event()` → scheduler fires matching tasks
5. Task completes with auto-reply → reply handler routes response back
6. Plugin unloads → `stop()` called → clean up threads/connections

Daemons survive hot-reload — `stop()` is called before unload, then `start()` again after reload.

---

## Real Examples

| Plugin | Event Source | What It Does |
|--------|------------|--------------|
| `plugins/telegram/` | `telegram_message` | Telethon client, listens for incoming messages via asyncio event loop |
| `plugins/discord/` | `discord_message` | Discord.py bot, listens for channel messages |
| `plugins/email/` | `email_message` | IMAP polling (configurable interval), checks for UNSEEN mail |
| `plugins/mcp_client/` | — | MCP server connections (daemon without event sources) |

---

## Reference for AI

DAEMON SYSTEM:
- Plugin declares `capabilities.daemon` with `entry` (module path) and `event_sources` (what events it emits)
- Module exports `start(plugin_loader, settings)` and `stop()`
- Daemon thread listens for external events, calls `plugin_loader.emit_daemon_event(source_name, json_payload)`
- Scheduler finds tasks matching source, fires them with event data as context
- Reply handlers route LLM responses back to source platform
- `active_daemon_accounts(source_name)` returns set of accounts with active tasks
- Filter fields: AND-matched against event payload
- Task fields: per-task config (select with static/dynamic options, boolean)
- Lifecycle: start on load, stop on unload, survives hot-reload
