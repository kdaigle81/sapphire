// settings-tabs/help-tab.js — Embeds the Help view inside Settings sidebar

export default {
    id: 'help',
    name: 'Help',
    icon: '\uD83D\uDCD6',
    description: 'Guides, shortcuts, and troubleshooting',

    render() {
        return `<div id="settings-help-embed" style="height:100%;overflow:auto">
            <div class="view-placeholder"><p class="text-muted">Loading help...</p></div>
        </div>`;
    },

    async attachListeners(ctx, el) {
        const embed = el.querySelector('#settings-help-embed');
        if (!embed) return;
        try {
            const v = document.querySelector('meta[name="boot-version"]')?.content || '';
            const helpMod = await import(`../help.js?v=${v}`);
            if (helpMod.default?.init) helpMod.default.init(embed);
            if (helpMod.default?.show) helpMod.default.show();
        } catch (e) {
            embed.innerHTML = `<div class="view-placeholder"><p style="color:var(--error)">Failed to load help: ${e.message}</p></div>`;
        }
    }
};
