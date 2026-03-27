// Status app — live system dashboard

let _interval = null;
let _container = null;

export async function render(container) {
    _container = container;
    container.innerHTML = '<div class="status-loading">Loading status...</div>';
    await refresh();
    _interval = setInterval(refresh, 10000);
}

export function cleanup() {
    if (_interval) clearInterval(_interval);
    _interval = null;
    _container = null;
}

async function refresh() {
    if (!_container) return;
    try {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
        const res = await fetch('/api/plugin/status/full', { headers: { 'X-CSRF-Token': csrf } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderDashboard(_container, data);
    } catch (e) {
        console.error('[Status] Refresh failed:', e);
    }
}

function renderDashboard(el, d) {
    const ident = d.identity || {};
    const sess = d.session || {};
    const svc = d.services || {};
    const tasks = d.tasks || {};
    const daemons = d.daemons || {};
    const providers = d.providers || [];
    const plugins = d.plugins || [];
    const metrics = d.metrics || {};

    const upMin = Math.floor((ident.uptime_seconds || 0) / 60);
    const upH = Math.floor(upMin / 60);
    const upM = upMin % 60;
    const env = ident.docker ? 'Docker' : (ident.os || 'Unknown');
    const branch = ident.branch ? ` (${esc(ident.branch)})` : '';

    el.innerHTML = `
        <div class="status-dashboard">
            <!-- Row 1: Identity + Session -->
            <div class="status-row">
                <div class="status-card status-identity">
                    <div class="status-card-title">Sapphire v${esc(ident.app_version || '?')}${branch}</div>
                    <div class="status-meta">
                        Python ${esc(ident.python_version || '?')} &middot; ${esc(env)} &middot; Uptime: ${upH}h ${upM}m
                        ${ident.hostname ? ` &middot; ${esc(ident.hostname)}` : ''}
                    </div>
                </div>
                <div class="status-card">
                    <div class="status-card-title">Active Session</div>
                    <div class="status-grid">
                        ${field('Chat', sess.chat)}
                        ${field('Prompt', sess.prompt)}
                        ${field('Persona', sess.persona || 'none')}
                        ${field('LLM', `${sess.llm_primary || 'auto'}${sess.llm_model ? ' (' + sess.llm_model + ')' : ''}`)}
                        ${field('Toolset', `${sess.toolset || '?'} (${sess.function_count || 0} tools)`)}
                        ${field('Memory', sess.memory_scope || 'default')}
                        ${field('Knowledge', sess.knowledge_scope || 'default')}
                    </div>
                </div>
            </div>

            <!-- Row 2: Services + Task Engine -->
            <div class="status-row">
                <div class="status-card">
                    <div class="status-card-title">Services</div>
                    <div class="status-service-list">
                        <div class="status-svc-row">${dot(svc.tts?.enabled)} TTS: ${esc(svc.tts?.provider || 'off')}${svc.tts?.voice ? ' (' + esc(svc.tts.voice) + ')' : ''}</div>
                        <div class="status-svc-row">${dot(svc.stt?.enabled)} STT: ${esc(svc.stt?.provider || 'off')}</div>
                        <div class="status-svc-row">${dot(svc.wakeword?.enabled)} Wakeword${svc.wakeword?.model ? ': ' + esc(svc.wakeword.model) : ''}</div>
                        <div class="status-svc-row">${dot(svc.embeddings?.enabled)} Embeddings: ${esc(svc.embeddings?.provider || 'off')}</div>
                        <div class="status-svc-row">${dot(svc.socks?.enabled)} SOCKS Proxy${svc.socks?.enabled ? (svc.socks.has_credentials ? ' (creds set)' : ' (no creds)') : ''}</div>
                        ${Object.entries(daemons).map(([k,v]) =>
                            `<div class="status-svc-row">${dot(v === 'running')} ${esc(k)}: ${esc(v)}</div>`
                        ).join('')}
                    </div>
                </div>
                <div class="status-card">
                    <div class="status-card-title">Task Engine</div>
                    <div class="status-grid">
                        ${field('Total', tasks.total)}
                        ${field('Enabled', tasks.enabled)}
                        ${field('Running', tasks.running)}
                    </div>
                    <div class="status-task-types">
                        ${tasks.tasks ? `<span class="status-type-chip">Tasks: ${tasks.tasks}</span>` : ''}
                        ${tasks.heartbeats ? `<span class="status-type-chip">Heartbeats: ${tasks.heartbeats}</span>` : ''}
                        ${tasks.daemons ? `<span class="status-type-chip">Daemons: ${tasks.daemons}</span>` : ''}
                        ${tasks.webhooks ? `<span class="status-type-chip">Webhooks: ${tasks.webhooks}</span>` : ''}
                    </div>
                </div>
            </div>

            <!-- Row 3: Providers + Metrics -->
            <div class="status-row">
                <div class="status-card">
                    <div class="status-card-title">LLM Providers</div>
                    ${providers.length ? `
                    <table class="status-table">
                        <thead><tr><th>Provider</th><th>Status</th><th>Key</th><th>Type</th></tr></thead>
                        <tbody>
                            ${providers.map(p => `
                                <tr>
                                    <td>${esc(p.name || p.key)}</td>
                                    <td>${dot(p.enabled)} ${p.enabled ? 'on' : 'off'}</td>
                                    <td>${p.has_key ? '<span style="color:var(--color-success,#4caf50)">set</span>' : '<span style="color:var(--text-muted)">-</span>'}</td>
                                    <td>${p.is_local ? 'local' : 'cloud'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>` : '<div class="status-meta">No providers configured</div>'}
                </div>
                ${metrics.total_tokens ? `
                <div class="status-card">
                    <div class="status-card-title">Token Usage (7 days)</div>
                    <div class="status-grid">
                        ${field('Total tokens', (metrics.total_tokens || 0).toLocaleString())}
                        ${field('API calls', metrics.total_calls || 0)}
                        ${metrics.by_provider ? Object.entries(metrics.by_provider).map(([k,v]) =>
                            field(k, (v.tokens || 0).toLocaleString() + ' tok, ' + (v.calls || 0) + ' calls')
                        ).join('') : ''}
                    </div>
                </div>` : ''}
            </div>

            <!-- Row 4: Plugins + Diagnostics -->
            <div class="status-row">
                <div class="status-card">
                    <div class="status-card-title">Plugins (${plugins.filter(p => p.loaded).length} loaded)</div>
                    <div class="status-plugin-grid">
                        ${plugins.map(p => `
                            <span class="status-plugin-chip ${p.loaded ? 'loaded' : p.enabled ? 'enabled' : 'disabled'}">
                                ${esc(p.name)}${p.version ? ' v' + esc(p.version) : ''}
                            </span>
                        `).join('')}
                    </div>
                </div>
                <div class="status-card">
                    <button class="status-copy-btn" id="status-copy-diag">Copy Diagnostics</button>
                    <div class="status-meta" style="margin-top:8px">One-click copy for Discord support</div>
                </div>
            </div>
        </div>

        <style>
            .status-dashboard { display: flex; flex-direction: column; gap: 16px; }
            .status-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
            .status-card {
                background: var(--bg-secondary, #1a1a2e); border: 1px solid var(--border, #333);
                border-radius: 10px; padding: 16px;
            }
            .status-identity { border-color: var(--accent, #4a9eff); }
            .status-card-title { font-weight: 600; margin-bottom: 10px; color: var(--text); }
            .status-meta { color: var(--text-muted); font-size: var(--font-sm); }
            .status-grid { display: flex; flex-direction: column; gap: 4px; font-size: var(--font-sm); }
            .status-field { display: flex; gap: 8px; }
            .status-field-label { color: var(--text-muted); min-width: 90px; }
            .status-field-value { color: var(--text); }
            .status-service-list { display: flex; flex-direction: column; gap: 6px; font-size: var(--font-sm); }
            .status-svc-row { display: flex; align-items: center; color: var(--text); white-space: nowrap; }
            .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; flex-shrink: 0; }
            .status-dot.on { background: #4caf50; }
            .status-dot.off { background: #666; }
            .status-task-types { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
            .status-type-chip { font-size: var(--font-xs); padding: 2px 8px; border-radius: 10px; background: var(--bg, #111); color: var(--text-muted); }
            .status-table { width: 100%; border-collapse: collapse; font-size: var(--font-sm); }
            .status-table th { text-align: left; color: var(--text-muted); padding: 4px 8px; border-bottom: 1px solid var(--border); }
            .status-table td { padding: 4px 8px; color: var(--text); }
            .status-plugin-grid { display: flex; flex-wrap: wrap; gap: 6px; }
            .status-plugin-chip {
                font-size: var(--font-xs); padding: 3px 8px; border-radius: 12px;
                border: 1px solid var(--border);
            }
            .status-plugin-chip.loaded { color: var(--text); border-color: var(--color-success, #4caf50); }
            .status-plugin-chip.enabled { color: var(--text-muted); }
            .status-plugin-chip.disabled { color: var(--text-muted); opacity: 0.5; }
            .status-copy-btn {
                background: var(--bg); border: 1px solid var(--border); color: var(--text);
                padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: var(--font-sm); width: 100%;
            }
            .status-copy-btn:hover { border-color: var(--accent); }
            .status-loading { color: var(--text-muted); text-align: center; padding: 40px; }
        </style>
    `;

    // Copy diagnostics
    el.querySelector('#status-copy-diag')?.addEventListener('click', () => {
        const lines = [
            `Sapphire v${ident.app_version}${branch} | Python ${ident.python_version} | ${env}`,
            `Uptime: ${upH}h ${upM}m | Host: ${ident.hostname || 'unknown'}`,
            `Chat: ${sess.chat} | Prompt: ${sess.prompt} | Persona: ${sess.persona || 'none'}`,
            `LLM: ${sess.llm_primary} (${sess.llm_model || 'default'})`,
            `Toolset: ${sess.toolset} (${sess.function_count} tools)`,
            `TTS: ${svc.tts?.provider || 'off'} | STT: ${svc.stt?.provider || 'off'} | Wakeword: ${svc.wakeword?.enabled ? 'ON' : 'OFF'}`,
            `Embeddings: ${svc.embeddings?.provider || 'off'} | SOCKS: ${svc.socks?.enabled ? 'ON' : 'OFF'}`,
            `Tasks: ${tasks.tasks || 0} tasks, ${tasks.heartbeats || 0} heartbeats, ${tasks.daemons || 0} daemons, ${tasks.webhooks || 0} webhooks (${tasks.running || 0} running)`,
            `Plugins: ${plugins.filter(p => p.loaded).length} loaded / ${plugins.length} total`,
            `Providers: ${providers.filter(p => p.enabled).map(p => p.name || p.key).join(', ') || 'none enabled'}`,
        ];
        if (metrics.total_tokens) lines.push(`Tokens (7d): ${metrics.total_tokens.toLocaleString()}`);
        navigator.clipboard.writeText(lines.join('\n'));
        const btn = el.querySelector('#status-copy-diag');
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy Diagnostics', 2000);
    });
}

function esc(s) { return String(s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function dot(on) { return `<span class="status-dot ${on ? 'on' : 'off'}"></span>`; }
function field(label, value) {
    return `<div class="status-field"><span class="status-field-label">${esc(label)}</span><span class="status-field-value">${esc(value)}</span></div>`;
}
