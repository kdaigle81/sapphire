// settings-tabs/plugins.js - Plugin toggles tab
import * as ui from '../../ui.js';
import { showDangerConfirm } from '../../shared/danger-confirm.js';

// Infrastructure plugins hidden from toggle list
const HIDDEN = new Set([
    'setup-wizard', 'plugins-modal', 'backup', 'continuity'
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
            'Review tools in user/functions/ periodically',
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

        return `
            <div class="plugin-toggles-list">
                ${visible.map(p => {
                    const locked = ctx.lockedPlugins.includes(p.name);
                    return `
                        <div class="plugin-toggle-item${p.enabled ? ' enabled' : ''}" data-plugin="${p.name}">
                            <div class="plugin-toggle-info">
                                <span class="plugin-toggle-name">${p.title || p.name}</span>
                                ${locked ? '<span class="plugin-toggle-badge">Core</span>' : ''}
                            </div>
                            <label class="setting-toggle">
                                <input type="checkbox" data-plugin-toggle="${p.name}"
                                       ${p.enabled ? 'checked' : ''} ${locked ? 'disabled' : ''}>
                                <span>${p.enabled ? 'Enabled' : 'Disabled'}</span>
                            </label>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    },

    attachListeners(ctx, el) {
        el.addEventListener('change', async e => {
            const name = e.target.dataset.pluginToggle;
            if (!name) return;

            // Guard against rapid double-clicks
            if (toggling.has(name)) {
                e.preventDefault();
                e.target.checked = !e.target.checked;  // revert browser toggle
                return;
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
                if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.status);
                const data = await res.json();

                // Update cached plugin list
                const cached = ctx.pluginList.find(p => p.name === name);
                if (cached) cached.enabled = data.enabled;

                // Load or unload dynamic settings tab
                if (data.enabled && cached?.settingsUI) {
                    await ctx.loadPluginTab(name, cached.settingsUI);
                } else if (!data.enabled) {
                    const { unregisterPluginSettings } = await import(
                        '../../core-ui/plugins-modal/plugin-registry.js'
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

                ctx.refreshSidebar();
                window.dispatchEvent(new CustomEvent('functions-changed'));
                ui.showToast(`${cached?.title || name} ${data.enabled ? 'enabled' : 'disabled'}`, 'success');
            } catch (err) {
                // Revert checkbox
                e.target.checked = !e.target.checked;
                if (span) span.textContent = e.target.checked ? 'Enabled' : 'Disabled';
                ui.showToast(`Toggle failed: ${err.message}`, 'error');
            } finally {
                toggling.delete(name);
                // checkbox may be on detached DOM after refreshSidebar, that's fine
                e.target.disabled = false;
            }
        });
    }
};
