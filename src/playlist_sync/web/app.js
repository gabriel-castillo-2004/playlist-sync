/**
 * Playlist Sync - "A prueba de mamá" Frontend Application
 * Vanilla JavaScript (RNF-5), SSE (RF-10) with contingency polling.
 */

(() => {
  'use strict';

  // Application State
  const state = {
    sources: [],
    activeSourceId: null,
    isSyncing: false,
    expandedSources: new Set(),
    sourceItemsCache: new Map(),
    pollingTimer: null,
    eventSource: null,
  };

  // DOM Elements
  const elements = {
    sourcesContainer: document.getElementById('sources-container'),
    btnReconcile: document.getElementById('btn-reconcile'),
    btnSyncAll: document.getElementById('btn-sync-all'),
    addForm: document.getElementById('add-source-form'),
    sourceInput: document.getElementById('source-url-input'),
    btnAddSource: document.getElementById('btn-add-source'),
    addErrorBox: document.getElementById('add-error-box'),
    addErrorMessage: document.getElementById('add-error-message'),
    btnCloseError: document.getElementById('btn-close-error'),
    podcastSearchBox: document.getElementById('podcast-search-results'),
    podcastResultsList: document.getElementById('podcast-results-list'),
    btnCloseSearch: document.getElementById('btn-close-search'),
    syncBanner: document.getElementById('sync-banner'),
    syncBannerTitle: document.getElementById('sync-banner-title'),
    syncBannerDetail: document.getElementById('sync-banner-detail'),
    syncBannerProgress: document.getElementById('sync-banner-progress'),
    healthPill: document.getElementById('system-health-pill'),
    healthLabel: document.getElementById('health-label'),
    connectionPill: document.getElementById('connection-pill'),
    connectionLabel: document.getElementById('connection-label'),
    healthModal: document.getElementById('health-modal'),
    healthChecksList: document.getElementById('health-checks-list'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    btnModalDismiss: document.getElementById('btn-modal-dismiss'),
    toastContainer: document.getElementById('toast-container'),
  };

  // --- API Client ---

  async function apiRequest(endpoint, options = {}) {
    try {
      const response = await fetch(endpoint, {
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
        ...options,
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const error = new Error(
          data?.detail?.user_message || data?.user_message || data?.message || 'Error en la petición'
        );
        error.status = response.status;
        error.code = data?.detail?.code || data?.code;
        throw error;
      }

      return data;
    } catch (err) {
      if (err.name === 'TypeError' && err.message.includes('fetch')) {
        const netErr = new Error('No se pudo conectar con el servidor local.');
        netErr.status = 0;
        throw netErr;
      }
      throw err;
    }
  }

  // --- Toast Notifications ---

  function showToast(message, duration = 3500) {
    if (!elements.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'all 200ms ease';
      setTimeout(() => toast.remove(), 250);
    }, duration);
  }

  // --- Connection & Contingency Polling ---

  function setConnectionStatus(status) {
    if (!elements.connectionPill || !elements.connectionLabel) return;
    const dot = elements.connectionPill.querySelector('.connection-dot');
    dot.className = `connection-dot ${status}`;

    if (status === 'live') {
      elements.connectionLabel.textContent = 'En vivo';
    } else if (status === 'polling') {
      elements.connectionLabel.textContent = 'Respaldo (5s)';
    } else {
      elements.connectionLabel.textContent = 'Sin conexión';
    }
  }

  function startContingencyPolling() {
    if (state.pollingTimer) return;
    setConnectionStatus('polling');
    state.pollingTimer = setInterval(async () => {
      try {
        await loadSources(false);
        await checkSystemHealth();
      } catch (e) {
        setConnectionStatus('disconnected');
      }
    }, 5000);
  }

  function stopContingencyPolling() {
    if (state.pollingTimer) {
      clearInterval(state.pollingTimer);
      state.pollingTimer = null;
    }
  }

  // --- Server-Sent Events (SSE) (RF-10) ---

  function initSSE() {
    if (state.eventSource) {
      state.eventSource.close();
    }

    try {
      const es = new EventSource('/events');
      state.eventSource = es;

      es.onopen = () => {
        setConnectionStatus('live');
        stopContingencyPolling();
      };

      es.onerror = () => {
        startContingencyPolling();
      };

      es.addEventListener('ping', () => {
        setConnectionStatus('live');
        stopContingencyPolling();
      });

      es.addEventListener('sync_started', (e) => {
        const data = JSON.parse(e.data);
        state.isSyncing = true;
        state.activeSourceId = data.source_id;
        showSyncBanner('Descargando música...', 'Iniciando descarga de canciones');
        renderSources();
      });

      es.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        state.isSyncing = true;
        state.activeSourceId = data.source_id;
        const trackTitle = data.current_track || 'Canción actual';
        const percent = data.percentage || 0;
        updateSyncBanner(
          `Descargando: ${trackTitle}`,
          `Progreso: ${percent}%`,
          percent
        );
      });

      es.addEventListener('sync_completed', (e) => {
        const data = JSON.parse(e.data);
        hideSyncBanner();
        state.isSyncing = false;
        state.activeSourceId = null;
        const msg = data.downloaded > 0
          ? `¡Listo! Se descargaron ${data.downloaded} canciones nuevas.`
          : 'La lista ya estaba al día.';
        showToast(msg);
        loadSources(false);
      });

      es.addEventListener('sync_failed', (e) => {
        hideSyncBanner();
        state.isSyncing = false;
        state.activeSourceId = null;
        showToast('Hubo un problema al sincronizar la lista.');
        loadSources(false);
      });

      es.addEventListener('sync_all_started', (e) => {
        state.isSyncing = true;
        showSyncBanner('Actualizando todas las listas...', 'Procesando una por una');
        renderSources();
      });

      es.addEventListener('sync_all_completed', () => {
        hideSyncBanner();
        state.isSyncing = false;
        state.activeSourceId = null;
        showToast('¡Se revisaron todas tus listas con éxito!');
        loadSources(false);
      });
    } catch (err) {
      startContingencyPolling();
    }
  }

  // --- Banner Controls ---

  function showSyncBanner(title, detail) {
    if (!elements.syncBanner) return;
    elements.syncBanner.classList.remove('hidden');
    elements.syncBannerTitle.textContent = title;
    elements.syncBannerDetail.textContent = detail;
    elements.syncBannerProgress.style.width = '0%';
  }

  function updateSyncBanner(title, detail, percent) {
    if (!elements.syncBanner) return;
    elements.syncBannerTitle.textContent = title;
    elements.syncBannerDetail.textContent = detail;
    elements.syncBannerProgress.style.width = `${Math.min(Math.max(percent, 0), 100)}%`;
  }

  function hideSyncBanner() {
    if (!elements.syncBanner) return;
    elements.syncBanner.classList.add('hidden');
  }

  // --- UI Rendering ---

  function renderSources() {
    if (!elements.sourcesContainer) return;

    if (state.sources.length === 0) {
      elements.sourcesContainer.innerHTML = `
        <div class="empty-state card">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 18V5l12-2v13" />
            <circle cx="6" cy="18" r="3" />
            <circle cx="18" cy="16" r="3" />
          </svg>
          <h2>No tienes listas guardadas</h2>
          <p>Pega un enlace de YouTube o YouTube Music arriba para empezar a guardar tu música.</p>
        </div>
      `;
      return;
    }

    elements.sourcesContainer.innerHTML = '';

    state.sources.forEach((source) => {
      const card = document.createElement('article');
      card.className = 'source-card card';
      card.dataset.sourceId = source.id;

      // Status badge logic
      let badgeHtml = '';
      const isCardSyncing = state.isSyncing && state.activeSourceId === source.id;

      if (isCardSyncing) {
        badgeHtml = '<span class="badge badge-active">Descargando...</span>';
      } else if (source.error_count > 0) {
        badgeHtml = `<span class="badge badge-warning">Problemas en ${source.error_count} ${source.error_count === 1 ? 'canción' : 'canciones'}</span>`;
      } else if (source.pending_count > 0) {
        badgeHtml = `<span class="badge badge-warning">${source.pending_count} nuevas — Descargar</span>`;
      } else {
        badgeHtml = '<span class="badge badge-success">Al día ✓</span>';
      }

      // Counts text
      const countsText = `${source.downloaded_count} de ${source.last_known_count || (source.downloaded_count + source.pending_count)} listas`;

      const isExpanded = state.expandedSources.has(source.id);
      const items = state.sourceItemsCache.get(source.id) || [];

      let itemsHtml = '';
      if (isExpanded) {
        itemsHtml = `
          <div class="source-items-panel">
            ${items.length === 0 ? '<p style="font-size: 0.85rem; color: var(--text-muted);">Cargando canciones...</p>' : ''}
            <div class="items-table">
              ${items.map((it) => `
                <div class="item-row ${it.status === 'error' ? 'item-error' : ''}">
                  <div class="item-info">
                    <div class="item-title">${escapeHtml(it.title)}</div>
                    ${it.status === 'error' ? `<div class="item-error-msg">${escapeHtml(it.error_message || 'No se pudo descargar')}</div>` : ''}
                  </div>
                  <div>
                    ${it.status === 'downloaded' ? '<span style="color: var(--success-text); font-weight: bold;">✓</span>' : ''}
                    ${it.status === 'pending' ? '<span style="color: var(--text-muted); font-size: 0.8rem;">Pendiente</span>' : ''}
                    ${it.status === 'downloading' ? '<span style="color: var(--primary); font-size: 0.8rem;">Descargando</span>' : ''}
                    ${it.status === 'error' ? `<button class="btn btn-secondary btn-sm btn-retry-item" data-item-id="${it.id}">Reintentar</button>` : ''}
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="source-header">
          <img
            src="/covers/${source.id}"
            class="source-cover"
            alt="Portada"
            loading="lazy"
            onerror="this.src='/icons/icon.svg'"
          />
          <div class="source-info">
            <h2 class="source-title">${escapeHtml(source.title)}</h2>
            ${badgeHtml}
            <div class="source-counts">${countsText}</div>
          </div>
        </div>

        <div class="source-actions">
          <button
            class="btn btn-primary btn-sync-source"
            data-source-id="${source.id}"
            ${state.isSyncing ? 'disabled' : ''}
          >
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            <span>${source.pending_count > 0 ? 'Descargar nuevas' : 'Actualizar'}</span>
          </button>

          <button
            class="btn btn-secondary btn-toggle-items"
            data-source-id="${source.id}"
          >
            <span>${isExpanded ? 'Ocultar canciones' : 'Ver canciones'}</span>
          </button>
        </div>

        ${itemsHtml}
      `;

      elements.sourcesContainer.appendChild(card);
    });

    // Attach card event handlers
    elements.sourcesContainer.querySelectorAll('.btn-sync-source').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.sourceId, 10);
        handleSyncSource(id);
      });
    });

    elements.sourcesContainer.querySelectorAll('.btn-toggle-items').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.sourceId, 10);
        handleToggleItems(id);
      });
    });

    elements.sourcesContainer.querySelectorAll('.btn-retry-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.itemId, 10);
        handleRetryItem(id);
      });
    });
  }

  // --- Handlers ---

  async function loadSources(showLoading = true) {
    try {
      const data = await apiRequest('/sources');
      state.sources = data || [];
      renderSources();
    } catch (err) {
      if (showLoading) {
        showToast(err.message || 'Error al cargar las listas');
      }
    }
  }

  async function handleAddSource(event) {
    event.preventDefault();
    hideAddError();
    hidePodcastSearch();

    const inputVal = elements.sourceInput.value.trim();
    if (!inputVal) return;

    elements.btnAddSource.disabled = true;

    // Check if input is a direct URL or a search query
    const isDirectUrl = inputVal.startsWith('http://') || inputVal.startsWith('https://');

    if (isDirectUrl) {
      elements.btnAddSource.innerHTML = '<span>Guardando...</span>';
      try {
        const newSource = await apiRequest('/sources', {
          method: 'POST',
          body: JSON.stringify({ url: inputVal }),
        });

        elements.sourceInput.value = '';
        showToast(`¡"${newSource.title}" guardada!`);
        await loadSources(false);

        // Offer immediate sync
        handleSyncSource(newSource.id);
      } catch (err) {
        showAddError(err.message || 'No se pudo agregar la lista.');
      } finally {
        elements.btnAddSource.disabled = false;
        elements.btnAddSource.innerHTML = '<span>Guardar</span>';
      }
    } else {
      // Search podcast by name via iTunes API
      elements.btnAddSource.innerHTML = '<span>Buscando...</span>';
      try {
        const results = await apiRequest(`/podcasts/search?q=${encodeURIComponent(inputVal)}`);
        if (!results || results.length === 0) {
          showAddError(`No se encontró ningún podcast con el nombre "${inputVal}".`);
        } else {
          showPodcastSearchResults(results);
        }
      } catch (err) {
        showAddError(err.message || 'No se pudo buscar podcasts.');
      } finally {
        elements.btnAddSource.disabled = false;
        elements.btnAddSource.innerHTML = '<span>Guardar</span>';
      }
    }
  }

  function showPodcastSearchResults(results) {
    if (!elements.podcastSearchBox || !elements.podcastResultsList) return;

    elements.podcastResultsList.innerHTML = results.map((item) => `
      <div class="podcast-result-item">
        <img
          src="${escapeHtml(item.cover_url || '/icons/icon.svg')}"
          class="podcast-result-cover"
          alt="Portada"
          onerror="this.src='/icons/icon.svg'"
        />
        <div class="podcast-result-info">
          <div class="podcast-result-title">${escapeHtml(item.title)}</div>
          <div class="podcast-result-meta">${escapeHtml(item.artist)}${item.track_count ? ' · ' + item.track_count + ' episodios' : ''}</div>
        </div>
        <button
          class="btn btn-secondary btn-sm btn-select-podcast"
          data-feed-url="${escapeHtml(item.feed_url)}"
          data-title="${escapeHtml(item.title)}"
        >
          Agregar
        </button>
      </div>
    `).join('');

    elements.podcastSearchBox.classList.remove('hidden');

    elements.podcastResultsList.querySelectorAll('.btn-select-podcast').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const feedUrl = btn.dataset.feedUrl;
        const title = btn.dataset.title;
        btn.disabled = true;
        btn.textContent = 'Guardando...';

        try {
          const newSource = await apiRequest('/sources', {
            method: 'POST',
            body: JSON.stringify({ url: feedUrl }),
          });
          hidePodcastSearch();
          elements.sourceInput.value = '';
          showToast(`¡"${title}" guardado!`);
          await loadSources(false);
          handleSyncSource(newSource.id);
        } catch (err) {
          showAddError(err.message || 'No se pudo agregar este podcast.');
          btn.disabled = false;
          btn.textContent = 'Agregar';
        }
      });
    });
  }

  function hidePodcastSearch() {
    if (elements.podcastSearchBox) {
      elements.podcastSearchBox.classList.add('hidden');
    }
  }

  async function handleSyncSource(sourceId) {
    if (state.isSyncing) {
      showToast('Ya hay una descarga en curso. Espera a que termine.');
      return;
    }

    try {
      await apiRequest(`/sources/${sourceId}/sync`, { method: 'POST' });
      showToast('Descarga iniciada...');
    } catch (err) {
      showToast(err.message || 'No se pudo iniciar la descarga.');
    }
  }

  async function handleSyncAll() {
    if (state.isSyncing) {
      showToast('Ya hay una descarga en curso. Espera a que termine.');
      return;
    }

    try {
      await apiRequest('/sync-all', { method: 'POST' });
      showToast('Revisando todas tus listas...');
    } catch (err) {
      showToast(err.message || 'No se pudo iniciar la sincronización.');
    }
  }

  async function handleReconcile() {
    try {
      const res = await apiRequest('/reconcile', { method: 'POST' });
      showToast(res.message || 'Archivos verificados en disco.');
      await loadSources(false);
    } catch (err) {
      showToast(err.message || 'No se pudo verificar los archivos en disco.');
    }
  }

  async function handleToggleItems(sourceId) {
    if (state.expandedSources.has(sourceId)) {
      state.expandedSources.delete(sourceId);
      renderSources();
      return;
    }

    state.expandedSources.add(sourceId);
    renderSources();

    try {
      const detail = await apiRequest(`/sources/${sourceId}`);
      state.sourceItemsCache.set(sourceId, detail.items || []);
      renderSources();
    } catch (err) {
      showToast('No se pudieron cargar las canciones de esta lista.');
    }
  }

  async function handleRetryItem(itemId) {
    if (state.isSyncing) {
      showToast('Hay una descarga en curso. Espera a que termine antes de reintentar.');
      return;
    }

    try {
      await apiRequest(`/items/${itemId}/retry`, { method: 'POST' });
      showToast('Reintentando descarga...');
    } catch (err) {
      showToast(err.message || 'No se pudo programar el reintento.');
    }
  }

  // --- System Health (RF-15) ---

  async function checkSystemHealth() {
    try {
      const health = await apiRequest('/health');
      const allOk = health.status === 'ok';

      const dot = elements.healthPill.querySelector('.health-dot');
      dot.className = `health-dot ${allOk ? 'health-ok' : 'health-degraded'}`;
      elements.healthLabel.textContent = allOk ? 'Sistema listo ✓' : 'Atención necesaria ⚠️';

      // Store checks for modal
      elements.healthPill.dataset.checks = JSON.stringify(health.checks || []);
    } catch (err) {
      const dot = elements.healthPill.querySelector('.health-dot');
      dot.className = 'health-dot health-degraded';
      elements.healthLabel.textContent = 'Servidor inaccesible';
    }
  }

  function showHealthModal() {
    const raw = elements.healthPill.dataset.checks;
    const checks = raw ? JSON.parse(raw) : [];

    elements.healthChecksList.innerHTML = checks.map((c) => `
      <div class="check-item">
        <div class="check-item-head">
          <span>${escapeHtml(c.name)}</span>
          <span style="color: ${c.passed ? 'var(--success-text)' : 'var(--error-text)'};">
            ${c.passed ? 'Listo ✓' : 'Falta ✗'}
          </span>
        </div>
        <div class="check-item-msg">${escapeHtml(c.message)}</div>
        ${c.recommendation ? `<div class="check-item-rec">${escapeHtml(c.recommendation)}</div>` : ''}
      </div>
    `).join('');

    elements.healthModal.showModal();
  }

  // --- Helpers ---

  function showAddError(msg) {
    elements.addErrorMessage.textContent = msg;
    elements.addErrorBox.classList.remove('hidden');
  }

  function hideAddError() {
    elements.addErrorBox.classList.add('hidden');
    elements.addErrorMessage.textContent = '';
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --- Initialization ---

  function init() {
    // Event Listeners
    elements.addForm.addEventListener('submit', handleAddSource);
    elements.btnCloseError.addEventListener('click', hideAddError);
    elements.btnCloseSearch.addEventListener('click', hidePodcastSearch);
    elements.btnSyncAll.addEventListener('click', handleSyncAll);
    if (elements.btnReconcile) {
      elements.btnReconcile.addEventListener('click', handleReconcile);
    }

    elements.healthPill.addEventListener('click', () => {
      showHealthModal();
    });

    elements.btnCloseModal.addEventListener('click', () => {
      elements.healthModal.close();
    });

    elements.btnModalDismiss.addEventListener('click', () => {
      elements.healthModal.close();
    });

    // Start Real-time SSE
    initSSE();

    // Initial Data Fetch
    loadSources();
    checkSystemHealth();
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

