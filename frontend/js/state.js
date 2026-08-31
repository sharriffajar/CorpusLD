/**
 * Application State & Configuration Management
 */

export const appState = {
  documents: [],
  isIndexed: false,
  selectedDoc: '',
  localModels: ['qwen2.5:3b'],
  settings: {
    provider: 'ollama',
    ollamaModel: 'qwen2.5:3b',
    cloudModel: 'gemini-3.5-flash-lite',
    apiKey: '',
    baseUrl: '',
    parser: 'pypdf',
    llamaparseKey: '',
    unstructuredKey: '',
    graphdbType: 'neo4j',
    neo4jUri: 'bolt://localhost:7687',
    neo4jUser: 'neo4j',
    neo4jPass: '',
    neo4jDb: 'neo4j',
    sparqlUrl: 'http://localhost:3030/dataset/update'
  }
};

export function loadSettingsFromStorage() {
  const savedPrefs = localStorage.getItem('corpusld_preferences');
  if (savedPrefs) {
    try {
      const prefs = JSON.parse(savedPrefs);
      appState.settings.provider = prefs.provider || 'ollama';
      appState.settings.ollamaModel = prefs.ollamaModel || 'qwen2.5:3b';
      appState.settings.cloudModel = prefs.cloudModel || 'gemini-3.5-flash-lite';
      appState.settings.baseUrl = prefs.baseUrl || '';
      appState.settings.parser = prefs.parser || 'pypdf';
      appState.settings.graphdbType = prefs.graphdbType || 'neo4j';
      appState.settings.neo4jUri = prefs.neo4jUri || 'bolt://localhost:7687';
      appState.settings.neo4jUser = prefs.neo4jUser || 'neo4j';
      appState.settings.neo4jDb = prefs.neo4jDb || 'neo4j';
      appState.settings.sparqlUrl = prefs.sparqlUrl || 'http://localhost:3030/dataset/update';
    } catch (e) {
      console.warn('Failed to parse saved preferences:', e);
    }
  }

  const savedSession = sessionStorage.getItem('corpusld_session_keys');
  if (savedSession) {
    try {
      const keys = JSON.parse(savedSession);
      appState.settings.apiKey = keys.apiKey || '';
      appState.settings.llamaparseKey = keys.llamaparseKey || '';
      appState.settings.unstructuredKey = keys.unstructuredKey || '';
      appState.settings.neo4jPass = keys.neo4jPass || '';
    } catch (e) {
      console.warn('Failed to parse session keys:', e);
    }
  }

  if (localStorage.getItem('corpusld_settings')) {
    localStorage.removeItem('corpusld_settings');
  }

  updatePrivacyIndicator();
}

export function saveSettingsToStorage(newSettings) {
  Object.assign(appState.settings, newSettings);

  const generalPrefs = {
    provider: appState.settings.provider,
    ollamaModel: appState.settings.ollamaModel,
    cloudModel: appState.settings.cloudModel,
    baseUrl: appState.settings.baseUrl,
    parser: appState.settings.parser,
    graphdbType: appState.settings.graphdbType,
    neo4jUri: appState.settings.neo4jUri,
    neo4jUser: appState.settings.neo4jUser,
    neo4jDb: appState.settings.neo4jDb,
    sparqlUrl: appState.settings.sparqlUrl
  };
  localStorage.setItem('corpusld_preferences', JSON.stringify(generalPrefs));

  const sensitiveKeys = {
    apiKey: appState.settings.apiKey,
    llamaparseKey: appState.settings.llamaparseKey,
    unstructuredKey: appState.settings.unstructuredKey,
    neo4jPass: appState.settings.neo4jPass
  };
  sessionStorage.setItem('corpusld_session_keys', JSON.stringify(sensitiveKeys));

  updatePrivacyIndicator();
}

export function resetSettingsToDefault() {
  appState.settings = {
    provider: 'ollama',
    ollamaModel: 'qwen2.5:3b',
    cloudModel: 'gemini-3.5-flash-lite',
    apiKey: '',
    baseUrl: '',
    parser: 'pypdf',
    llamaparseKey: '',
    unstructuredKey: '',
    graphdbType: 'neo4j',
    neo4jUri: 'bolt://localhost:7687',
    neo4jUser: 'neo4j',
    neo4jPass: '',
    neo4jDb: 'neo4j',
    sparqlUrl: 'http://localhost:3030/dataset/update'
  };
  localStorage.removeItem('corpusld_preferences');
  sessionStorage.removeItem('corpusld_session_keys');
  updatePrivacyIndicator();
}

