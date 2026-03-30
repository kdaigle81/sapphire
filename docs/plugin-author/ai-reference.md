# AI Reference

Compact reference for Sapphire's own use when building plugins. For simple tool creation (tool_save/tool_load), see the TOOLMAKER doc — this covers full plugin development.

When creating or modifying plugins:

- Plugin = folder in `plugins/{name}/` with `plugin.json` manifest
- `plugin.json` requires `name` field, everything else optional
- Hooks = Python functions receiving mutable `HookEvent` object
- Tools = `TOOLS` list + `execute(function_name, arguments, config)` returning `(str, bool)`
- Tool schema supports `is_local` (bool or `"endpoint"`) and `network: true` flags
- Voice commands = pre_chat hooks with trigger matching, `bypass_llm: true` for instant response
- Routes = custom HTTP endpoints at `/api/plugin/{name}/{path}`, handler receives `(path_params, body, settings)`, auth+CSRF+rate-limit enforced by framework
- Schedule = cron tasks calling `run(event)` handler, event has `system`, `config`, `task`, `plugin_state`
- Web settings = `web/index.js` using `registerPluginSettings()`, served at `/plugin-web/{name}/`
- Plugin scripts = `web/main.js` auto-loaded on app startup, listen for `sapphire:tool_start` DOM events
- Daemon = background thread with `start(plugin_loader, settings)` / `stop()`, emits events via `plugin_loader.emit_daemon_event(source_name, json_payload)`
- Daemon event sources declared in manifest `capabilities.daemon.event_sources[]` — `name`, `label`, `filter_fields`, `task_fields`
- Reply handlers: `plugin_loader.register_reply_handler(plugin_name, handler)` — routes LLM responses back to source platform
- Providers = register TTS/STT/Embedding/LLM backends via `capabilities.providers` — appear in settings dropdowns
- App = full-page plugin UI via `capabilities.app` — `label`, `icon`, optional `nav: true` for navrail promotion (max 3)
- Themes = custom CSS themes via `capabilities.themes[]` — `css`, `scripts`, `preview`, per-theme `settings`
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
- Settings files are in `user/` (gitignored) — never tracked
- Multi-account tools use ContextVar scopes: `scope_email`, `scope_bitcoin`, `scope_knowledge`, etc.
- Web UI modules available: `plugin-registry.js`, `plugins-api.js`, `toast.js`, `modal.js`, `danger-confirm.js`, `fetch.js`
- CSS variables for theming: `--bg`, `--text`, `--border`, `--trim`, `--success`, `--error`, etc.
- Always guard system access with `hasattr()` checks — subsystems may be None if disabled
