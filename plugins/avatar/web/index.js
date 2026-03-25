// Avatar plugin settings — model management, track mapping, idle pool
import { registerPluginSettings } from '/static/shared/plugin-registry.js';

console.log('[Avatar Settings] Module loaded');
const API = '/api/plugin/avatar';

function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

async function fetchJSON(url, opts = {}) {
    opts.headers = { 'X-CSRF-Token': csrf(), ...(opts.headers || {}) };
    const r = await fetch(url, opts);
    return r.ok ? r.json() : null;
}

// Avatar states that need track mapping
const AVATAR_STATES = [
    { key: 'idle',        label: 'Idle' },
    { key: 'thinking',    label: 'Thinking' },
    { key: 'typing',      label: 'Composing' },
    { key: 'listening',   label: 'Listening' },
    { key: 'speaking',    label: 'Speaking' },
    { key: 'toolcall',    label: 'Tool Use' },
    { key: 'happy',       label: 'Happy' },
    { key: 'wakeword',    label: 'Alert' },
    { key: 'user_typing', label: 'User Typing' },
    { key: 'reading',     label: 'Reading' },
];

let _renderContainer = null;

registerPluginSettings({
    id: 'avatar',
    name: 'Avatar',
    icon: '\uD83D\uDC8E',
    helpText: '3D avatar model management and animation mapping',

    load: () => fetchJSON(`${API}/config`),

    getSettings: () => {
        if (!_renderContainer) return {};
        return collectConfig(_renderContainer);
    },

    save: async (settings) => {
        const resp = await fetch(`${API}/config`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf(),
            },
            body: JSON.stringify(settings),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    },

    render: (container) => {
        _renderContainer = container;
        console.log('[Avatar Settings] render() called, container:', container?.id || container?.className);
        injectStyles();

        container.innerHTML = `
            <div class="avatar-settings">
                <div class="avatar-section">
                    <h3>Models</h3>
                    <div id="avatar-model-list" class="avatar-model-list"></div>
                    <label class="avatar-upload-btn">
                        Upload Model (.glb)
                        <input type="file" id="avatar-upload" accept=".glb" hidden>
                    </label>
                </div>

                <div class="avatar-section" id="avatar-mapping-section" style="display:none">
                    <h3>Track Mapping</h3>
                    <p class="avatar-help">Map avatar states to animation tracks from your model.</p>
                    <div id="avatar-track-grid" class="avatar-track-grid"></div>
                </div>

                <div class="avatar-section" id="avatar-idle-section" style="display:none">
                    <h3>Idle Variety Pool</h3>
                    <p class="avatar-help">Tracks to cycle through when idle. Higher weight = more frequent.</p>
                    <div id="avatar-idle-pool"></div>
                </div>

                <div class="avatar-section" id="avatar-greeting-section" style="display:none">
                    <h3>Greeting &amp; Display</h3>
                    <div class="avatar-field">
                        <label>Play on load</label>
                        <select id="avatar-greeting-track"></select>
                    </div>
                    <div class="avatar-field" style="margin-top:6px">
                        <label>Scale</label>
                        <input type="number" id="avatar-scale" min="0.01" max="100" step="0.1" value="1.0" class="avatar-weight" style="width:70px">
                        <span class="avatar-help" style="margin:0">(1.0 = auto-fit, adjust if too big/small)</span>
                    </div>
                </div>

            </div>
        `;

        // Wire upload (use event delegation so it survives DOM rebuilds)
        container.addEventListener('change', async (e) => {
            const input = e.target.closest('#avatar-upload');
            if (!input) return;
            const file = input.files[0];
            if (!file) return;
            const form = new FormData();
            form.append('file', file);
            const label = container.querySelector('.avatar-upload-btn');
            if (label) label.textContent = 'Uploading...';
            try {
                const result = await fetch(`${API}/upload`, {
                    method: 'POST',
                    headers: { 'X-CSRF-Token': csrf() },
                    body: form,
                });
                const data = await result.json();
                if (data.error) {
                    alert(data.error);
                } else {
                    await loadModels(container);
                }
            } catch (err) {
                alert('Upload failed');
            }
            if (label) {
                label.innerHTML = 'Upload Model (.glb)<input type="file" id="avatar-upload" accept=".glb" hidden>';
            }
        });

        // Initial load
        loadModels(container).catch(e => console.error('[Avatar Settings] loadModels failed:', e));
    }
});

let _currentModels = [];
let _activeModel = '';
let _activeTracks = [];
let _activeConfig = {};

