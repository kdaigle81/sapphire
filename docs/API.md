# API Reference

Sapphire runs a single FastAPI server on port 8073 (HTTPS). Every endpoint below requires authentication — either a browser session or an API key.

Routes are split across multiple modules under `core/routes/` — this doc covers all ~280 endpoints.

## Authentication

### Browser Session
Log in at `/login` with your password. Sessions last 30 days.

### API Key (Programmatic Access)
For scripts or external tools, send your API key as a header:

```bash
curl -k https://localhost:8073/api/status \
  -H "X-API-Key: $(cat ~/.config/sapphire/secret_key)"
```

The key is the bcrypt hash stored in your config directory:

| OS | Path |
|----|------|
| Linux | `~/.config/sapphire/secret_key` |
| macOS | `~/Library/Application Support/Sapphire/secret_key` |
| Windows | `%APPDATA%\Sapphire\secret_key` |

This file is created during initial setup. To reset, delete it and restart Sapphire.

### CSRF
CSRF tokens are required for browser sessions on POST/PUT/DELETE requests. API key auth **bypasses CSRF** — no extra headers needed.

### Rate Limiting
5 attempts per 60 seconds per IP on auth endpoints.

---

## Endpoints

### Core

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/status` | Unified UI state (prompt, context, spice, TTS/STT readiness) |
| GET | `/api/init` | Mega initialization (all toolsets, prompts, personas, spices, settings) |

### Chat

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/chat` | Send message, get response |
| POST | `/api/chat/stream` | Streaming SSE response |
| POST | `/api/cancel` | Cancel active stream |
| GET | `/api/events` | SSE event stream (real-time UI updates) |
| GET | `/api/history` | Get chat message history |

### Chat Sessions

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/chats` | List all chats |
| POST | `/api/chats` | Create new chat |
| POST | `/api/chats/private` | Create private chat |
| DELETE | `/api/chats/{name}` | Delete chat |
| POST | `/api/chats/{name}/activate` | Switch active chat |
| GET | `/api/chats/active` | Get active chat name |
| GET | `/api/chats/{name}/settings` | Get chat settings |
| PUT | `/api/chats/{name}/settings` | Update chat settings |

### Message History

| Method | Endpoint | Purpose |
|--------|----------|---------|
| DELETE | `/api/history/messages` | Remove messages (by count, user message, or clear all with count=-1) |
| POST | `/api/history/messages/remove-last-assistant` | Remove last assistant message |
| POST | `/api/history/messages/remove-from-assistant` | Remove from last assistant message onward |
| DELETE | `/api/history/tool-call/{id}` | Delete specific tool call |
| POST | `/api/history/messages/edit` | Edit a message |
| GET | `/api/history/raw` | Export raw chat history |
| POST | `/api/history/import` | Import chat history |

### TTS / STT / Audio

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/tts` | Generate TTS audio |
| POST | `/api/tts/preview` | Preview voice sample |
| GET | `/api/tts/status` | TTS server status |
| POST | `/api/tts/stop` | Stop TTS playback |
| POST | `/api/tts/test` | Test TTS provider connectivity |
| GET | `/api/tts/voices` | List voices for active TTS provider |
| POST | `/api/tts/voices` | List voices (with optional api_key for pre-save browsing) |
| POST | `/api/transcribe` | Transcribe audio file |
| POST | `/api/mic/active` | Set web mic active state (suppresses wakeword) |
| POST | `/api/upload/image` | Upload image for chat |
| GET | `/api/audio/devices` | List audio devices |
| POST | `/api/audio/test-input` | Test input device |
| POST | `/api/audio/test-output` | Test output device |

