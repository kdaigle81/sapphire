// settings-tabs/embedding.js - Embedding provider settings
import { renderProviderTab, attachProviderListeners } from '../../shared/provider-selector.js';

const tabConfig = {
    providerKey: 'EMBEDDING_PROVIDER',
    disabledMessage: 'Embeddings disabled. Memory and knowledge search will use text matching only.',

    providers: {
        none: {
            label: 'Disabled',
            essentialKeys: [],
            advancedKeys: []
        },
        local: {
            label: 'Local (Nomic ONNX)',
            essentialKeys: [],
            advancedKeys: []
        },
        api: {
            label: 'Remote (Nomic API)',
            essentialKeys: ['EMBEDDING_API_URL'],
            advancedKeys: ['EMBEDDING_API_KEY']
        },
        sapphire_router: {
            label: 'Sapphire Router',
            essentialKeys: ['SAPPHIRE_ROUTER_URL', 'SAPPHIRE_ROUTER_TENANT_ID'],
            advancedKeys: []
        }
    },

    commonKeys: [],
    commonAdvancedKeys: []
};

export default {
    id: 'embedding',
    name: 'Embedding',
    icon: '\uD83E\uDDF2',
    description: 'Vector embedding engine for memory and knowledge search',

    render(ctx) {
        let html = renderProviderTab(tabConfig, ctx);
        // Test button — shown for all providers except disabled
        html += `
            <div class="settings-grid" style="margin-top: 1rem;">
                <div class="setting-row full-width">
                    <button id="embedding-test-btn" class="btn btn-secondary" style="width: auto;">
                        Test Embedding
                    </button>
                    <span id="embedding-test-result" style="margin-left: 0.75rem; font-size: var(--font-sm);"></span>
                </div>
            </div>
            <div class="settings-grid" style="margin-top: 1.5rem;">
                <div class="setting-row full-width">
                    <div class="setting-label">
                        <label for="setting-MEMORY_DEDUP_THRESHOLD">Memory Dedup Threshold</label>
                        <div class="setting-description">Similarity threshold for detecting duplicate memories (0.0 - 1.0). Higher = stricter matching, fewer false positives.</div>
                    </div>
                    <div class="setting-control" style="display:flex;align-items:center;gap:0.5rem;">
                        <input type="range" id="setting-MEMORY_DEDUP_THRESHOLD" data-key="MEMORY_DEDUP_THRESHOLD"
                            min="0.70" max="0.99" step="0.01"
                            value="${ctx.settings.MEMORY_DEDUP_THRESHOLD ?? 0.92}"
                            style="flex:1;">
                        <span id="dedup-threshold-value" style="font-size:var(--font-sm);min-width:2.5rem;text-align:right;">
                            ${ctx.settings.MEMORY_DEDUP_THRESHOLD ?? 0.92}
                        </span>
                    </div>
                </div>
            </div>`;
        return html;
    },

    attachListeners(ctx, el) {
        attachProviderListeners(tabConfig, ctx, el, this);

        // Set placeholder on URL field after render
        const urlInput = el.querySelector('[data-key="EMBEDDING_API_URL"]');
        if (urlInput) urlInput.placeholder = 'http://your-server:8080/v1/embeddings';

        // Dedup threshold slider — show live value + store as number
        const slider = el.querySelector('#setting-MEMORY_DEDUP_THRESHOLD');
        const valSpan = el.querySelector('#dedup-threshold-value');
        if (slider && valSpan) {
            slider.addEventListener('input', () => { valSpan.textContent = slider.value; });
            slider.addEventListener('change', (e) => {
                e.stopPropagation();  // prevent generic handler from storing as string
                ctx.settings.MEMORY_DEDUP_THRESHOLD = parseFloat(slider.value);
                ctx.markChanged('MEMORY_DEDUP_THRESHOLD', parseFloat(slider.value));
            });
        }

        // Test button
        const btn = el.querySelector('#embedding-test-btn');
        const result = el.querySelector('#embedding-test-result');
        if (btn) btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.textContent = 'Testing...';
            result.textContent = '';
            result.style.color = '';
            try {
                const res = await fetch('/api/embedding/test', { method: 'POST' });
                if (!res.ok) throw new Error(`Server error (${res.status})`);
                const data = await res.json();
                if (data.success) {
                    result.style.color = 'var(--color-success, #4caf50)';
                    result.textContent = `${data.provider} — ${data.dimensions}d vector in ${data.ms}ms`;
                } else {
                    result.style.color = 'var(--color-error, #f44336)';
                    result.textContent = data.error || 'Test failed';
                }
            } catch (e) {
                result.style.color = 'var(--color-error, #f44336)';
                result.textContent = `Error: ${e.message}`;
            }
            btn.disabled = false;
            btn.textContent = 'Test Embedding';
        });
    }
};