async function loadModels(container) {
    const data = await fetchJSON(`${API}/models`);
    if (!data) return;

    _currentModels = data.models || [];
    _activeModel = data.active_model || '';

    const list = container.querySelector('#avatar-model-list');
    if (!_currentModels.length) {
        list.innerHTML = '<div class="avatar-help">No models uploaded yet.</div>';
        return;
    }

    list.innerHTML = _currentModels.map(m => `
        <div class="avatar-model-card ${m.active ? 'active' : ''}" data-filename="${m.filename}">
            <div class="avatar-model-info">
                <span class="avatar-model-name">${m.filename}</span>
                <span class="avatar-model-meta">${(m.size / 1024 / 1024).toFixed(1)}MB${m.track_count ? ' · ' + m.track_count + ' mapped' : ''}</span>
            </div>
            <div class="avatar-model-actions">
                ${m.active ? '<span class="avatar-badge">Active</span>' : `<button class="avatar-btn avatar-btn-sm" data-action="activate">Use</button>`}
                <button class="avatar-btn avatar-btn-sm avatar-btn-danger" data-action="delete">Delete</button>
            </div>
        </div>
    `).join('');

    // Wire card actions
    list.querySelectorAll('[data-action="activate"]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const filename = btn.closest('[data-filename]').dataset.filename;
            await fetchJSON(`${API}/config`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ active_model: filename }),
            });
            await loadModels(container);
        });
    });

    list.querySelectorAll('[data-action="delete"]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const filename = btn.closest('[data-filename]').dataset.filename;
            if (!confirm(`Delete ${filename}?`)) return;
            await fetchJSON(`${API}/models/${filename}`, { method: 'DELETE' });
            await loadModels(container);
        });
    });

    // Load track mapping for active model
    if (_activeModel) {
        await loadTrackMapping(container);
    }
}

async function loadTrackMapping(container) {
    // Get tracks + config in one call where possible
    const [trackData, cfg] = await Promise.all([
        fetchJSON(`${API}/tracks/${_activeModel}`),
        fetchJSON(`${API}/config`),
    ]);
    if (!trackData) return;
    _activeTracks = trackData.tracks || [];
    _activeConfig = (cfg?.models || {})[_activeModel] || {};

    const trackMap = _activeConfig.track_map || {};
    const idlePool = _activeConfig.idle_pool || [];
    const greetingTrack = _activeConfig.greeting_track || '';

    // Show sections
    container.querySelector('#avatar-mapping-section').style.display = '';
    container.querySelector('#avatar-idle-section').style.display = '';
    container.querySelector('#avatar-greeting-section').style.display = '';

    // Track mapping grid
    const grid = container.querySelector('#avatar-track-grid');
    const trackOptions = _activeTracks.map(t =>
        `<option value="${t.name}">${t.name} (${t.duration}s)</option>`
    ).join('');

    grid.innerHTML = AVATAR_STATES.map(s => `
        <div class="avatar-field">
            <label>${s.label}</label>
            <select data-state="${s.key}">
                <option value="">(none)</option>
                ${trackOptions}
            </select>
        </div>
    `).join('');

    // Set current values
    grid.querySelectorAll('select').forEach(sel => {
        const state = sel.dataset.state;
        if (trackMap[state]) sel.value = trackMap[state];
    });

    // Idle pool
    const poolEl = container.querySelector('#avatar-idle-pool');
    poolEl.innerHTML = _activeTracks.map(t => {
        const entry = idlePool.find(p => p.track === t.name);
        const enabled = !!entry;
        const weight = entry?.weight || 10;
        const oneshot = entry?.oneshot || false;
        return `
            <div class="avatar-idle-row">
                <label>
                    <input type="checkbox" data-track="${t.name}" ${enabled ? 'checked' : ''}>
                    ${t.name}
                </label>
                <input type="number" data-track-weight="${t.name}" min="1" max="100" value="${weight}" class="avatar-weight" ${enabled ? '' : 'disabled'}>
                <label class="avatar-oneshot">
                    <input type="checkbox" data-track-oneshot="${t.name}" ${oneshot ? 'checked' : ''} ${enabled ? '' : 'disabled'}>
                    oneshot
                </label>
            </div>
        `;
    }).join('');

    // Wire checkbox enable/disable
    poolEl.querySelectorAll('input[type="checkbox"][data-track]').forEach(cb => {
        cb.addEventListener('change', () => {
            const track = cb.dataset.track;
            const weightInput = poolEl.querySelector(`[data-track-weight="${track}"]`);
            const oneshotInput = poolEl.querySelector(`[data-track-oneshot="${track}"]`);
            if (weightInput) weightInput.disabled = !cb.checked;
            if (oneshotInput) oneshotInput.disabled = !cb.checked;
        });
    });

    // Greeting dropdown
    const greetSel = container.querySelector('#avatar-greeting-track');
    greetSel.innerHTML = `<option value="">(none)</option>` + trackOptions;
    if (greetingTrack) greetSel.value = greetingTrack;

    // Scale
    const scaleInput = container.querySelector('#avatar-scale');
    if (scaleInput) scaleInput.value = _activeConfig.scale || 1.0;
}