### Settings

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/settings` | Get all settings |
| GET | `/api/settings/{key}` | Get a single setting |
| PUT | `/api/settings/{key}` | Update a single setting |
| DELETE | `/api/settings/{key}` | Reset a setting to default |
| PUT | `/api/settings/batch` | Batch update multiple settings |
| POST | `/api/settings/reload` | Force reload from disk |
| POST | `/api/settings/reset` | Reset all settings to defaults |
| GET | `/api/settings/help` | Get setting descriptions |
| GET | `/api/settings/help/{key}` | Get help for a specific setting |
| GET | `/api/settings/tiers` | Get hot vs restart-required status |
| GET | `/api/settings/tool-settings` | Get tool-specific settings |
| GET | `/api/settings/chat-defaults` | Get chat default settings |
| PUT | `/api/settings/chat-defaults` | Update chat defaults |
| DELETE | `/api/settings/chat-defaults` | Reset chat defaults to factory |
| GET | `/api/settings/wakeword-models` | List available wakeword models |

### Credentials & SOCKS Proxy

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/credentials` | List configured credential keys |
| PUT | `/api/credentials/llm/{provider}` | Set LLM API key |
| DELETE | `/api/credentials/llm/{provider}` | Remove LLM API key |
| GET | `/api/credentials/socks` | Get SOCKS proxy config |
| PUT | `/api/credentials/socks` | Set SOCKS proxy config |
| DELETE | `/api/credentials/socks` | Remove SOCKS proxy config |
| POST | `/api/credentials/socks/test` | Test SOCKS proxy connection |

### LLM Providers

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/llm/providers` | List LLM providers |
| PUT | `/api/llm/providers/{key}` | Update provider config |
| PUT | `/api/llm/fallback-order` | Set LLM fallback order |
| POST | `/api/llm/test/{provider}` | Test LLM connection |
| POST | `/api/llm/custom-providers` | Add a custom LLM provider |
| DELETE | `/api/llm/custom-providers/{key}` | Remove a custom LLM provider |
| GET | `/api/llm/custom-providers/{key}/models` | Fetch models from a custom provider |
| GET | `/api/llm/presets` | List LLM provider presets |

### Provider Registry (TTS / STT)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/tts/providers` | List TTS providers (core + plugin) |
| GET | `/api/stt/providers` | List STT providers (core + plugin) |

### Embeddings

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/embedding/test` | Test embedding provider |

### Privacy

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/privacy` | Get privacy mode status |
| PUT | `/api/privacy` | Toggle privacy mode |
| PUT | `/api/privacy/start-mode` | Set privacy mode default at startup |

### System Prompt

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/system/status` | System status (detailed) |
| GET | `/api/system/prompt` | Get current system prompt |
| POST | `/api/system/prompt` | Set system prompt directly |
| POST | `/api/system/merge-updates` | Merge missing prompts + personas from app updates |

### Personas

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/personas` | List all personas |
| GET | `/api/personas/{name}` | Get persona details |
| POST | `/api/personas` | Create persona |
| PUT | `/api/personas/{name}` | Update persona |
| DELETE | `/api/personas/{name}` | Delete persona |
| POST | `/api/personas/{name}/duplicate` | Clone persona |
| POST | `/api/personas/{name}/load` | Activate persona on current chat |
| POST | `/api/personas/from-chat` | Create persona from current chat settings |
| POST | `/api/personas/{name}/avatar` | Upload avatar (max 4MB) |
| DELETE | `/api/personas/{name}/avatar` | Remove avatar |
| GET | `/api/personas/{name}/avatar` | Get avatar image |
| PUT | `/api/personas/default` | Set default persona for new chats |
| DELETE | `/api/personas/default` | Clear default persona |
| GET | `/api/personas/{name}/export` | Export persona as portable JSON bundle |
| POST | `/api/personas/import` | Import persona from JSON bundle |

