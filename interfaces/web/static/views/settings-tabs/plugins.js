// settings-tabs/plugins.js - Plugin toggles tab
import * as ui from '../../ui.js';
import { showDangerConfirm } from '../../shared/danger-confirm.js';
import pluginsAPI from '../../shared/plugins-api.js';

// Infrastructure plugins hidden from toggle list
const HIDDEN = new Set([
    'setup-wizard', 'backup', 'continuity'
]);

// Danger confirmation configs for risky plugins
const DANGER_PLUGINS = {
    ssh: {
        title: 'Enable SSH — Remote Command Execution',
        warnings: [
            'The AI can execute shell commands on configured servers',
            'Commands run with the permissions of the SSH user',
            'There is no confirmation before command execution',
            'A blacklist blocks obvious destructive commands, but it is not comprehensive',
        ],
        buttonLabel: 'Enable SSH',
        doubleConfirm: true,
        stage2Title: '\u26A0 Final Confirmation — Shell Access',
        stage2Warnings: [
            'The AI can delete files, kill processes, and modify system configuration',
            'A single bad command can brick a server or destroy data',
            'Review your blacklist and keep SSH out of chats with scheduled tasks',
        ],
    },
    bitcoin: {
        title: 'Enable Bitcoin — Autonomous Transactions',
        warnings: [
            'The AI can send Bitcoin from any configured wallet',
            'Transactions are irreversible — sent BTC cannot be recovered',
            'There is no amount limit or address whitelist',
            'A single hallucinated tool call can result in permanent loss of funds',
        ],
        buttonLabel: 'Enable Bitcoin',
        doubleConfirm: true,
        stage2Title: '\u26A0 Final Confirmation — Real Money',
        stage2Warnings: [
            'You are enabling autonomous control over real financial assets',
            'Ensure your toolsets are configured carefully',
            'Consider keeping BTC tools out of chats with scheduled tasks',
        ],
    },
    email: {
        title: 'Enable Email — AI Sends From Your Address',
        warnings: [
            'The AI can read your inbox and send emails to whitelisted contacts',
            'The AI can reply to any email regardless of whitelist',
            'The AI can archive (permanently move) messages',
            'Emails are sent from your real email address',
        ],
        buttonLabel: 'Enable Email',
    },
    homeassistant: {
        title: 'Enable Home Assistant — Smart Home Control',
        warnings: [
            'The AI can control lights, switches, thermostats, and scenes',
            'The AI can read presence data (who is home)',
            'The AI can trigger HA scripts which may have broad permissions',
            'Locks and covers are blocked by default — review your blacklist',
        ],
        buttonLabel: 'Enable Home Assistant',
    },
    toolmaker: {
        title: 'Enable Tool Maker — AI Code Execution',
        warnings: [
            'The AI can write Python code and install it as a live tool',
            'Custom tools run inside the Sapphire process with full access',
            'Validation catches common dangerous patterns but is not a sandbox',
            'A motivated prompt injection could bypass validation',
        ],
        buttonLabel: 'Enable Tool Maker',
        doubleConfirm: true,
        stage2Title: '\u26A0 Final Confirmation — Code Execution',
        stage2Warnings: [
            'Custom tools persist across restarts',
            'Review AI-created plugins in user/plugins/ periodically',
            'Consider keeping Tool Maker out of public-facing chats',
        ],
    },
};

// Plugins that own a nav-rail view
const PLUGIN_NAV_MAP = { continuity: 'schedule' };

// Prevent double-click race condition on toggles
const toggling = new Set();

