// ── AI PROVIDER SETTINGS ──

const DEFAULT_PROVIDER = {
    id: 'pollinations',
    name: 'Pollinations AI',
    base_url: 'https://text.pollinations.ai/openai',
    model: 'openai',
    api_key: '',
    requires_key: false,
};

let providerPresets = [];

function loadProviderSettings() {
    try {
        const saved = localStorage.getItem('ai_provider');
        if (saved) {
            const parsed = JSON.parse(saved);
            // Migrate from old broken Pollinations URL
            if (parsed.base_url === 'https://gen.pollinations.ai/v1') {
                parsed.base_url = 'https://text.pollinations.ai/openai';
                if (parsed.model === 'claude-large') parsed.model = 'openai';
                localStorage.setItem('ai_provider', JSON.stringify(parsed));
            }
            return { ...DEFAULT_PROVIDER, ...parsed };
        }
    } catch (e) { }
    return { ...DEFAULT_PROVIDER };
}

function saveProviderSettings(settings) {
    localStorage.setItem('ai_provider', JSON.stringify(settings));
    updateProviderBadge();
}

function getProviderHeaders() {
    const s = loadProviderSettings();
    const headers = {};
    if (s.base_url) headers['X-AI-Base-URL'] = s.base_url;
    if (s.api_key) headers['X-AI-API-Key'] = s.api_key;
    if (s.model) headers['X-AI-Model'] = s.model;
    return headers;
}

function updateProviderBadge() {
    const s = loadProviderSettings();
    const badge = document.getElementById('provider-badge');
    if (badge) {
        badge.textContent = s.name || s.id || 'Pollinations';
        badge.title = `${s.base_url} — ${s.model}`;
    }
}

async function openSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    const content = modal.querySelector('.settings-modal-body');
    if (content) content.scrollTop = 0;

    // Load presets if not cached
    if (providerPresets.length === 0) {
        try {
            const res = await fetch('/api/providers');
            providerPresets = await res.json();
        } catch (e) {
            providerPresets = [];
        }
    }

    renderProviderCards();
    highlightActiveProvider();
}

function closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.style.display = 'none';
}

function renderProviderCards() {
    const container = document.getElementById('provider-cards');
    if (!container) return;

    container.innerHTML = providerPresets.map(p => `
    <div class="provider-card" data-provider-id="${p.id}" onclick="selectProvider('${p.id}')">
      <div class="provider-card-header">
        <span class="provider-card-name">${escapeHtml(p.name)}</span>
        ${!p.requires_key ? '<span class="provider-free-badge">FREE</span>' : ''}
      </div>
      <div class="provider-card-desc">${escapeHtml(p.description)}</div>
    </div>
  `).join('');
}

function highlightActiveProvider() {
    const current = loadProviderSettings();
    document.querySelectorAll('.provider-card').forEach(card => {
        card.classList.toggle('active', card.dataset.providerId === current.id);
    });

    // Fill form fields
    const preset = providerPresets.find(p => p.id === current.id);
    document.getElementById('settings-base-url').value = current.base_url || '';
    document.getElementById('settings-api-key').value = current.api_key || '';

    // Populate model dropdown
    const modelSelect = document.getElementById('settings-model');
    modelSelect.innerHTML = '';
    const models = preset ? preset.models : [];
    if (models.length > 0) {
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            if (m === current.model) opt.selected = true;
            modelSelect.appendChild(opt);
        });
    }
    // Always add custom option
    const customOpt = document.createElement('option');
    customOpt.value = '__custom__';
    customOpt.textContent = '— Custom model name —';
    modelSelect.appendChild(customOpt);

    // If current model not in list, select custom
    if (models.length === 0 || !models.includes(current.model)) {
        modelSelect.value = '__custom__';
        document.getElementById('settings-custom-model').style.display = 'block';
        document.getElementById('settings-custom-model-input').value = current.model || '';
    } else {
        document.getElementById('settings-custom-model').style.display = 'none';
    }

    // Show/hide API key field
    const keyRow = document.getElementById('settings-key-row');
    if (keyRow) {
        keyRow.style.display = (preset && !preset.requires_key) ? 'none' : 'block';
    }
}

function selectProvider(providerId) {
    const preset = providerPresets.find(p => p.id === providerId);
    if (!preset) return;

    document.getElementById('settings-base-url').value = preset.base_url || '';
    document.getElementById('settings-api-key').value = '';

    const modelSelect = document.getElementById('settings-model');
    modelSelect.innerHTML = '';
    (preset.models || []).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        if (m === preset.default_model) opt.selected = true;
        modelSelect.appendChild(opt);
    });
    const customOpt = document.createElement('option');
    customOpt.value = '__custom__';
    customOpt.textContent = '— Custom model name —';
    modelSelect.appendChild(customOpt);

    document.getElementById('settings-custom-model').style.display = 'none';
    document.getElementById('settings-custom-model-input').value = '';

    const keyRow = document.getElementById('settings-key-row');
    if (keyRow) keyRow.style.display = preset.requires_key ? 'block' : 'none';

    document.querySelectorAll('.provider-card').forEach(card => {
        card.classList.toggle('active', card.dataset.providerId === providerId);
    });
}

function onModelSelectChange() {
    const val = document.getElementById('settings-model').value;
    const customDiv = document.getElementById('settings-custom-model');
    if (val === '__custom__') {
        customDiv.style.display = 'block';
    } else {
        customDiv.style.display = 'none';
    }
}

function saveSettings() {
    const activeCard = document.querySelector('.provider-card.active');
    const providerId = activeCard ? activeCard.dataset.providerId : 'custom';
    const preset = providerPresets.find(p => p.id === providerId);

    const baseUrl = document.getElementById('settings-base-url').value.trim();
    const apiKey = document.getElementById('settings-api-key').value.trim();
    const modelSelect = document.getElementById('settings-model').value;
    const customModel = document.getElementById('settings-custom-model-input').value.trim();
    const model = modelSelect === '__custom__' ? customModel : modelSelect;

    if (!baseUrl) {
        alert('Please enter a Base URL');
        return;
    }
    if (!model) {
        alert('Please select or enter a model name');
        return;
    }

    const settings = {
        id: providerId,
        name: preset ? preset.name : 'Custom Provider',
        base_url: baseUrl,
        api_key: apiKey,
        model: model,
        requires_key: preset ? preset.requires_key : true,
    };

    saveProviderSettings(settings);
    closeSettingsModal();

    // Show confirmation
    const status = document.getElementById('settings-status');
    if (status) {
        status.textContent = `✅ Saved! Using ${settings.name} with ${model}`;
        status.style.display = 'block';
        setTimeout(() => { status.style.display = 'none'; }, 3000);
    }
}

// ── Global fetch interceptor: auto-inject provider headers on all /api/ calls ──
(function () {
    const originalFetch = window.fetch;
    window.fetch = function (url, options) {
        options = options || {};
        const urlStr = typeof url === 'string' ? url : (url instanceof Request ? url.url : String(url));
        if (urlStr.startsWith('/api/')) {
            const providerHeaders = getProviderHeaders();
            if (Object.keys(providerHeaders).length > 0) {
                if (options.headers instanceof Headers) {
                    for (const [k, v] of Object.entries(providerHeaders)) {
                        if (!options.headers.has(k)) options.headers.set(k, v);
                    }
                } else {
                    options.headers = { ...providerHeaders, ...(options.headers || {}) };
                }
            }
        }
        return originalFetch.call(this, url, options);
    };
})();

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    updateProviderBadge();
});