### Prompts

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/prompts` | List prompts |
| GET | `/api/prompts/{name}` | Get prompt details |
| PUT | `/api/prompts/{name}` | Create or update prompt |
| DELETE | `/api/prompts/{name}` | Delete prompt |
| POST | `/api/prompts/{name}/load` | Activate prompt on current chat |
| POST | `/api/prompts/reload` | Reload from disk |
| POST | `/api/prompts/reset` | Reset to defaults |
| POST | `/api/prompts/merge` | Merge defaults into current |
| POST | `/api/prompts/reset-chat-defaults` | Reset chat defaults to factory |
| GET | `/api/prompts/components` | List prompt components |
| PUT | `/api/prompts/components/{type}/{key}` | Save prompt component |
| DELETE | `/api/prompts/components/{type}/{key}` | Delete prompt component |

### Toolsets

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/toolsets` | List toolsets (?filter=sidebar to exclude module-level) |
| GET | `/api/toolsets/current` | Get active toolset |
| POST | `/api/toolsets/{name}/activate` | Activate toolset |
| POST | `/api/toolsets/custom` | Save custom toolset |
| DELETE | `/api/toolsets/{name}` | Delete toolset |
| POST | `/api/toolsets/{name}/emoji` | Set toolset emoji |
| GET | `/api/functions` | List all available functions |
| POST | `/api/functions/enable` | Enable specific functions |

### Spices

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/spices` | List all spices |
| POST | `/api/spices` | Add a new spice to a category |
| PUT | `/api/spices/{category}/{index}` | Update a spice |
| DELETE | `/api/spices/{category}/{index}` | Delete a spice |
| POST | `/api/spices/category` | Create spice category |
| PUT | `/api/spices/category/{name}` | Rename spice category |
| DELETE | `/api/spices/category/{name}` | Delete spice category |
| POST | `/api/spices/category/{name}/emoji` | Set category emoji |
| POST | `/api/spices/category/{name}/toggle` | Enable/disable category |
| POST | `/api/spices/reload` | Reload spices from disk |

### Spice Sets

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/spice-sets` | List spice sets |
| GET | `/api/spice-sets/current` | Get active spice set |
| POST | `/api/spice-sets/{name}/activate` | Activate spice set |
| POST | `/api/spice-sets/custom` | Save custom spice set |
| DELETE | `/api/spice-sets/{name}` | Delete spice set |
| POST | `/api/spice-sets/{name}/emoji` | Set spice set emoji |

### Memory

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/memory/scopes` | List memory scopes |
| POST | `/api/memory/scopes` | Create scope |
| DELETE | `/api/memory/scopes/{name}` | Delete scope |
| GET | `/api/memory/list` | List memories (grouped by label) |
| PUT | `/api/memory/{id}` | Update memory |
| DELETE | `/api/memory/{id}` | Delete memory |
| GET | `/api/memory/export` | Export all memories in scope as JSON |
| POST | `/api/memory/import` | Import memories from JSON |
| GET | `/api/memory/duplicates` | Find near-duplicate memories via vector similarity |

### Knowledge

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/knowledge/scopes` | List knowledge scopes |
| POST | `/api/knowledge/scopes` | Create scope |
| DELETE | `/api/knowledge/scopes/{name}` | Delete scope |
| GET | `/api/knowledge/tabs` | List knowledge tabs (in scope) |
| POST | `/api/knowledge/tabs` | Create tab |
| GET | `/api/knowledge/tabs/{id}` | Get tab with entries |
| PUT | `/api/knowledge/tabs/{id}` | Update tab |
| DELETE | `/api/knowledge/tabs/{id}` | Delete tab |
| POST | `/api/knowledge/tabs/{id}/entries` | Add entry |
| POST | `/api/knowledge/tabs/{id}/upload` | Upload file (auto-chunks + embeds) |
| DELETE | `/api/knowledge/tabs/{id}/file/{name}` | Delete uploaded file entries |
| PUT | `/api/knowledge/entries/{id}` | Update entry |
| DELETE | `/api/knowledge/entries/{id}` | Delete entry |
| GET | `/api/knowledge/tabs/{id}/export` | Export knowledge tab as JSON |
| POST | `/api/knowledge/tabs/import` | Import knowledge tab from JSON |