export default {
    id: 'plugins',
    name: 'Plugins',
    icon: '🔌',
    description: 'Enable or disable feature plugins',

    render(ctx) {
        const visible = (ctx.pluginList || []).filter(p => !HIDDEN.has(p.name));
        if (!visible.length) return '<p class="text-muted">No feature plugins available.</p>';

        const allowUnsigned = ctx.settings?.ALLOW_UNSIGNED_PLUGINS ?? false;

        return `
            <div class="plugin-actions" style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
                <button class="btn btn-sm" id="rescan-plugins-btn">Rescan Plugins</button>
                <label class="setting-toggle" style="margin-left:auto">
                    <input type="checkbox" id="allow-unsigned-toggle" ${allowUnsigned ? 'checked' : ''}>
                    <span>Allow Unsigned Plugins</span>
                </label>
            </div>
            <div class="plugin-install-section" style="margin-bottom:16px;padding:14px;background:var(--bg-secondary);border-radius:var(--radius-sm);border:1px solid var(--border);">
                <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
                    <input type="text" id="plugin-install-url" placeholder="GitHub URL (e.g. https://github.com/user/plugin)"
                           style="flex:1;padding:8px 10px;background:var(--input-bg);border:1px solid var(--border-light);border-radius:var(--radius-sm);color:var(--text-light);font-size:0.9em;">
                    <button class="btn btn-sm" id="plugin-install-url-btn">Install</button>
                </div>
                <div style="display:flex;gap:8px;align-items:center;">
                    <input type="file" id="plugin-install-file" accept=".zip" style="flex:1;font-size:0.85em;color:var(--text-muted);">
                    <button class="btn btn-sm" id="plugin-install-file-btn">Upload</button>
                </div>
            </div>
            <div class="plugin-toggles-list">
                ${visible.map(p => {
                    const locked = ctx.lockedPlugins.includes(p.name);
                    let verifyBadge = '';
                    const tier = p.verify_tier;
                    if (tier === 'official') {
                        verifyBadge = '<span class="plugin-toggle-badge verified">Official</span>';
                    } else if (tier === 'verified_author') {
                        const authorName = p.verified_author || 'Unknown';
                        verifyBadge = `<span class="plugin-toggle-badge author">Verified Author (${authorName})</span>`;
                    } else if (tier === 'unsigned' || (!tier && p.verify_msg === 'unsigned')) {
                        verifyBadge = '<span class="plugin-toggle-badge unsigned">Unsigned</span>';
                    } else if (tier === 'failed' || (!tier && p.verified === false && p.verify_msg && p.verify_msg !== 'unsigned')) {
                        verifyBadge = '<span class="plugin-toggle-badge failed">Tampered</span>';
                    } else if (!tier && p.verified === true) {
                        // Fallback for old API without verify_tier
                        verifyBadge = '<span class="plugin-toggle-badge verified">Official</span>';
                    }
                    const meta = [];
                    if (p.version) meta.push(`v${p.version}`);
                    if (p.author) meta.push(p.author);
                    const metaStr = meta.length ? `<span class="plugin-toggle-meta">${meta.join(' · ')}</span>` : '';
                    const urlLink = p.url ? `<a href="${p.url}" target="_blank" rel="noopener" class="plugin-toggle-link">View</a>` : '';

                    const isUser = p.band === 'user';
                    const userActions = isUser ? `
                        <div class="plugin-user-actions" style="display:flex;gap:4px;margin-left:8px;">
                            <button class="btn btn-sm plugin-update-btn" data-plugin="${p.name}"
                                    style="font-size:0.75em;padding:2px 8px;">Check Update</button>
                            <button class="btn btn-sm btn-danger plugin-uninstall-btn" data-plugin="${p.name}"
                                    style="font-size:0.75em;padding:2px 8px;">Uninstall</button>
                        </div>
                    ` : '';

                    return `
                        <div class="plugin-toggle-item${p.enabled ? ' enabled' : ''}" data-plugin="${p.name}">
                            <div class="plugin-toggle-info">
                                <div class="plugin-toggle-header">
                                    <span class="plugin-toggle-name">${p.title || p.name}</span>
                                    ${locked ? '<span class="plugin-toggle-badge">Core</span>' : ''}
                                    ${verifyBadge}
                                    ${urlLink}
                                </div>
                                ${metaStr}
                            </div>
                            <div style="display:flex;align-items:center;">
                                <label class="setting-toggle">
                                    <input type="checkbox" data-plugin-toggle="${p.name}"
                                           ${p.enabled ? 'checked' : ''} ${locked ? 'disabled' : ''}>
                                    <span>${p.enabled ? 'Enabled' : 'Disabled'}</span>
                                </label>
                                ${userActions}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    },

    attachListeners(ctx, el) {
        // Sideloading toggle
        const unsignedToggle = el.querySelector('#allow-unsigned-toggle');
        if (unsignedToggle) {
            unsignedToggle.addEventListener('change', async e => {
                const enabling = e.target.checked;

                if (enabling) {
                    const confirmed = await showDangerConfirm({
                        title: 'Allow Unsigned Plugins — No Signature Verification',
                        warnings: [
                            'Unsigned plugins have not been verified by Sapphire',
                            'They can execute arbitrary code with full system access',
                            'A malicious plugin could steal credentials, modify files, or exfiltrate data',
                            'Only enable this if you trust the source of your plugins',
                        ],
                        buttonLabel: 'Allow Unsigned',
                        doubleConfirm: true,
                        stage2Title: 'Final Confirmation — Unsigned Plugins',
                        stage2Warnings: [
                            'You are disabling signature verification for all non-system plugins',
                            'This cannot be undone automatically — you must manually disable plugins if compromised',
                            'Sapphire cannot guarantee the safety of unsigned code',
                        ],
                    });
                    if (!confirmed) {
                        e.target.checked = false;
                        return;
                    }
                }

                try {
                    const res = await fetch('/api/settings/batch', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ settings: { ALLOW_UNSIGNED_PLUGINS: enabling } })
                    });
                    if (!res.ok) throw new Error('Failed to save');
                    ctx.settings.ALLOW_UNSIGNED_PLUGINS = enabling;
                    ui.showToast(`Unsigned plugins ${enabling ? 'allowed' : 'blocked'}`, enabling ? 'warning' : 'success');
                    if (!enabling) await ctx.refreshTab();
                } catch (err) {
                    e.target.checked = !enabling;
                    ui.showToast(`Setting failed: ${err.message}`, 'error');
                }
            });
        }

        // Rescan button
        const rescanBtn = el.querySelector('#rescan-plugins-btn');
        if (rescanBtn) {
            rescanBtn.addEventListener('click', async () => {
                rescanBtn.disabled = true;
                rescanBtn.textContent = 'Scanning...';
                try {
                    const res = await fetch('/api/plugins/rescan', { method: 'POST' });
                    if (!res.ok) throw new Error('Rescan failed');
                    const data = await res.json();
                    const added = data.added?.length || 0;
                    const removed = data.removed?.length || 0;
                    if (added || removed) {
                        ui.showToast(`Rescan: ${added} added, ${removed} removed`, 'success');
                        await ctx.refreshTab();
                    } else {
                        ui.showToast('No new plugins found', 'info');
                    }
                } catch (err) {
                    ui.showToast(`Rescan failed: ${err.message}`, 'error');
                } finally {
                    rescanBtn.disabled = false;
                    rescanBtn.textContent = 'Rescan Plugins';
                }
            });
        }

        // ── Install from URL ──
        const installUrlBtn = el.querySelector('#plugin-install-url-btn');
        if (installUrlBtn) {
            installUrlBtn.addEventListener('click', async () => {
                const urlInput = el.querySelector('#plugin-install-url');
                const url = urlInput?.value?.trim();
                if (!url) { ui.showToast('Enter a GitHub URL', 'warning'); return; }
                installUrlBtn.disabled = true;
                installUrlBtn.textContent = 'Installing...';
                try {
                    const result = await pluginsAPI.installPlugin({ url });
                    if (result.conflict) {
                        // Plugin exists — ask to replace
                        const confirmed = await showDangerConfirm({
                            title: `Replace Plugin: ${result.name}`,
                            warnings: [
                                `Installed: v${result.existing_version || '?'} by ${result.existing_author || 'unknown'}`,
                                `New: v${result.version || '?'} by ${result.author || 'unknown'}`,
                                'The existing plugin and its settings will be replaced',
                                'Plugin state data will be preserved',
                            ],
                            buttonLabel: 'Replace',
                        });
                        if (!confirmed) return;
                        const forced = await pluginsAPI.installPlugin({ url, force: true });
                        ui.showToast(`Updated ${forced.plugin_name} → v${forced.version}`, 'success');
                    } else {
                        ui.showToast(`Installed ${result.plugin_name} v${result.version}`, 'success');
                    }
                    urlInput.value = '';
                    await ctx.refreshTab();
                } catch (err) {
                    ui.showToast(`Install failed: ${err.message}`, 'error', 5000);
                } finally {
                    installUrlBtn.disabled = false;
                    installUrlBtn.textContent = 'Install';
                }
            });
        }

        // ── Install from zip upload ──
        const installFileBtn = el.querySelector('#plugin-install-file-btn');
        if (installFileBtn) {
            installFileBtn.addEventListener('click', async () => {
                const fileInput = el.querySelector('#plugin-install-file');
                const file = fileInput?.files?.[0];
                if (!file) { ui.showToast('Select a zip file', 'warning'); return; }
                installFileBtn.disabled = true;
                installFileBtn.textContent = 'Uploading...';
                try {
                    const result = await pluginsAPI.installPlugin({ file });
                    if (result.conflict) {
                        const confirmed = await showDangerConfirm({
                            title: `Replace Plugin: ${result.name}`,
                            warnings: [
                                `Installed: v${result.existing_version || '?'} by ${result.existing_author || 'unknown'}`,
                                `New: v${result.version || '?'} by ${result.author || 'unknown'}`,
                                'The existing plugin and its settings will be replaced',
                                'Plugin state data will be preserved',
                            ],
                            buttonLabel: 'Replace',
                        });
                        if (!confirmed) return;
                        const forced = await pluginsAPI.installPlugin({ file, force: true });
                        ui.showToast(`Updated ${forced.plugin_name} → v${forced.version}`, 'success');
                    } else {
                        ui.showToast(`Installed ${result.plugin_name} v${result.version}`, 'success');
                    }
                    fileInput.value = '';
                    await ctx.refreshTab();
                } catch (err) {
                    ui.showToast(`Install failed: ${err.message}`, 'error', 5000);
                } finally {
                    installFileBtn.disabled = false;
                    installFileBtn.textContent = 'Upload';
                }
            });
        }

        // Store ctx on el so the handler always uses the latest after refreshTab()
        el._pluginCtx = ctx;

        // Bind toggle handler once — prevents stacking on repeated renderTabContent() calls
        if (el._pluginsBound) return;
        el._pluginsBound = true;

        // ── Uninstall (delegated) ──
        el.addEventListener('click', async e => {
            const btn = e.target.closest('.plugin-uninstall-btn');
            if (!btn) return;
            const name = btn.dataset.plugin;
            const ctx = el._pluginCtx;
            const plugin = ctx.pluginList?.find(p => p.name === name);

            const confirmed = await showDangerConfirm({
                title: `Uninstall Plugin: ${plugin?.title || name}`,
                warnings: [
                    'The plugin and all its settings will be permanently deleted',
                    'Plugin state data will also be removed',
                    'This cannot be undone',
                ],
                buttonLabel: 'Uninstall',
            });
            if (!confirmed) return;

            btn.disabled = true;
            btn.textContent = 'Removing...';
            try {
                await pluginsAPI.uninstallPlugin(name);
                // Unregister settings tab if any
                try {
                    const { unregisterPluginSettings } = await import('../../shared/plugin-registry.js');
                    unregisterPluginSettings(name);
                    ctx.syncDynamicTabs();
                } catch (_) {}
                ui.showToast(`Uninstalled ${plugin?.title || name}`, 'success');
                window.dispatchEvent(new CustomEvent('functions-changed'));
                await ctx.refreshTab();
            } catch (err) {
                ui.showToast(`Uninstall failed: ${err.message}`, 'error', 5000);
                btn.disabled = false;
                btn.textContent = 'Uninstall';
            }
        });

        // ── Check update (delegated) ──
        el.addEventListener('click', async e => {
            const btn = e.target.closest('.plugin-update-btn');
            if (!btn) return;
            const name = btn.dataset.plugin;
            const ctx = el._pluginCtx;

            btn.disabled = true;
            btn.textContent = 'Checking...';
            try {
                const result = await pluginsAPI.checkUpdate(name);
                if (result.update_available) {
                    btn.textContent = `Update to v${result.remote_version}`;
                    btn.disabled = false;
                    btn.classList.add('btn-primary');
                    // Replace click handler to trigger install
                    btn.classList.remove('plugin-update-btn');
                    btn.addEventListener('click', async () => {
                        btn.disabled = true;
                        btn.textContent = 'Updating...';
                        try {
                            await pluginsAPI.installPlugin({ url: result.source_url, force: true });
                            ui.showToast(`Updated ${name} → v${result.remote_version}`, 'success');
                            await ctx.refreshTab();
                        } catch (err) {
                            ui.showToast(`Update failed: ${err.message}`, 'error', 5000);
                            btn.disabled = false;
                            btn.textContent = `Update to v${result.remote_version}`;
                        }
                    }, { once: true });
                } else {
                    btn.textContent = 'Up to date';
                    setTimeout(() => {
                        btn.textContent = 'Check Update';
                        btn.disabled = false;
                    }, 2000);
                }
            } catch (err) {
                ui.showToast(`Update check failed: ${err.message}`, 'error');
                btn.textContent = 'Check Update';
                btn.disabled = false;
            }
        });

        el.addEventListener('change', async e => {
            const name = e.target.dataset.pluginToggle;
            if (!name) return;

            const ctx = el._pluginCtx;

            // Guard against rapid double-clicks
            if (toggling.has(name)) {
                e.preventDefault();
                e.target.checked = !e.target.checked;  // revert browser toggle
                return;
            }

            // Per-plugin unsigned gate
            if (e.target.checked) {
                const plugin = ctx.pluginList.find(p => p.name === name);
                if (plugin?.verify_msg === 'unsigned') {
                    toggling.add(name);
                    const unsignedOk = await showDangerConfirm({
                        title: `Enable Unsigned Plugin: ${plugin.title || plugin.name}`,
                        warnings: [
                            'This plugin has no verified signature',
                            'It will execute code with access to your system',
                            'Review the plugin source before enabling',
                        ],
                        buttonLabel: 'Enable Plugin',
                    });
                    toggling.delete(name);
                    if (!unsignedOk) {
                        e.target.checked = false;
                        return;
                    }
                }
            }

            // Danger gate for risky plugins on enable
            const dangerConfig = DANGER_PLUGINS[name];
            if (dangerConfig && e.target.checked) {
                const ackKey = `sapphire_danger_ack_${name}`;
                if (!localStorage.getItem(ackKey)) {
                    // Prevent the toggle from firing until confirmed
                    toggling.add(name);
                    const confirmed = await showDangerConfirm(dangerConfig);
                    toggling.delete(name);
                    if (!confirmed) {
                        e.target.checked = false;
                        return;
                    }
                    localStorage.setItem(ackKey, Date.now().toString());
                }
            }

            toggling.add(name);
            e.target.disabled = true;

            const item = e.target.closest('.plugin-toggle-item');
            const span = e.target.parentElement?.querySelector('span');

            try {
                const res = await fetch(`/api/webui/plugins/toggle/${name}`, { method: 'PUT' });
                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    throw new Error(body.detail || body.error || res.status);
                }
                const data = await res.json();

                // Update cached plugin list
                const cached = ctx.pluginList.find(p => p.name === name);
                if (cached) cached.enabled = data.enabled;

                // Load or unload dynamic settings tab
                if (data.enabled && cached?.settingsUI) {
                    await ctx.loadPluginTab(name, cached.settingsUI);
                } else if (!data.enabled) {
                    const { unregisterPluginSettings } = await import(
                        '../../shared/plugin-registry.js'
                    );
                    unregisterPluginSettings(name);
                    ctx.syncDynamicTabs();
                }

                // Hide/show associated nav-rail item
                const navView = PLUGIN_NAV_MAP[name];
                if (navView) {
                    const navBtn = document.querySelector(`.nav-item[data-view="${navView}"]`);
                    if (navBtn) navBtn.style.display = data.enabled ? '' : 'none';
                }

                // Update DOM in-place (no full re-render flash)
                if (item) item.classList.toggle('enabled', data.enabled);
                if (span) span.textContent = data.enabled ? 'Enabled' : 'Disabled';

                // Only full re-render if tab list changed (plugin with settings UI)
                if (cached?.settingsUI) ctx.refreshSidebar();

                window.dispatchEvent(new CustomEvent('functions-changed'));
                ui.showToast(`${cached?.title || name} ${data.enabled ? 'enabled' : 'disabled'}`, 'success');
            } catch (err) {
                // Revert checkbox
                e.target.checked = !e.target.checked;
                if (span) span.textContent = e.target.checked ? 'Enabled' : 'Disabled';
                const msg = (err.message || 'Unknown error').replace(/^Plugin blocked:\s*/, '');
                console.warn('Plugin toggle blocked:', msg);
                ui.showToast(msg, 'error', 5000);
            } finally {
                toggling.delete(name);
                e.target.disabled = false;
            }
        });
    }
};