function collectConfig(container) {
    // Track map
    const track_map = {};
    container.querySelectorAll('#avatar-track-grid select').forEach(sel => {
        if (sel.value) track_map[sel.dataset.state] = sel.value;
    });

    // Idle pool
    const idle_pool = [];
    container.querySelectorAll('#avatar-idle-pool input[type="checkbox"][data-track]').forEach(cb => {
        if (!cb.checked) return;
        const track = cb.dataset.track;
        const weight = parseInt(container.querySelector(`[data-track-weight="${track}"]`)?.value || '10');
        const oneshot = container.querySelector(`[data-track-oneshot="${track}"]`)?.checked || false;
        idle_pool.push({ track, weight, oneshot });
    });

    // Greeting + scale
    const greeting_track = container.querySelector('#avatar-greeting-track')?.value || null;
    const scale = parseFloat(container.querySelector('#avatar-scale')?.value || '1.0') || 1.0;

    return {
        active_model: _activeModel,
        models: {
            [_activeModel]: {
                ..._activeConfig,
                track_map,
                idle_pool,
                greeting_track,
                scale,
            }
        }
    };
}

function injectStyles() {
    if (document.getElementById('avatar-settings-styles')) return;
    const style = document.createElement('style');
    style.id = 'avatar-settings-styles';
    style.textContent = `
        .avatar-settings { display: flex !important; flex-direction: column !important; gap: 20px; }
        .avatar-section { display: block !important; }
        .avatar-section h3 { margin: 0 0 8px; font-size: 14px; color: var(--text); }
        .avatar-help { font-size: 12px; color: var(--text-muted); margin: 0 0 8px; }

        .avatar-model-list { display: flex !important; flex-direction: column !important; gap: 6px; margin-bottom: 10px; }
        .avatar-model-card {
            display: flex !important; justify-content: space-between; align-items: center;
            padding: 8px 12px; border-radius: 6px;
            background: var(--bg-primary); border: 1px solid var(--border);
        }
        .avatar-model-card.active { border-color: #4a9eff; }
        .avatar-model-name { font-size: 13px; font-weight: 500; display: block; }
        .avatar-model-meta { font-size: 11px; color: var(--text-muted); display: block; margin-top: 2px; }
        .avatar-model-actions { display: flex !important; gap: 6px; align-items: center; }
        .avatar-badge { font-size: 11px; color: #4a9eff; border: 1px solid #4a9eff; border-radius: 4px; padding: 2px 6px; }

        .avatar-track-grid { display: flex !important; flex-direction: column !important; gap: 6px; }
        .avatar-field { display: flex !important; align-items: center; gap: 8px; }
        .avatar-field label { min-width: 80px; font-size: 13px; color: var(--text); flex-shrink: 0; }
        .avatar-field select {
            flex: 1; padding: 5px 8px; border: 1px solid var(--border);
            border-radius: 5px; background: var(--bg-primary); color: var(--text); font-size: 12px;
        }

        .avatar-idle-row {
            display: flex !important; align-items: center; gap: 10px; padding: 4px 0;
        }
        .avatar-idle-row > label { font-size: 13px; color: var(--text); min-width: 120px; flex-shrink: 0; }
        .avatar-weight { width: 50px; padding: 3px 6px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-primary); color: var(--text); font-size: 12px; text-align: center; }
        .avatar-oneshot { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }

        .avatar-upload-btn {
            display: inline-block; padding: 6px 14px; border-radius: 6px; cursor: pointer;
            background: var(--bg-primary); border: 1px dashed var(--border); color: var(--text);
            font-size: 12px; text-align: center; transition: border-color 0.15s;
        }
        .avatar-upload-btn:hover { border-color: #4a9eff; }

        .avatar-btn {
            padding: 5px 12px; border: 1px solid var(--border); border-radius: 5px;
            background: var(--bg-primary); color: var(--text); cursor: pointer; font-size: 12px;
        }
        .avatar-btn:hover { background: var(--bg-secondary); }
        .avatar-btn-primary { background: #4a9eff; color: white; border-color: #4a9eff; }
        .avatar-btn-primary:hover { background: #3a8eef; }
        .avatar-btn-sm { padding: 3px 8px; font-size: 11px; }
        .avatar-btn-danger { color: var(--error, #ff4444); }
        .avatar-btn-danger:hover { background: var(--error, #ff4444); color: white; }
    `;
    document.head.appendChild(style);
}