### People

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/knowledge/people/scopes` | List people scopes |
| POST | `/api/knowledge/people/scopes` | Create scope |
| DELETE | `/api/knowledge/people/scopes/{name}` | Delete scope |
| GET | `/api/knowledge/people` | List people (in scope) |
| POST | `/api/knowledge/people` | Create/update person |
| DELETE | `/api/knowledge/people/{id}` | Delete person |
| POST | `/api/knowledge/people/import-vcf` | Import vCard file |
| GET | `/api/knowledge/people/export` | Export people as JSON |
| POST | `/api/knowledge/people/import` | Import people from JSON |

### Goals

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/goals/scopes` | List goal scopes |
| POST | `/api/goals/scopes` | Create scope |
| DELETE | `/api/goals/scopes/{name}` | Delete scope |
| GET | `/api/goals` | List goals (filtered by scope/status) |
| GET | `/api/goals/{id}` | Get a single goal |
| POST | `/api/goals` | Create goal |
| PUT | `/api/goals/{id}` | Update goal |
| POST | `/api/goals/{id}/progress` | Add progress note |
| DELETE | `/api/goals/{id}` | Delete goal |

### Per-Chat Documents (RAG)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/chats/{name}/documents` | Upload document to chat |
| GET | `/api/chats/{name}/documents` | List chat documents |
| DELETE | `/api/chats/{name}/documents/{file}` | Remove document |

### Story Engine

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/story/presets` | List available presets |
| POST | `/api/story/start` | Start story on a chat |
| GET | `/api/story/{chat}` | Get current state |
| POST | `/api/story/{chat}/set` | Update state variable |
| POST | `/api/story/{chat}/reset` | Reset to preset defaults |
| GET | `/api/story/{chat}/history` | State transition log |
| GET | `/api/story/saves/{preset}` | List saved games |
| POST | `/api/story/{chat}/save` | Save game state |
| POST | `/api/story/{chat}/load` | Load saved game |

### Heartbeat (Scheduled Tasks)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/continuity/tasks` | List scheduled tasks |
| POST | `/api/continuity/tasks` | Create task |
| GET | `/api/continuity/tasks/{id}` | Get task |
| PUT | `/api/continuity/tasks/{id}` | Update task |
| DELETE | `/api/continuity/tasks/{id}` | Delete task |
| POST | `/api/continuity/tasks/{id}/run` | Run task now |
| GET | `/api/continuity/status` | Scheduler status |
| GET | `/api/continuity/activity` | Recent activity log |
| GET | `/api/continuity/timeline` | Upcoming schedule (future only) |
| GET | `/api/continuity/merged-timeline` | Past activity + future schedule with NOW marker |

### Daemon Events

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/events/sources` | List daemon event sources from loaded plugins |
| POST | `/api/events/emit/{source}` | Emit a daemon event to trigger matching tasks |

### Backup

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/backup/list` | List backups |
| POST | `/api/backup/create` | Create backup |
| DELETE | `/api/backup/delete/{name}` | Delete backup |
| GET | `/api/backup/download/{name}` | Download backup zip |

### Agents

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/agents/status` | List agents (?chat=name to filter) |
| GET | `/api/agents/providers` | List available LLM providers for agents |
| POST | `/api/agents/{id}/dismiss` | Dismiss an agent |

### Workspace Runner

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/workspace/run` | Run a command in a workspace project |
| POST | `/api/workspace/stop` | Stop a running workspace process |
| GET | `/api/workspace/status` | Get status of all running workspaces |

### Plugins — Listing & Lifecycle

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/webui/plugins` | List all plugins (loaded, enabled, manifest info) |
| PUT | `/api/webui/plugins/toggle/{name}` | Enable/disable a plugin (live load/unload) |
| POST | `/api/plugins/rescan` | Discover newly added plugins without restart |
| POST | `/api/plugins/{name}/reload` | Hot-reload a plugin (unload + load) |

### Plugins — Install & Uninstall

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/plugins/install` | Install plugin from GitHub URL or zip upload |
| DELETE | `/api/plugins/{name}/uninstall` | Uninstall user plugin (unload + delete) |
| GET | `/api/plugins/{name}/check-update` | Check for updates from install source |

