/** OpenSquilla Web UI — Local Document RAG view. */

const RagView = (() => {
  let _el = null;
  let _rpc = null;
  let _configData = null;
  let _status = null;
  let _sources = [];
  let _results = [];
  let _searchPayload = null;
  let _expandedResults = {};
  let _stateUnsub = null;
  let _busy = null;
  let _busyTimer = null;
  let _lastJobSummary = null;
  let _settingsNotice = null;
  let _settingsSaving = false;
  let _selectedUploadFile = null;

  const DEFAULT_INCLUDE = '*.md,*.txt,**/*.md,**/*.txt';
  const DEFAULT_EXCLUDE = '.obsidian/**,.git/**,private/**';

  const STATUS_METRICS = [
    {
      label: 'RAG',
      value: status => status?.enabled ? 'Enabled' : 'Disabled',
      hint: status => status?.unavailable ? 'Restart required' : (status?.enabled ? 'Configured on' : 'Disabled in config'),
      tone: status => status?.unavailable ? 'warn' : (status?.enabled ? 'ok' : 'warn'),
    },
    {
      label: 'Retrieval',
      value: status => _formatRetrievalMode(status?.retrievalMode),
      hint: () => 'Default search mode',
      tone: () => 'neutral',
    },
    {
      label: 'Sources',
      value: status => _formatCount(status?.counts?.sources),
      hint: status => _summaryHint(status?.sourcesSummary, 'source', status?.counts?.sources),
      tone: status => Number(status?.counts?.sources || 0) > 0 ? 'ok' : 'muted',
    },
    {
      label: 'Documents',
      value: status => _formatCount(status?.counts?.documents),
      hint: status => _summaryHint(status?.documentsSummary, 'document', status?.counts?.documents),
      tone: status => Number(status?.counts?.documents || 0) > 0 ? 'ok' : 'muted',
    },
    {
      label: 'Chunks',
      value: status => _formatCount(status?.counts?.chunks),
      hint: () => 'Indexed chunks',
      tone: status => Number(status?.counts?.chunks || 0) > 0 ? 'ok' : 'muted',
    },
    {
      label: 'Vector index',
      value: status => _formatIndexStatus(status?.vector),
      hint: status => _vectorHint(status),
      tone: status => status?.vector?.available ? 'ok' : 'warn',
    },
    {
      label: 'Ingestion',
      value: status => Number(status?.ingestion?.activeJobs || 0) > 0 ? 'Indexing' : 'Idle',
      hint: status => _ingestionHint(status),
      tone: status => Number(status?.ingestion?.activeJobs || 0) > 0 ? 'warn' : 'ok',
    },
  ];

  function render(el) {
    _el = el;
    _rpc = App.getRpc();
    if (_stateUnsub) _stateUnsub();
    _stateUnsub = _rpc.on('_state', (state) => {
      if (!_el) return;
      if (state === 'connected') _load();
      else if (!_status) _renderConnecting(state);
    });
    _el.innerHTML = `
      <div class="view-stack rag-view">
        <header class="view-header rag-header">
          <div>
            <h2>RAG</h2>
          </div>
          <div class="toolbar">
            <button class="btn btn--ghost" id="rag-refresh">${icons.refresh()}<span>Refresh</span></button>
          </div>
        </header>

        <section class="stat-row" id="rag-stats"></section>
        <section id="rag-job-panel" class="rag-job-host" aria-live="polite"></section>

        <div class="rag-top-grid">
          <section class="panel rag-panel rag-source-panel rag-panel--primary">
            <div class="panel__header">
              <h3>Add Source</h3>
            </div>
            <div class="rag-source-mode" role="tablist" aria-label="RAG source input type">
              <button type="button" class="rag-source-mode__btn is-active" data-source-mode="upload" aria-pressed="true">Upload ZIP</button>
              <button type="button" class="rag-source-mode__btn" data-source-mode="server" aria-pressed="false">Server path</button>
            </div>
            <div id="rag-upload-source-panel" class="rag-source-upload-panel" data-source-panel="upload">
              <input id="rag-upload-file" type="file" accept=".zip,application/zip" hidden />
              <button type="button" id="rag-upload-dropzone" class="rag-upload-dropzone">
                <span class="rag-upload-dropzone__icon">${icons.download ? icons.download() : icons.plus()}</span>
                <span>
                  <strong>Choose or drop a ZIP file</strong>
                  <small>Markdown and text files import into managed RAG storage.</small>
                </span>
              </button>
              <div id="rag-upload-file-summary" class="rag-upload-summary" aria-live="polite"></div>
            </div>
            <div id="rag-server-source-panel" class="rag-server-source-panel" data-source-panel="server" hidden>
              <div class="form-grid rag-source-form">
                <label class="rag-field-wide">Path<input id="rag-add-path" type="text" placeholder="/path/to/docs" /></label>
                <label>Include<input id="rag-add-include" type="text" value="${DEFAULT_INCLUDE}" /></label>
                <label>Exclude<input id="rag-add-exclude" type="text" value="${DEFAULT_EXCLUDE}" /></label>
              </div>
            </div>
            <div class="rag-source-summary" id="rag-source-summary" aria-live="polite"></div>
            <details class="rag-source-options">
              <summary>Options</summary>
              <div class="form-grid rag-source-form rag-source-form--meta">
                <label>Label<input id="rag-add-name" type="text" placeholder="Auto" /></label>
                <label>Group<input id="rag-add-collection" type="text" value="default" /></label>
              </div>
            </details>
            <div class="toolbar rag-source-actions">
              <button class="btn btn--ghost" id="rag-add">${icons.plus()}<span id="rag-add-label">Import</span></button>
              <button class="btn" id="rag-add-index">${icons.refresh()}<span id="rag-add-index-label">Import + Sync</span></button>
            </div>
          </section>

          <section class="panel rag-panel rag-settings-panel rag-panel--compact">
            <div class="panel__header">
              <h3>Settings</h3>
              <button class="btn btn--ghost" id="rag-settings-save" disabled>${icons.check ? icons.check() : ''}<span>Save</span></button>
            </div>
            <div id="rag-settings"></div>
          </section>
        </div>

        <section class="panel rag-panel rag-sources-panel">
          <div class="panel__header"><h3>Sources</h3></div>
          <div id="rag-sources"></div>
        </section>

        <section class="panel rag-panel rag-search-panel">
          <div class="panel__header"><h3>Search Preview</h3></div>
          <div class="toolbar rag-searchbar">
            <input id="rag-query" type="search" placeholder="Search indexed documents" />
            <select id="rag-mode">
              <option value="hybrid">hybrid</option>
              <option value="fts">fts</option>
              <option value="vector_only">vector_only</option>
            </select>
            <button class="btn" id="rag-search">${icons.search()}<span>Search</span></button>
          </div>
          <div id="rag-results"></div>
        </section>
    </div>`;
    _bind();
    _renderUploadFile();
    _renderSourceSummary();
    _load();
  }

  function destroy() {
    if (_stateUnsub) {
      _stateUnsub();
      _stateUnsub = null;
    }
    _stopBusyTimer();
    _el = null;
    _rpc = null;
    _configData = null;
    _selectedUploadFile = null;
    _expandedResults = {};
  }

  function _bind() {
    _el.querySelector('#rag-refresh')?.addEventListener('click', _load);
    _el.querySelector('#rag-settings-save')?.addEventListener('click', _saveSettings);
    _el.querySelector('#rag-add')?.addEventListener('click', () => _add(false));
    _el.querySelector('#rag-add-index')?.addEventListener('click', () => _add(true));
    _el.querySelectorAll('[data-source-mode]').forEach(btn => {
      btn.addEventListener('click', () => _setSourceMode(btn.dataset.sourceMode));
    });
    const uploadInput = _el.querySelector('#rag-upload-file');
    const dropzone = _el.querySelector('#rag-upload-dropzone');
    dropzone?.addEventListener('click', () => uploadInput?.click());
    dropzone?.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('is-dragover');
    });
    dropzone?.addEventListener('dragleave', (e) => {
      if (!dropzone.contains(e.relatedTarget)) dropzone.classList.remove('is-dragover');
    });
    dropzone?.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('is-dragover');
      const files = Array.from(e.dataTransfer?.files || []);
      _setUploadFile(files.find(file => file.name.toLowerCase().endsWith('.zip')) || files[0]);
    });
    uploadInput?.addEventListener('change', (e) => {
      _setUploadFile(e.currentTarget.files?.[0] || null);
    });
    _el.querySelector('#rag-add-path')?.addEventListener('input', _renderSourceSummary);
    _el.querySelector('#rag-add-name')?.addEventListener('input', _renderSourceSummary);
    _el.querySelector('#rag-add-collection')?.addEventListener('input', _renderSourceSummary);
    _el.querySelector('#rag-search')?.addEventListener('click', _search);
    _el.querySelector('#rag-query')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') _search();
    });
    _el.querySelector('#rag-mode')?.addEventListener('change', (e) => {
      e.currentTarget.dataset.touched = 'true';
    });
  }

  function _selectedSourceMode() {
    return _el.querySelector('[data-source-mode].is-active')?.dataset.sourceMode || 'upload';
  }

  function _setSourceMode(mode) {
    const selected = mode === 'server' ? 'server' : 'upload';
    _el.querySelectorAll('[data-source-mode]').forEach(btn => {
      const active = btn.dataset.sourceMode === selected;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    _el.querySelectorAll('[data-source-panel]').forEach(panel => {
      panel.hidden = panel.dataset.sourcePanel !== selected;
    });
    const addLabel = _el.querySelector('#rag-add-label');
    const addIndexLabel = _el.querySelector('#rag-add-index-label');
    if (addLabel) addLabel.textContent = selected === 'upload' ? 'Import' : 'Add';
    if (addIndexLabel) addIndexLabel.textContent = selected === 'upload' ? 'Import + Sync' : 'Add + Sync';
    _renderSourceSummary();
  }

  function _setUploadFile(file) {
    _selectedUploadFile = file || null;
    _renderUploadFile();
    _renderSourceSummary();
    if (file && !file.name.toLowerCase().endsWith('.zip')) {
      UI.toast('RAG import only accepts .zip files.', 'warn');
    }
  }

  function _renderUploadFile() {
    const host = _el?.querySelector('#rag-upload-file-summary');
    if (!host) return;
    if (!_selectedUploadFile) {
      host.innerHTML = '<span class="rag-upload-empty">No file selected.</span>';
      return;
    }
    const valid = _selectedUploadFile.name.toLowerCase().endsWith('.zip');
    host.innerHTML = `
      <div class="rag-upload-file ${valid ? '' : 'is-invalid'}">
        <div>
          <strong>${_escape(_selectedUploadFile.name)}</strong>
          <small>${_escape(_formatBytes(_selectedUploadFile.size || 0))}</small>
        </div>
        <button type="button" class="btn btn--ghost" id="rag-upload-clear">${icons.x()}<span>Clear</span></button>
      </div>`;
    host.querySelector('#rag-upload-clear')?.addEventListener('click', () => {
      _selectedUploadFile = null;
      const input = _el.querySelector('#rag-upload-file');
      if (input) input.value = '';
      _renderUploadFile();
      _renderSourceSummary();
    });
  }

  function _renderSourceSummary() {
    const host = _el?.querySelector('#rag-source-summary');
    if (!host) return;
    const label = _sourceLabelValue() || 'Auto label';
    const group = _sourceGroupValue();
    const mode = _selectedSourceMode() === 'server' ? 'Server path' : 'ZIP upload';
    host.innerHTML = `
      <div>
        <strong>${_escape(label)}</strong>
        <small>${_escape(mode)} · ${_escape(group)}</small>
      </div>`;
  }

  function _sourceLabelValue() {
    const manual = _el?.querySelector('#rag-add-name')?.value.trim();
    return manual || _autoSourceLabel();
  }

  function _sourceGroupValue() {
    return _el?.querySelector('#rag-add-collection')?.value.trim() || 'default';
  }

  function _autoSourceLabel() {
    if (_selectedSourceMode() === 'upload') {
      return _selectedUploadFile?.name?.replace(/\.zip$/i, '').trim() || '';
    }
    const rawPath = _el?.querySelector('#rag-add-path')?.value.trim() || '';
    const parts = rawPath.replace(/\/+$/, '').split('/').filter(Boolean);
    return parts[parts.length - 1] || rawPath;
  }

  async function _load() {
    if (!_rpc) return;
    try {
      await _ensureConnected();
      if (!_el) return;
      _configData = await _rpc.call('config.get', {});
      try {
        _status = await _rpc.call('rag.status', {});
      } catch (err) {
        _status = _statusFromConfig(err);
      }
      if (_status.enabled && !_status.unavailable) {
        const payload = await _rpc.call('rag.list', { kind: 'sources' });
        _sources = payload.items || [];
      } else {
        _sources = [];
      }
      _render();
    } catch (err) {
      _el.querySelector('#rag-stats').innerHTML = `<div class="card">RAG unavailable: ${_escape(err.message || String(err))}</div>`;
    }
  }

  async function _add(index) {
    if (_selectedSourceMode() === 'upload') {
      await _importZip(index);
      return;
    }
    await _addServerSource(index);
  }

  async function _addServerSource(index) {
    try {
      await _ensureConnected();
      const path = _el.querySelector('#rag-add-path').value.trim();
      if (!path) return;
      const include = _splitGlobs(_el.querySelector('#rag-add-include').value);
      const exclude = _splitGlobs(_el.querySelector('#rag-add-exclude').value);
      if (index) _startBusy('Add + Sync', path);
      const payload = await _rpc.call('rag.add', {
        path,
        name: _sourceLabelValue() || null,
        collectionId: _sourceGroupValue(),
        include,
        exclude,
        index,
      });
      if (index) _finishBusy('Add + Sync', payload);
      await _load();
    } catch (err) {
      _failBusy(err);
    }
  }

  async function _importZip(index) {
    try {
      await _ensureConnected();
      if (!_selectedUploadFile) {
        UI.toast('Choose a .zip file first.', 'warn');
        return;
      }
      if (!_selectedUploadFile.name.toLowerCase().endsWith('.zip')) {
        UI.toast('RAG import only accepts .zip files.', 'warn');
        return;
      }
      const action = index ? 'Import + Sync' : 'Import';
      _startBusy(action, _selectedUploadFile.name);
      const form = new FormData();
      form.append('file', _selectedUploadFile, _selectedUploadFile.name);
      form.append('collectionId', _sourceGroupValue());
      form.append('name', _sourceLabelValue() || _selectedUploadFile.name.replace(/\.zip$/i, ''));
      form.append('index', index ? 'true' : 'false');
      const response = await fetch('/api/v1/rag/imports', {
        method: 'POST',
        body: form,
        headers: _authHeaders(),
        credentials: 'same-origin',
      });
      const payload = await _readJsonResponse(response);
      if (!response.ok) {
        throw new Error(payload.error || `Upload failed with HTTP ${response.status}`);
      }
      _selectedUploadFile = null;
      _renderUploadFile();
      _finishBusy(action, payload);
      await _load();
    } catch (err) {
      _failBusy(err);
    }
  }

  async function _sync(sourceId, force) {
    try {
      await _ensureConnected();
      _startBusy(force ? 'Reindex' : 'Sync', sourceId);
      const payload = await _rpc.call(force ? 'rag.reindex' : 'rag.sync', { sourceId });
      _finishBusy(force ? 'Reindex' : 'Sync', payload);
      await _load();
    } catch (err) {
      _failBusy(err);
    }
  }

  async function _search() {
    await _ensureConnected();
    const query = _el.querySelector('#rag-query').value.trim();
    if (!query) return;
    const payload = await _rpc.call('rag.search', {
      query,
      mode: _el.querySelector('#rag-mode').value,
      limit: 5,
    });
    _searchPayload = payload;
    _results = payload.results || [];
    _expandedResults = {};
    _renderResults();
  }

  async function _showChunk(chunkId) {
    if (!chunkId) return;
    if (_expandedResults[chunkId]) {
      const next = { ..._expandedResults };
      delete next[chunkId];
      _expandedResults = next;
      _renderResults();
      return;
    }
    await _ensureConnected();
    const payload = await _rpc.call('rag.show', { chunkId, maxChars: 6000 });
    _expandedResults = { ..._expandedResults, [chunkId]: payload };
    _renderResults();
  }

  async function _setSourceEnabled(sourceId, enabled) {
    if (!sourceId) return;
    try {
      await _ensureConnected();
      await _rpc.call(enabled ? 'rag.enable_source' : 'rag.disable_source', { sourceId });
      await _load();
    } catch (err) {
      UI.toast(err?.message || String(err), 'err');
    }
  }

  async function _removeSource(sourceId) {
    if (!sourceId) return;
    const ok = await UI.confirm({
      title: 'Remove RAG source',
      message: 'Remove this source and delete its indexed chunks from RAG?',
      confirmLabel: 'Remove',
      danger: true,
    });
    if (!ok) return;
    try {
      await _ensureConnected();
      await _rpc.call('rag.remove_source', { sourceId, deleteIndex: true });
      _searchPayload = null;
      _results = [];
      _expandedResults = {};
      await _load();
    } catch (err) {
      UI.toast(err?.message || String(err), 'err');
    }
  }

  async function _ensureConnected() {
    if (!_rpc) throw new Error('Not connected');
    if (_rpc.state === 'connected') return;
    _renderConnecting(_rpc.state);
    await Promise.race([
      _rpc.waitForConnection(),
      new Promise((_, reject) => setTimeout(() => reject(new Error('Not connected')), 5000)),
    ]);
  }

  function _renderConnecting(state) {
    if (!_el) return;
    const host = _el.querySelector('#rag-stats');
    if (host) {
      host.innerHTML = `<div class="card">Connecting to gateway (${_escape(state || 'disconnected')})...</div>`;
    }
  }

  function _render() {
    _renderStats();
    _renderSettings();
    _renderJobPanel();
    _renderSources();
    _renderResults();
    _syncBusyControls();
  }

  function _renderStats() {
    _el.querySelector('#rag-stats').innerHTML = STATUS_METRICS
      .map(metric => _statusCard(metric, _status))
      .join('');
  }

  function _renderSources() {
    const host = _el.querySelector('#rag-sources');
    if (!_sources.length) {
      host.innerHTML = '<div class="empty">No RAG sources.</div>';
      return;
    }
    host.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Source</th><th>Status</th><th>Path</th><th>Last Sync</th><th></th></tr></thead>
        <tbody>${_sources.map(s => `
          <tr>
            <td class="rag-source-name-cell" title="${_escape(s.sourceId)}">
              <strong>${_escape(s.name || s.sourceId)}</strong>
              <small>${_escape(s.sourceId)}</small>
            </td>
            <td class="rag-source-status-cell">${_sourceStatusMarkup(s)}</td>
            <td class="rag-source-path-cell" title="${_escape(s.path || '')}">${_escape(s.path || '')}</td>
            <td class="rag-source-sync-cell">${s.lastScanFinishedAt ? new Date(s.lastScanFinishedAt * 1000).toLocaleString() : '-'}</td>
            <td class="rag-source-actions-cell">
              <div class="rag-source-actions-cell__inner">
                <button class="btn btn--ghost" data-sync="${_escape(s.sourceId)}" title="Sync">${icons.refresh()}</button>
                <button class="btn btn--ghost" data-reindex="${_escape(s.sourceId)}" title="Reindex">${icons.regenerate ? icons.regenerate() : icons.refresh()}</button>
                ${s.enabled === false || s.status === 'disabled'
                  ? `<button class="btn btn--ghost" data-enable="${_escape(s.sourceId)}">Enable</button>`
                  : `<button class="btn btn--ghost" data-disable="${_escape(s.sourceId)}">Disable</button>`}
                <button class="btn btn--ghost" data-remove="${_escape(s.sourceId)}">Remove</button>
              </div>
            </td>
          </tr>`).join('')}</tbody>
      </table>`;
    host.querySelectorAll('[data-sync]').forEach(btn => {
      btn.addEventListener('click', () => _sync(btn.dataset.sync, false));
    });
    host.querySelectorAll('[data-reindex]').forEach(btn => {
      btn.addEventListener('click', () => _sync(btn.dataset.reindex, true));
    });
    host.querySelectorAll('[data-enable]').forEach(btn => {
      btn.addEventListener('click', () => _setSourceEnabled(btn.dataset.enable, true));
    });
    host.querySelectorAll('[data-disable]').forEach(btn => {
      btn.addEventListener('click', () => _setSourceEnabled(btn.dataset.disable, false));
    });
    host.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', () => _removeSource(btn.dataset.remove));
    });
  }

  function _renderSettings() {
    const host = _el.querySelector('#rag-settings');
    if (!host) return;
    const rag = _ragConfig();
    const enabled = Boolean(rag.enabled ?? _status?.enabled);
    const mode = _normalizeMode(rag.retrieval_mode || _status?.retrievalMode);
    host.innerHTML = `
      <div class="rag-settings-grid">
        <div class="rag-setting-row">
          <label class="rag-switch">
            <input id="rag-setting-enabled" type="checkbox" ${enabled ? 'checked' : ''} />
            <span class="rag-switch__track" aria-hidden="true"></span>
            <span class="rag-switch__text">RAG enabled</span>
          </label>
        </div>
        <div class="rag-setting-row rag-setting-row--stacked rag-mode-setting">
          <span class="rag-control-label">Default retrieval</span>
          <div class="rag-segmented" role="group" aria-label="Default retrieval mode">
            ${_modeButton('hybrid', 'Hybrid', mode)}
            ${_modeButton('fts', 'Text', mode)}
            ${_modeButton('vector_only', 'Vector', mode)}
          </div>
        </div>
      </div>
      ${_settingsStatusMarkup()}`;
    const searchMode = _el.querySelector('#rag-mode');
    if (searchMode && !searchMode.dataset.touched) {
      searchMode.value = mode;
    }
    _bindSettings();
    _syncSettingsDirty();
  }

  function _modeButton(value, label, current) {
    const active = value === current;
    return `<button type="button" class="rag-segmented__btn ${active ? 'is-active' : ''}" data-rag-mode-option="${_escape(value)}" aria-pressed="${active ? 'true' : 'false'}">${_escape(label)}</button>`;
  }

  function _sourceStatusMarkup(source) {
    const status = source?.status || (source?.enabled === false ? 'disabled' : '');
    const tone = status === 'active' ? 'chip-ok' : status ? 'chip-warn' : '';
    return `<span class="chip ${tone}">${_escape(status || '-')}</span>`;
  }

  function _settingsStatusMarkup() {
    if (_settingsNotice) {
      return `<div class="rag-settings-notice rag-settings-notice--${_escape(_settingsNotice.type || 'info')}">${_escape(_settingsNotice.text || '')}</div>`;
    }
    if (_status?.unavailable) {
      return `<div class="rag-settings-notice rag-settings-notice--warn">${_escape(_status.statusError || 'RAG manager is not available')}</div>`;
    }
    return '';
  }

  function _bindSettings() {
    _el.querySelector('#rag-setting-enabled')?.addEventListener('change', _syncSettingsDirty);
    _el.querySelectorAll('[data-rag-mode-option]').forEach(btn => {
      btn.addEventListener('click', () => {
        _el.querySelectorAll('[data-rag-mode-option]').forEach(other => {
          const active = other === btn;
          other.classList.toggle('is-active', active);
          other.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        _syncSettingsDirty();
      });
    });
  }

  function _syncSettingsDirty() {
    const button = _el.querySelector('#rag-settings-save');
    if (!button) return;
    const rag = _ragConfig();
    const enabled = Boolean(_el.querySelector('#rag-setting-enabled')?.checked);
    const mode = _selectedSettingsMode();
    const dirty = enabled !== Boolean(rag.enabled) || mode !== _normalizeMode(rag.retrieval_mode);
    button.disabled = _settingsSaving || !dirty;
  }

  async function _saveSettings() {
    const rag = _ragConfig();
    const enabled = Boolean(_el.querySelector('#rag-setting-enabled')?.checked);
    const mode = _selectedSettingsMode();
    const patches = {};
    if (enabled !== Boolean(rag.enabled)) patches['rag.enabled'] = enabled;
    if (mode !== _normalizeMode(rag.retrieval_mode)) patches['rag.retrieval_mode'] = mode;
    if (!Object.keys(patches).length) return;
    _settingsSaving = true;
    _syncSettingsDirty();
    try {
      const result = await _rpc.call('config.patch', { patches });
      _settingsNotice = result.restartRequired
        ? { type: 'warn', text: 'Saved. Restart gateway to apply runtime changes.' }
        : { type: 'ok', text: 'Saved.' };
      UI.toast(_settingsNotice.text, result.restartRequired ? 'info' : 'ok');
      await _load();
    } catch (err) {
      _settingsNotice = { type: 'err', text: err?.message || String(err) };
      _renderSettings();
    } finally {
      _settingsSaving = false;
      _syncSettingsDirty();
    }
  }

  function _selectedSettingsMode() {
    const active = _el.querySelector('[data-rag-mode-option].is-active');
    return _normalizeMode(active?.dataset.ragModeOption);
  }

  function _renderResults() {
    const host = _el.querySelector('#rag-results');
    if (!host) return;
    if (!_results.length) {
      host.innerHTML = _searchPayload
        ? '<div class="state"><div class="state-title">No chunk matches</div></div>'
        : '<div class="empty">No search results.</div>';
      return;
    }
    host.innerHTML = `
      <div class="rag-results-summary">
        <div>
          <strong>${_escape(String(_results.length))} chunk matches</strong>
          <small>${_escape(_searchMeta())}</small>
        </div>
        ${_searchPayload?.fallback ? `<span class="chip chip-warn">${_escape(_fallbackLabel(_searchPayload.fallback))}</span>` : ''}
      </div>
      ${_renderInspectPanel()}
      <div class="rag-results-list">
        ${_results.map((result, index) => _renderResultCard(result, index)).join('')}
      </div>`;
    host.querySelectorAll('[data-rag-show-chunk]').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          btn.disabled = true;
          await _showChunk(btn.dataset.ragShowChunk);
        } catch (err) {
          UI.toast(err?.message || String(err), 'err');
        } finally {
          btn.disabled = false;
        }
      });
    });
  }

  function _renderResultCard(result, index) {
    const citation = result.citation || {};
    const lineRange = _lineRange(citation);
    const title = result.title || _basename(result.path);
    const preview = result.contentPreview || result.snippet || result.content || '';
    const breakdown = result.scoreBreakdown || result.metadata?.scoreBreakdown || {};
    const expanded = result.chunkId ? _expandedResults[result.chunkId] : null;
    const ftsScore = result.ftsScore ?? result.textScore;
    return `
      <article class="rag-result">
        <div class="rag-result__rank">#${index + 1}</div>
        <div class="rag-result__body">
          <div class="rag-result__topline">
            <span class="chip chip-accent">chunk</span>
            <span class="chip">${_escape(result.retrievalMode || _searchPayload?.effectiveMode || '')}</span>
            ${result.sourceStatus ? `<span class="chip ${result.sourceStatus === 'active' ? 'chip-ok' : 'chip-warn'}">${_escape(result.sourceStatus)}</span>` : ''}
            ${result.untrustedEvidence ? '<span class="chip chip-warn">untrusted evidence</span>' : ''}
            <span class="rag-result__score">${_escape(_scoreLabel(result))}</span>
          </div>
          <h4>${_escape(title || 'Untitled document')}</h4>
          <div class="rag-result__path">${_escape(result.path || '')}</div>
          <p class="rag-result__snippet rag-result__preview">${_escape(preview)}</p>
          ${_renderScoreBreakdown(breakdown)}
          <div class="rag-result__meta">
            ${_metaItem('Citation', citation.label || '')}
            ${_metaItem('Lines', lineRange)}
            ${_metaItem('Collection', result.collectionId)}
            ${_metaItem('Source', result.sourceId)}
            ${_metaItem('Chunk', _shortId(result.chunkId))}
            ${result.vectorScore !== null && result.vectorScore !== undefined ? _metaItem('Vector', _fixed(result.vectorScore)) : ''}
            ${ftsScore !== null && ftsScore !== undefined ? _metaItem('FTS', _fixed(ftsScore)) : ''}
          </div>
          <div class="rag-result__actions">
            <button type="button" class="btn btn--ghost" data-rag-show-chunk="${_escape(result.chunkId || '')}">${expanded ? 'Hide chunk' : 'Show chunk'}</button>
          </div>
          ${expanded ? _renderExpandedChunk(expanded) : ''}
        </div>
      </article>`;
  }

  function _renderInspectPanel() {
    if (!_searchPayload) return '';
    const diagnostics = _searchPayload.diagnostics || {};
    const scoring = diagnostics.scoring || {};
    const candidates = diagnostics.candidates || {};
    const budget = _searchPayload.payloadBudget || {};
    return `
      <div class="rag-inspect">
        <div>
          <strong>Inspect</strong>
          <small>${_escape(_inspectMeta(scoring, candidates, budget))}</small>
        </div>
        ${budget.maxChars ? `<span class="chip ${budget.truncated ? 'chip-warn' : ''}">${_escape(`${_formatCount(budget.actualChars)} / ${_formatCount(budget.maxChars)} chars`)}</span>` : ''}
        ${scoring.textWeight !== undefined ? `<span class="chip">${_escape(`textWeight ${_fixed(scoring.textWeight)}`)}</span>` : ''}
        ${scoring.vectorWeight !== undefined ? `<span class="chip">${_escape(`vectorWeight ${_fixed(scoring.vectorWeight)}`)}</span>` : ''}
      </div>`;
  }

  function _renderScoreBreakdown(breakdown) {
    if (!breakdown || (!('textWeight' in breakdown) && !('vectorWeight' in breakdown))) return '';
    return `
      <div class="rag-score-breakdown">
        ${_metaItem('Formula', breakdown.formula)}
        ${breakdown.textWeight !== undefined ? _metaItem('FTS weight', _fixed(breakdown.textWeight)) : ''}
        ${breakdown.ftsContribution !== undefined ? _metaItem('FTS contribution', _fixed(breakdown.ftsContribution)) : ''}
        ${breakdown.vectorWeight !== undefined ? _metaItem('Vector weight', _fixed(breakdown.vectorWeight)) : ''}
        ${breakdown.vectorContribution !== undefined ? _metaItem('Vector contribution', _fixed(breakdown.vectorContribution)) : ''}
      </div>`;
  }

  function _renderExpandedChunk(payload) {
    const citation = payload.citation || {};
    return `
      <div class="rag-expanded-chunk">
        <div class="rag-expanded-chunk__header">
          <strong>Chunk detail</strong>
          ${payload.truncated ? '<span class="chip chip-warn">truncated</span>' : ''}
          ${citation.label ? `<span class="chip">${_escape(citation.label)}</span>` : ''}
        </div>
        <pre>${_escape(payload.content || '')}</pre>
      </div>`;
  }

  function _metaItem(label, value) {
    if (value === null || value === undefined || value === '') return '';
    return `<span><strong>${_escape(label)}</strong>${_escape(String(value))}</span>`;
  }

  function _searchMeta() {
    const query = _searchPayload?.query || '';
    const mode = _searchPayload?.effectiveMode || _searchPayload?.mode || '';
    const ms = _searchPayload?.diagnostics?.durationMs;
    return [query, mode, ms !== undefined ? `${ms} ms` : ''].filter(Boolean).join(' · ');
  }

  function _inspectMeta(scoring, candidates, budget) {
    const parts = [];
    if (scoring.strategy) parts.push(scoring.strategy);
    if (candidates.fts !== undefined) parts.push(`fts ${_formatCount(candidates.fts)}`);
    if (candidates.vector !== undefined) parts.push(`vector ${_formatCount(candidates.vector)}`);
    if (candidates.merged !== undefined) parts.push(`merged ${_formatCount(candidates.merged)}`);
    if (budget.truncated) parts.push('truncated');
    return parts.join(' · ') || 'Search diagnostics';
  }

  function _fallbackLabel(fallback) {
    return `${fallback.from || 'mode'} -> ${fallback.to || 'fallback'}`;
  }

  function _lineRange(citation) {
    if (citation.page !== null && citation.page !== undefined) return `p. ${citation.page}`;
    if (citation.lineStart && citation.lineEnd) return `L${citation.lineStart}-L${citation.lineEnd}`;
    if (citation.lineStart) return `L${citation.lineStart}`;
    return '';
  }

  function _scoreLabel(result) {
    return `score ${_fixed(result.score || 0)}`;
  }

  function _fixed(value) {
    return Number(value || 0).toFixed(3);
  }

  function _shortId(value) {
    const raw = String(value || '');
    if (!raw) return '';
    return raw.length > 14 ? `${raw.slice(0, 10)}...` : raw;
  }

  function _basename(path) {
    const raw = String(path || '');
    return raw.split('/').filter(Boolean).pop() || raw;
  }

  function _startBusy(action, target) {
    _busy = { action, target, startedAt: Date.now() };
    _lastJobSummary = null;
    _renderJobPanel();
    _syncBusyControls();
    _stopBusyTimer();
    _busyTimer = setInterval(_renderJobPanel, 1000);
  }

  function _finishBusy(action, payload) {
    const elapsedMs = _busy ? Date.now() - _busy.startedAt : 0;
    _stopBusyTimer();
    const jobs = _extractJobs(payload);
    _lastJobSummary = { action, ok: true, elapsedMs, jobs };
    _busy = null;
    _renderJobPanel();
    _syncBusyControls();
  }

  function _failBusy(err) {
    const elapsedMs = _busy ? Date.now() - _busy.startedAt : 0;
    _stopBusyTimer();
    _lastJobSummary = {
      action: _busy?.action || 'RAG job',
      ok: false,
      elapsedMs,
      error: err?.message || String(err),
      jobs: [],
    };
    _busy = null;
    _renderJobPanel();
    _syncBusyControls();
  }

  function _stopBusyTimer() {
    if (_busyTimer !== null) {
      clearInterval(_busyTimer);
      _busyTimer = null;
    }
  }

  function _renderJobPanel() {
    const host = _el?.querySelector('#rag-job-panel');
    if (!host) return;
    if (_busy) {
      const elapsed = _formatDuration(Date.now() - _busy.startedAt);
      host.innerHTML = `
        <div class="rag-job rag-job--running" role="status" aria-busy="true">
          <div class="rag-job__header">
            <span class="spinner" aria-hidden="true"></span>
            <div>
              <strong>${_escape(_busy.action)} running</strong>
              <small>${_escape(_busy.target || '')}</small>
            </div>
            <span class="rag-job__time">${_escape(elapsed)}</span>
          </div>
          <div class="rag-progress" aria-hidden="true"><span></span></div>
          <div class="rag-job__hint">Scanning, chunking, and embedding may take a few minutes.</div>
        </div>`;
      return;
    }
    if (!_lastJobSummary) {
      host.innerHTML = '';
      return;
    }
    const summary = _summarizeJobs(_lastJobSummary.jobs);
    const statusClass = _lastJobSummary.ok ? 'rag-job--done' : 'rag-job--failed';
    const title = _lastJobSummary.ok ? `${_lastJobSummary.action} completed` : `${_lastJobSummary.action} failed`;
    host.innerHTML = `
      <div class="rag-job ${statusClass}" role="${_lastJobSummary.ok ? 'note' : 'alert'}">
        <div class="rag-job__header">
          <span class="dot ${_lastJobSummary.ok ? 'ok' : 'err'}" aria-hidden="true"></span>
          <div>
            <strong>${_escape(title)}</strong>
            <small>${_escape(_formatDuration(_lastJobSummary.elapsedMs))}</small>
          </div>
        </div>
        ${_lastJobSummary.error ? `<div class="rag-job__error">${_escape(_lastJobSummary.error)}</div>` : ''}
        ${_lastJobSummary.ok ? _renderJobMetrics(summary) : ''}
      </div>`;
  }

  function _renderJobMetrics(summary) {
    return `
      <div class="rag-job__metrics">
        ${_metric('files seen', summary.filesSeen)}
        ${_metric('indexed', summary.filesIndexed)}
        ${_metric('skipped', summary.filesSkipped)}
        ${_metric('failed', summary.filesFailed)}
        ${_metric('chunks', summary.chunksWritten)}
        ${_metric('embeddings', summary.embeddingsWritten)}
      </div>`;
  }

  function _metric(label, value) {
    return `<span><strong>${_escape(String(value || 0))}</strong>${_escape(label)}</span>`;
  }

  function _extractJobs(payload) {
    if (!payload) return [];
    if (Array.isArray(payload.jobs)) return payload.jobs;
    if (payload.job) return [payload.job];
    return [];
  }

  function _summarizeJobs(jobs) {
    return (jobs || []).reduce((acc, job) => {
      acc.filesSeen += Number(job.filesSeen || 0);
      acc.filesIndexed += Number(job.filesIndexed || 0);
      acc.filesSkipped += Number(job.filesSkipped || 0);
      acc.filesFailed += Number(job.filesFailed || 0);
      acc.chunksWritten += Number(job.chunksWritten || 0);
      acc.embeddingsWritten += Number(job.embeddingsWritten || 0);
      return acc;
    }, {
      filesSeen: 0,
      filesIndexed: 0,
      filesSkipped: 0,
      filesFailed: 0,
      chunksWritten: 0,
      embeddingsWritten: 0,
    });
  }

  function _syncBusyControls() {
    if (!_el) return;
    const busy = !!_busy;
    _el.querySelectorAll('#rag-refresh, #rag-add, #rag-add-index, #rag-search, #rag-upload-dropzone, [data-source-mode], [data-sync], [data-reindex]').forEach(btn => {
      btn.disabled = busy;
    });
  }

  function _authHeaders() {
    const headers = {};
    const token = (App.getAuthToken && App.getAuthToken()) || '';
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  async function _readJsonResponse(response) {
    const text = await response.text().catch(() => '');
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch {
      return { error: text };
    }
  }

  function _formatBytes(value) {
    const bytes = Number(value || 0);
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function _formatDuration(ms) {
    const seconds = Math.max(0, Math.floor((ms || 0) / 1000));
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    if (minutes <= 0) return `${rest}s`;
    return `${minutes}m ${String(rest).padStart(2, '0')}s`;
  }

  function _ragConfig() {
    return _configData?.rag || {};
  }

  function _statusFromConfig(err) {
    const rag = _ragConfig();
    const enabled = Boolean(rag.enabled);
    return {
      enabled,
      unavailable: enabled,
      reason: enabled ? 'manager_unavailable' : 'rag_disabled',
      statusError: err?.message || String(err),
      retrievalMode: _normalizeMode(rag.retrieval_mode),
      embedding: {
        enabled: Boolean(rag.embedding && rag.embedding.provider !== 'none'),
        model: rag.embedding?.remote?.model || rag.embedding?.local?.model || 'fts-only',
      },
      vector: { available: false, dimensions: null, indexStatus: 'unavailable' },
      counts: { collections: 0, sources: 0, documents: 0, chunks: 0, errors: 0 },
      sourcesSummary: {},
      documentsSummary: {},
      recentJobs: [],
      ingestion: { activeJobs: 0, isIndexing: false, latestJob: null, summary: {} },
    };
  }

  function _statusCard(metric, status) {
    const tone = metric.tone ? metric.tone(status) : 'neutral';
    const hint = metric.hint ? metric.hint(status) : '';
    return `
      <div class="stat rag-stat rag-stat--${_escape(tone || 'neutral')}">
        <span class="stat-label">${_escape(metric.label)}</span>
        <strong class="stat-value">${_escape(metric.value(status))}</strong>
        ${hint ? `<span class="stat-hint">${_escape(hint)}</span>` : ''}
      </div>`;
  }

  function _formatCount(value) {
    return new Intl.NumberFormat().format(Number(value || 0));
  }

  function _formatRetrievalMode(value) {
    value = _normalizeMode(value);
    return ({
      hybrid: 'Hybrid',
      fts: 'Text',
      vector_only: 'Vector',
    }[value] || '-');
  }

  function _normalizeMode(value) {
    const raw = String(value || 'hybrid').trim();
    if (raw === 'vector') return 'vector_only';
    if (raw === 'text') return 'fts';
    return ['hybrid', 'fts', 'vector_only'].includes(raw) ? raw : 'hybrid';
  }

  function _formatIndexStatus(vector) {
    const raw = vector?.indexStatus || (vector?.available ? 'ready' : 'unavailable');
    return ({
      ready: 'Ready',
      unavailable: 'Unavailable',
      stale: 'Stale',
      rebuilding: 'Rebuilding',
    }[raw] || String(raw || '-'));
  }

  function _summaryHint(summary, noun, total) {
    const entries = Object.entries(summary || {})
      .filter(([, value]) => Number(value || 0) > 0)
      .map(([key, value]) => `${_formatCount(value)} ${key}`);
    if (entries.length) return entries.join(' · ');
    if (Number(total || 0) > 0) return `${_formatCount(total)} total`;
    return `No ${noun}s`;
  }

  function _vectorHint(status) {
    const vector = status?.vector || {};
    const embedding = status?.embedding || {};
    if (!vector.available) {
      return embedding.enabled ? 'Embedding configured, index unavailable' : 'Embedding disabled';
    }
    const dims = vector.dimensions ? `${_formatCount(vector.dimensions)} dims` : '';
    const model = embedding.model && embedding.model !== 'fts-only' ? embedding.model : '';
    return [dims, model].filter(Boolean).join(' · ') || 'Vector search ready';
  }

  function _ingestionHint(status) {
    const ingestion = status?.ingestion || {};
    const latestJob = ingestion.latestJob;
    if (Number(ingestion.activeJobs || 0) > 0) {
      return `${_formatCount(ingestion.activeJobs)} active job`;
    }
    if (!latestJob) return 'No sync jobs yet';
    const duration = latestJob.durationMs !== null && latestJob.durationMs !== undefined
      ? _formatDuration(latestJob.durationMs)
      : '';
    return [latestJob.status || 'unknown', duration].filter(Boolean).join(' · ');
  }

  function _splitGlobs(value) {
    return String(value || '').split(',').map(v => v.trim()).filter(Boolean);
  }

  function _escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
  }

  return { render, destroy };
})();

window.RagView = RagView;
