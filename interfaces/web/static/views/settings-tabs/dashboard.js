// settings-tabs/dashboard.js - Dashboard with system controls, update checker, and token metrics
import * as ui from '../../ui.js';

let updateStatus = null;

export default {
    id: 'dashboard',
    name: 'Dashboard',
    icon: '\uD83C\uDFE0',
    description: 'System status, updates, and controls',

    render(ctx) {
        return `
            <div class="dashboard-grid">
                <div class="dash-card">
                    <h4>System</h4>
                    <div class="dash-version" id="dash-version">v${window.__appVersion || '?'} <span class="text-muted" id="dash-branch"></span></div>
                    <div class="dash-controls">
                        <button class="btn-primary btn-sm" id="dash-restart">Restart</button>
                        <button class="btn-sm danger" id="dash-shutdown">Shutdown</button>
                    </div>
                </div>
                <div class="dash-card">
                    <h4>Updates</h4>
                    <div class="dash-update-status" id="dash-update-status">
                        <span class="text-muted">Checking...</span>
                    </div>
                    <div class="dash-update-actions" id="dash-update-actions"></div>
                </div>
                <div class="dash-card">
                    <h4>Quick Stats</h4>
                    <div id="dash-quick-stats" class="dash-quick-stats">
                        <span class="text-muted" style="font-size:var(--font-sm)">Loading...</span>
                    </div>
                </div>
                <div class="dash-card">
                    <h4>Backups</h4>
                    <div id="dash-backup-status" class="text-muted" style="font-size:var(--font-sm);margin:0 0 8px">Checking...</div>
                    <button class="btn-primary btn-sm" id="dash-backup-now">Backup Now</button>
                </div>
                <div class="dash-card">
                    <h4>Help</h4>
                    <p class="text-muted" style="font-size:var(--font-sm);margin:0 0 8px">Guides and troubleshooting</p>
                    <button class="btn-primary btn-sm" id="dash-help">Open Help</button>
                </div>
                <div class="dash-card">
                    <h4>Maintenance</h4>
                    <div class="dash-controls" style="flex-direction:column;gap:6px">
                        <button class="btn-sm" id="dash-force-update" style="width:100%">Force Update (git pull)</button>
                        <button class="btn-sm" id="dash-clear-cache" style="width:100%">Clear JS Cache</button>
                    </div>
                </div>
                <div class="dash-card dash-card-wide">
                    <div class="dash-card-header">
                        <h4>Token Metrics <span class="text-muted" style="font-size:var(--font-xs);font-weight:normal">(30 days)</span></h4>
                        <label class="metrics-toggle" id="metrics-toggle">
                            <input type="checkbox" id="metrics-enabled-cb">
                            <span class="toggle-track"></span>
                            <span class="toggle-label">Track</span>
                        </label>
                    </div>
                    <div id="dash-metrics" class="dash-metrics">
                        <span class="text-muted">Loading...</span>
                    </div>
                </div>
            </div>
        `;
    },

    attachListeners(ctx, el) {
        // Help button
        el.querySelector('#dash-help')?.addEventListener('click', () => {
            import('../../core/router.js').then(r => r.switchView('help'));
        });

        // Quick stats
        loadQuickStats(el);

        // Force update
        el.querySelector('#dash-force-update')?.addEventListener('click', async () => {
            const btn = el.querySelector('#dash-force-update');
            if (!confirm('Pull latest code from git? Sapphire will restart after.')) return;
            btn.disabled = true;
            btn.textContent = 'Updating...';
            try {
                const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
                const res = await fetch('/api/system/update', { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                if (data.status === 'updated') {
                    ui.showToast('Updated! Restarting...', 'success');
                    setTimeout(() => pollForRestart(), 2000);
                } else {
                    ui.showToast(data.message || 'Already up to date', 'success');
                    btn.disabled = false;
                    btn.textContent = 'Force Update (git pull)';
                }
            } catch (e) {
                ui.showToast(`Update failed: ${e.message}`, 'error');
                btn.disabled = false;
                btn.textContent = 'Force Update (git pull)';
            }
        });

        // Clear JS cache
        el.querySelector('#dash-clear-cache')?.addEventListener('click', () => {
            if ('caches' in window) {
                caches.keys().then(names => names.forEach(n => caches.delete(n)));
            }
            ui.showToast('Cache cleared — reloading...', 'success');
            setTimeout(() => window.location.reload(true), 500);
        });

        // Backup
        loadBackupStatus(el);
        el.querySelector('#dash-backup-now')?.addEventListener('click', async () => {
            const btn = el.querySelector('#dash-backup-now');
            btn.disabled = true;
            btn.textContent = 'Backing up...';
            try {
                const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
                const res = await fetch('/api/backup/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
                    body: JSON.stringify({ type: 'manual' })
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                ui.showToast(`Backup created: ${data.filename || 'done'}`, 'success');
                loadBackupStatus(el);
            } catch (e) { ui.showToast(`Backup failed: ${e.message}`, 'error'); }
            finally { btn.disabled = false; btn.textContent = 'Backup Now'; }
        });

        // Restart
        el.querySelector('#dash-restart')?.addEventListener('click', async () => {
            if (!confirm('Restart Sapphire?')) return;
            try {
                const csrf1 = document.querySelector('meta[name="csrf-token"]')?.content || '';
                await fetch('/api/system/restart', { method: 'POST', headers: { 'X-CSRF-Token': csrf1 } });
                ui.showToast('Restarting...', 'success');
                setTimeout(() => pollForRestart(), 2000);
            } catch { ui.showToast('Restart failed', 'error'); }
        });

        // Shutdown
        el.querySelector('#dash-shutdown')?.addEventListener('click', async () => {
            if (!confirm('Shut down Sapphire? You will need to restart it manually.')) return;
            try {
                const csrf2 = document.querySelector('meta[name="csrf-token"]')?.content || '';
                await fetch('/api/system/shutdown', { method: 'POST', headers: { 'X-CSRF-Token': csrf2 } });
                ui.showToast('Shutting down...', 'success');
            } catch { ui.showToast('Shutdown failed', 'error'); }
        });

        checkForUpdate(el);
        loadMetrics(el);
    }
};


// =============================================================================
// UPDATE CHECKER
// =============================================================================

async function checkForUpdate(el) {
    const statusEl = el.querySelector('#dash-update-status');
    const actionsEl = el.querySelector('#dash-update-actions');
    if (!statusEl || !actionsEl) return;

    try {
        const res = await fetch('/api/system/update-check');
        if (!res.ok) throw new Error('Check failed');
        updateStatus = await res.json();

        // Show branch name in System card
        const branchEl = el.querySelector('#dash-branch');
        if (branchEl && updateStatus.branch) {
            const tag = updateStatus.is_fork ? `${updateStatus.branch} · fork` : updateStatus.branch;
            branchEl.textContent = `· ${tag}`;
        }

        if (updateStatus.available) {
            statusEl.innerHTML = `
                <span class="dash-update-badge">v${updateStatus.latest} available</span>
                <span class="text-muted" style="font-size:var(--font-xs)">Current: v${updateStatus.current}</span>
            `;

            if (updateStatus.is_fork) {
                // Fork: show upstream version, link to releases, no update button
                actionsEl.innerHTML = `<p class="text-muted" style="font-size:var(--font-xs);margin:0">Upstream update — get it from <a href="https://github.com/ddxfish/sapphire/releases" target="_blank">Sapphire releases</a></p>`;
            } else if (updateStatus.docker || updateStatus.managed) {
                actionsEl.innerHTML = `<p class="text-muted" style="font-size:var(--font-xs);margin:0">Update via: <code>docker compose pull && docker compose up -d</code></p>`;
            } else if (updateStatus.has_git) {
                actionsEl.innerHTML = `<button class="btn-primary btn-sm" id="dash-do-update">Update Now</button>`;
                actionsEl.querySelector('#dash-do-update')?.addEventListener('click', () => doUpdate(el));
            } else {
                actionsEl.innerHTML = `<p class="text-muted" style="font-size:var(--font-xs);margin:0">Download the latest release from <a href="https://github.com/ddxfish/sapphire/releases" target="_blank">GitHub</a></p>`;
            }

            window.dispatchEvent(new CustomEvent('update-available', { detail: updateStatus }));
        } else {
            statusEl.innerHTML = `<span class="text-muted">\u2713 Up to date (v${updateStatus.current})</span>`;
            actionsEl.innerHTML = `<button class="btn-sm" id="dash-recheck" style="margin-top:6px">Check Again</button>`;
            actionsEl.querySelector('#dash-recheck')?.addEventListener('click', () => {
                statusEl.innerHTML = '<span class="text-muted">Checking...</span>';
                actionsEl.innerHTML = '';
                checkForUpdate(el);
            });
        }
    } catch (e) {
        statusEl.innerHTML = `<span class="text-muted">Could not check for updates</span>`;
    }
}

async function doUpdate(el) {
    const actionsEl = el.querySelector('#dash-update-actions');
    if (!actionsEl) return;

    const btn = actionsEl.querySelector('#dash-do-update');
    if (btn) { btn.disabled = true; btn.textContent = 'Updating...'; }

    try {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
        const res = await fetch('/api/system/update', { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Update failed');
        }
        ui.showToast('Updated! Restarting...', 'success');

        const statusEl = el.querySelector('#dash-update-status');
        if (statusEl) statusEl.innerHTML = '<span class="text-muted">Restarting with new version...</span>';
        actionsEl.innerHTML = '';

        setTimeout(() => pollForRestart(), 2000);
    } catch (e) {
        ui.showToast(e.message, 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Update Now'; }
    }
}

function pollForRestart() {
    let attempts = 0;
    const poll = async () => {
        attempts++;
        try {
            const res = await fetch('/api/health');
            if (res.ok) { window.location.reload(); return; }
        } catch {}
        if (attempts < 30) setTimeout(poll, 1000);
    };
    poll();
}


// =============================================================================
// QUICK STATS
// =============================================================================

async function loadQuickStats(el) {
    const box = el.querySelector('#dash-quick-stats');
    if (!box) return;
    try {
        const res = await fetch('/api/status');
        if (!res.ok) { box.innerHTML = '<span class="text-muted" style="font-size:var(--font-sm)">Unavailable</span>'; return; }
        const data = await res.json();
        const chat = data.active_chat || '?';
        const msgs = data.history_length || 0;
        const ctx = data.context || {};
        const tts = data.tts_state || {};
        const stt = data.stt_state || {};

        box.innerHTML = `
            <div style="display:flex;flex-direction:column;gap:4px;font-size:var(--font-sm)">
                <div><span class="text-muted">Chat:</span> ${_esc(chat)} (${msgs} msgs)</div>
                <div><span class="text-muted">Context:</span> ${ctx.percent || 0}% used${ctx.limit ? ` (${(ctx.used||0).toLocaleString()}/${ctx.limit.toLocaleString()})` : ''}</div>
                <div><span class="text-muted">TTS:</span> ${tts.speaking ? '<span style="color:#4caf50">Speaking</span>' : 'Idle'}</div>
                <div><span class="text-muted">STT:</span> ${stt.recording ? '<span style="color:#4fc3f7">Recording</span>' : 'Idle'}</div>
            </div>
        `;
    } catch { box.innerHTML = '<span class="text-muted" style="font-size:var(--font-sm)">Stats unavailable</span>'; }
}

function _esc(s) { return String(s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// =============================================================================
// BACKUP STATUS
// =============================================================================

async function loadBackupStatus(el) {
    const statusEl = el.querySelector('#dash-backup-status');
    if (!statusEl) return;
    try {
        const res = await fetch('/api/backup/list');
        if (!res.ok) { statusEl.textContent = 'Could not check backups'; return; }
        const data = await res.json();
        const backups = data.backups || {};
        const all = [...(backups.daily || []), ...(backups.weekly || []), ...(backups.monthly || []), ...(backups.manual || [])];
        if (all.length === 0) {
            statusEl.textContent = 'No backups yet';
        } else {
            // Sort by date+time string (format: YYYY-MM-DD + HHMMSS)
            all.sort((a, b) => (`${b.date}_${b.time}`).localeCompare(`${a.date}_${a.time}`));
            const latest = all[0];
            const ago = _backupTimeAgo(latest.date, latest.time);
            const sizeMB = latest.size ? ` \u00b7 ${(latest.size / 1048576).toFixed(0)} MB` : '';
            statusEl.textContent = `${all.length} backups \u00b7 Latest: ${ago}${sizeMB}`;
        }
    } catch { statusEl.textContent = 'Backup status unavailable'; }
}

function _backupTimeAgo(dateStr, timeStr) {
    if (!dateStr) return 'unknown';
    // Parse "2026-03-27" + "030000" → ms since epoch
    const h = timeStr?.slice(0, 2) || '00', m = timeStr?.slice(2, 4) || '00', s = timeStr?.slice(4, 6) || '00';
    const parts = dateStr.split('-');
    const d = new Date(+parts[0], +parts[1] - 1, +parts[2], +h, +m, +s);
    if (isNaN(d.getTime())) return dateStr;
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 0) return 'just now';
    if (sec < 60) return 'just now';
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
}

// =============================================================================
// TOKEN METRICS
// =============================================================================

const fmt = n => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
};

async function loadMetrics(el) {
    const metricsEl = el.querySelector('#dash-metrics');
    const cb = el.querySelector('#metrics-enabled-cb');
    if (!metricsEl) return;

    // Load toggle state
    try {
        const toggleRes = await fetch('/api/metrics/enabled');
        if (toggleRes.ok) {
            const { enabled } = await toggleRes.json();
            if (cb) cb.checked = enabled;
        }
    } catch {}

    // Wire toggle
    if (cb) {
        cb.addEventListener('change', async () => {
            try {
                await fetch('/api/metrics/enabled', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: cb.checked })
                });
                loadMetricsData(metricsEl, cb.checked);
            } catch { cb.checked = !cb.checked; }
        });
    }

    loadMetricsData(metricsEl, cb?.checked !== false);
}

async function loadMetricsData(el, enabled) {
    if (!enabled) {
        el.innerHTML = '<span class="text-muted">Metrics tracking is off. Per-message stats still show in chat.</span>';
        return;
    }

    try {
        const [sumRes, brkRes, dailyRes] = await Promise.all([
            fetch('/api/metrics/summary?days=30'),
            fetch('/api/metrics/breakdown?days=30'),
            fetch('/api/metrics/daily?days=30')
        ]);

        if (!sumRes.ok || !brkRes.ok || !dailyRes.ok) throw new Error('Metrics fetch failed');

        const summary = await sumRes.json();
        const breakdown = await brkRes.json();
        const daily = await dailyRes.json();

        renderMetrics(el, summary, breakdown.models || [], daily.daily || []);
    } catch (e) {
        el.innerHTML = '<span class="text-muted">No metrics data yet — send some messages to start collecting</span>';
    }
}

function renderMetrics(el, s, models, daily) {
    if (!s.total_calls) {
        el.innerHTML = '<span class="text-muted">No data yet — metrics start recording from this version</span>';
        return;
    }

    const cacheRate = s.total_prompt > 0 && s.total_cache_read > 0
        ? Math.round((s.total_cache_read / s.total_prompt) * 100) : null;

    el.innerHTML = `
        <div class="metrics-stats">
            <div class="metric-item">
                <div class="metric-value">${fmt(s.total_calls)}</div>
                <div class="metric-label">LLM Calls</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${fmt(s.total_tokens)}</div>
                <div class="metric-label">Total Tokens</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${fmt(s.total_prompt)}</div>
                <div class="metric-label">Input</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${fmt(s.total_completion)}</div>
                <div class="metric-label">Output</div>
            </div>
            ${s.total_thinking > 0 ? `
            <div class="metric-item">
                <div class="metric-value">${fmt(s.total_thinking)}</div>
                <div class="metric-label">Thinking</div>
            </div>` : ''}
            ${cacheRate !== null ? `
            <div class="metric-item">
                <div class="metric-value">${cacheRate}%</div>
                <div class="metric-label">Cache Hit</div>
            </div>` : ''}
        </div>
        <div class="metrics-charts">
            <div class="metrics-chart-container">
                <div class="chart-title">Daily Usage</div>
                <div id="chart-daily" class="chart-area"></div>
            </div>
            <div class="metrics-chart-container">
                <div class="chart-title">Models</div>
                <div id="chart-models" class="chart-area"></div>
            </div>
        </div>
    `;

    renderDailyChart(el.querySelector('#chart-daily'), daily);
    renderModelChart(el.querySelector('#chart-models'), models);
}


// =============================================================================
// SVG CHARTS
// =============================================================================

function renderDailyChart(el, daily) {
    if (!el || daily.length < 2) {
        if (el) el.innerHTML = '<span class="text-muted" style="font-size:var(--font-xs)">Need 2+ days of data</span>';
        return;
    }

    const W = 540, H = 120, PAD_L = 40, PAD_R = 8, PAD_T = 8, PAD_B = 20;
    const chartW = W - PAD_L - PAD_R;
    const chartH = H - PAD_T - PAD_B;

    const maxTokens = Math.max(...daily.map(d => d.tokens)) || 1;
    const points = daily.map((d, i) => {
        const x = PAD_L + (i / (daily.length - 1)) * chartW;
        const y = PAD_T + chartH - (d.tokens / maxTokens) * chartH;
        return { x, y, ...d };
    });

    const polyline = points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');

    // Fill area under line
    const areaPoints = `${PAD_L},${PAD_T + chartH} ${polyline} ${points[points.length - 1].x.toFixed(1)},${PAD_T + chartH}`;

    // Y-axis labels (0, mid, max)
    const yMid = fmt(Math.round(maxTokens / 2));
    const yMax = fmt(maxTokens);

    // X-axis labels (first and last date)
    const firstDate = daily[0].date.slice(5); // MM-DD
    const lastDate = daily[daily.length - 1].date.slice(5);

    // Tooltip dots
    const dots = points.map(p =>
        `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" class="chart-dot">
            <title>${p.date}: ${fmt(p.tokens)} tokens, ${p.calls} calls</title>
        </circle>`
    ).join('');

    el.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" class="chart-svg">
            <!-- Grid lines -->
            <line x1="${PAD_L}" y1="${PAD_T}" x2="${PAD_L + chartW}" y2="${PAD_T}" class="chart-grid"/>
            <line x1="${PAD_L}" y1="${PAD_T + chartH / 2}" x2="${PAD_L + chartW}" y2="${PAD_T + chartH / 2}" class="chart-grid"/>
            <line x1="${PAD_L}" y1="${PAD_T + chartH}" x2="${PAD_L + chartW}" y2="${PAD_T + chartH}" class="chart-grid"/>

            <!-- Y labels -->
            <text x="${PAD_L - 4}" y="${PAD_T + 4}" class="chart-label" text-anchor="end">${yMax}</text>
            <text x="${PAD_L - 4}" y="${PAD_T + chartH / 2 + 3}" class="chart-label" text-anchor="end">${yMid}</text>
            <text x="${PAD_L - 4}" y="${PAD_T + chartH + 3}" class="chart-label" text-anchor="end">0</text>

            <!-- X labels -->
            <text x="${PAD_L}" y="${H - 2}" class="chart-label">${firstDate}</text>
            <text x="${PAD_L + chartW}" y="${H - 2}" class="chart-label" text-anchor="end">${lastDate}</text>

            <!-- Area fill -->
            <polygon points="${areaPoints}" class="chart-area-fill"/>

            <!-- Line -->
            <polyline points="${polyline}" class="chart-line"/>

            <!-- Dots -->
            ${dots}
        </svg>
    `;
}

function renderModelChart(el, models) {
    if (!el || !models.length) {
        if (el) el.innerHTML = '<span class="text-muted" style="font-size:var(--font-xs)">No model data yet</span>';
        return;
    }

    const top = models.slice(0, 5);
    const maxTotal = Math.max(...top.map(m => m.total)) || 1;

    const BAR_H = 18, GAP = 6, LABEL_W = 100, BAR_AREA = 370, PAD_R = 70;
    const W = LABEL_W + BAR_AREA + PAD_R;
    const H = top.length * (BAR_H + GAP) + GAP;

    const bars = top.map((m, i) => {
        const y = GAP + i * (BAR_H + GAP);
        const barW = Math.max(2, (m.total / maxTotal) * BAR_AREA);
        const label = m.model.length > 14 ? m.model.slice(0, 13) + '\u2026' : m.model;
        const cacheInfo = m.cache_read > 0 && m.prompt > 0
            ? ` \u00B7 cache ${Math.round((m.cache_read / m.prompt) * 100)}%` : '';

        return `
            <text x="${LABEL_W - 4}" y="${y + BAR_H / 2 + 4}" class="chart-label" text-anchor="end">${label}</text>
            <rect x="${LABEL_W}" y="${y}" width="${barW.toFixed(1)}" height="${BAR_H}" class="chart-bar" rx="2">
                <title>${m.model}: ${fmt(m.total)} tokens, ${m.calls} calls${cacheInfo}</title>
            </rect>
            <text x="${LABEL_W + barW + 4}" y="${y + BAR_H / 2 + 4}" class="chart-label">${fmt(m.total)}${cacheInfo}</text>
        `;
    }).join('');

    el.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" class="chart-svg">
            ${bars}
        </svg>
    `;
}