### Plugin Settings

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/webui/plugins/{name}/settings` | Get plugin settings |
| PUT | `/api/webui/plugins/{name}/settings` | Save plugin settings |
| DELETE | `/api/webui/plugins/{name}/settings` | Reset plugin settings |
| GET | `/api/webui/plugins/config` | Get plugin config metadata |

### Apps & Themes

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/apps` | List plugin apps (plugins with an app/ directory) |
| GET | `/api/themes` | List all themes (core + plugin manifest themes) |

### Home Assistant Plugin

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/webui/plugins/homeassistant/defaults` | Get HA default settings |
| POST | `/api/webui/plugins/homeassistant/test-connection` | Test HA connection |
| POST | `/api/webui/plugins/homeassistant/test-notify` | Test HA notification |
| PUT | `/api/webui/plugins/homeassistant/token` | Save HA token |
| GET | `/api/webui/plugins/homeassistant/token` | HA token status |
| POST | `/api/webui/plugins/homeassistant/entities` | Fetch HA entities |

### Image Generation Plugin

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/webui/plugins/image-gen/test-connection` | Test image gen connection |
| GET | `/api/webui/plugins/image-gen/defaults` | Get image gen defaults |

### Email Plugin

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/webui/plugins/email/credentials` | Get email credentials |
| PUT | `/api/webui/plugins/email/credentials` | Save email credentials |
| DELETE | `/api/webui/plugins/email/credentials` | Remove email credentials |
| POST | `/api/webui/plugins/email/test` | Test email connection |
| GET | `/api/email/accounts` | List email accounts (multi-scope) |
| PUT | `/api/email/accounts/{scope}` | Set email account for scope |
| DELETE | `/api/email/accounts/{scope}` | Remove email account for scope |
| POST | `/api/email/accounts/{scope}/test` | Test email account |

### Bitcoin Plugin

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/bitcoin/wallets` | List bitcoin wallets (multi-scope) |
| PUT | `/api/bitcoin/wallets/{scope}` | Set wallet for scope |
| DELETE | `/api/bitcoin/wallets/{scope}` | Remove wallet for scope |
| POST | `/api/bitcoin/wallets/{scope}/check` | Check wallet balance |
| GET | `/api/bitcoin/wallets/{scope}/export` | Export wallet details |

### Google Calendar Plugin

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/gcal/accounts` | List Google Calendar accounts (multi-scope) |
| PUT | `/api/gcal/accounts/{scope}` | Set GCal account for scope |
| DELETE | `/api/gcal/accounts/{scope}` | Remove GCal account for scope |

### SSH Plugin

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/webui/plugins/ssh/servers` | Get configured SSH servers |
| PUT | `/api/webui/plugins/ssh/servers` | Replace SSH servers list |
| POST | `/api/webui/plugins/ssh/test` | Test SSH connection |

### Avatars

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/avatars` | Get avatar paths for user/assistant |
| POST | `/api/avatar/upload` | Upload avatar (max 4MB) |
| GET | `/api/avatar/check/{role}` | Check if avatar exists for role |
| GET | `/api/avatar/{filename}` | Serve avatar file |

### Setup Wizard

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/setup/provider-status` | Check STT/TTS provider readiness |
| GET | `/api/setup/check-packages` | Check optional package installation status |
| GET | `/api/setup/wizard-step` | Get current wizard step |
| PUT | `/api/setup/wizard-step` | Set wizard step |