export function updatePrivacyIndicator() {
  const privacyBadge = document.getElementById('privacy-badge');
  const privacyBadgeText = document.getElementById('privacy-badge-text');
  if (!privacyBadge || !privacyBadgeText) return;

  const isOffline = appState.settings.provider === 'ollama' && appState.settings.parser === 'pypdf';
  if (isOffline) {
    privacyBadge.className = 'privacy-pill privacy-local';
    privacyBadgeText.textContent = '100% Local Offline Mode';
  } else if (appState.settings.parser === 'hybrid') {
    privacyBadge.className = 'privacy-pill privacy-cloud';
    privacyBadgeText.textContent = `Hybrid Mode (${appState.settings.provider.toUpperCase()} + LlamaParse)`;
  } else {
    privacyBadge.className = 'privacy-pill privacy-cloud';
    privacyBadgeText.textContent = `BYOK Mode (${appState.settings.provider.toUpperCase()})`;
  }
  updateModelStatus('ready');
}

export function updateModelStatus(state, info) {
  const modelStatusPill = document.getElementById('model-status-pill');
  const modelStatusText = document.getElementById('model-status-text');
  if (!modelStatusPill || !modelStatusText) return;

  const provider = appState.settings.provider || 'ollama';
  const activeModelName = provider === 'ollama' ? (appState.settings.ollamaModel || 'qwen2.5:3b') : (appState.settings.cloudModel || 'Cloud');

  if (state === 'running') {
    modelStatusPill.className = 'status-badge badge-warning';
    modelStatusText.textContent = info || `Model: Processing (${activeModelName})...`;
  } else if (state === 'error') {
    modelStatusPill.className = 'status-badge badge-danger';
    modelStatusText.textContent = info || 'Model: Error / Offline';
  } else {
    modelStatusPill.className = 'status-badge badge-success';
    modelStatusText.textContent = `Model: Ready (${activeModelName})`;
  }
}

export function updateIndexStatus(isIndexed) {
  appState.isIndexed = isIndexed;
  const syncStateBadge = document.getElementById('sync-state-badge');
  const btnSyncKb = document.getElementById('btn-sync-kb');
  const btnSyncLabel = document.getElementById('btn-sync-label');
  const chatInput = document.getElementById('chat-input');
  const btnSendChat = document.getElementById('btn-send-chat');

  const hasDocs = appState.documents && appState.documents.length > 0;

  if (!hasDocs) {
    if (syncStateBadge) {
      syncStateBadge.className = 'sync-badge badge-warning';
      syncStateBadge.textContent = 'No Docs';
    }
    if (btnSyncKb) {
      btnSyncKb.className = 'btn btn-sync btn-block';
      btnSyncKb.disabled = true;
    }
    if (btnSyncLabel) btnSyncLabel.textContent = 'Sync Knowledge Base';
    if (chatInput) chatInput.disabled = true;
    if (btnSendChat) btnSendChat.disabled = true;
    return;
  }

  if (isIndexed) {
    if (syncStateBadge) {
      syncStateBadge.className = 'sync-badge badge-success';
      syncStateBadge.textContent = 'Ready';
    }
    if (btnSyncKb) {
      btnSyncKb.className = 'btn btn-sync btn-sync-synced btn-block';
      btnSyncKb.disabled = false;
    }
    if (btnSyncLabel) btnSyncLabel.textContent = 'Knowledge Base Synced (Re-sync)';
    if (chatInput) chatInput.disabled = false;
    if (btnSendChat) btnSendChat.disabled = false;
  } else {
    if (syncStateBadge) {
      syncStateBadge.className = 'sync-badge badge-rose';
      syncStateBadge.textContent = 'Needs Sync';
    }
    if (btnSyncKb) {
      btnSyncKb.className = 'btn btn-sync btn-sync-needed btn-block';
      btnSyncKb.disabled = false;
    }
    if (btnSyncLabel) btnSyncLabel.textContent = 'Sync Knowledge Base';
    if (chatInput) chatInput.disabled = true;
    if (btnSendChat) btnSendChat.disabled = true;
  }
}