### Metrics (Token Usage)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/metrics/enabled` | Check if metrics tracking is enabled |
| PUT | `/api/metrics/enabled` | Toggle metrics tracking |
| GET | `/api/metrics/summary` | Aggregate token usage summary (?days=30) |
| GET | `/api/metrics/breakdown` | Usage broken down by model (?days=30) |
| GET | `/api/metrics/daily` | Daily usage for charting (?days=30) |

### System Updates

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/system/update-check` | Check for Sapphire updates |
| POST | `/api/system/update` | Apply update |
| POST | `/api/system/restart` | Restart Sapphire |
| POST | `/api/system/shutdown` | Shutdown Sapphire |

### Media (Tool-Generated Images)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/tool-image/{id}` | Serve tool-generated image |
| GET | `/api/sdxl-image/{id}` | Serve SDXL-generated image |

### Docs

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/docs` | List documentation tree |
| GET | `/api/docs/search` | Search across all docs (?q=query) |
| GET | `/api/docs/{path}` | Get raw markdown content of a doc |

### Static Assets & Plugin Web

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/plugin-web/{name}/{path}` | Serve plugin web/app assets |
| GET | `/workspace/{project}/{path}` | Serve Claude Code workspace files |

---

## Reference for AI

Sapphire API reference for programmatic access. ~280 endpoints across 12 route modules.

AUTH:
- Browser: Session cookie via /login
- Programmatic: X-API-Key header with bcrypt hash from secret_key file
- API key bypasses CSRF
- Rate limit: 5 attempts/60s per IP

ROUTE MODULES (core/routes/):
- chat.py: chat, history, sessions, events, health, status, init
- content.py: prompts, prompt components, toolsets, functions, spices, spice sets, personas (incl export/import)
- settings.py: settings CRUD, credentials, SOCKS proxy, LLM providers, custom providers, privacy, TTS/STT provider registry
- system.py: backup, audio devices, continuity/tasks, setup wizard, avatars, restart/shutdown, update, metrics, daemon events
- plugins.py: plugin listing/toggle/rescan/reload, install/uninstall/check-update, apps, themes, plugin settings, HA/email/bitcoin/gcal/ssh
- knowledge.py: embedding test, memory, goals, knowledge tabs/entries, people, RAG documents, export/import
- tts.py: TTS generate/preview/stop/test, voices, transcribe, mic, image upload
- story_engine.py: story presets/start/state/reset/history/save/load
- agents.py: agent status/providers/dismiss, workspace run/stop/status
- media.py: tool-image, sdxl-image serving
- docs.py: doc tree, search, markdown content

KEY ENDPOINTS:
- GET /api/status — unified UI state (prompt, context, spice, streaming, TTS/STT readiness)
- GET /api/init — mega endpoint (all toolsets, prompts, personas, spices, settings in one call)
- POST /api/chat/stream — SSE streaming chat response
- GET /api/events — SSE event stream for real-time UI updates

CHAT FLOW:
1. POST /api/chat or /api/chat/stream with {"text": "message", "chat_name": "optional"}
2. Response streams as SSE events (content, tool_pending, tool_start, tool_end, reload)
3. POST /api/cancel to abort

PLUGIN MANAGEMENT:
- POST /api/plugins/install — GitHub URL or zip upload
- DELETE /api/plugins/{name}/uninstall — user plugins only
- POST /api/plugins/{name}/reload — hot-reload
- POST /api/plugins/rescan — discover new plugins
- PUT /api/webui/plugins/toggle/{name} — live enable/disable

MULTI-ACCOUNT CREDENTIALS (email/bitcoin/gcal):
- GET /api/{type}/accounts — list all scoped accounts
- PUT /api/{type}/accounts/{scope} — set account for scope
- DELETE /api/{type}/accounts/{scope} — remove

COMMON PATTERNS:
- Scoped endpoints use ?scope=name query param
- File uploads use multipart/form-data
- Toolsets: /api/toolsets (not /api/abilities — legacy name removed)
- Most endpoints return JSON
- 200/201 success, 400 validation, 403 auth/CSRF, 404 not found, 503 system not ready
