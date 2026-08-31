import { appState, updateIndexStatus } from '../state.js';
import { fetchDocuments, deleteDocument, clearWorkspace, uploadFiles, syncKnowledgeBase, fetchExistingJsonLd, syncGraphdb, getExportUrl } from '../api.js';
import { escapeHtml } from '../utils/dom.js';
import { renderJsonLdData } from '../renderers/jsonldViewer.js';

export async function fetchDocumentsList() {
  const docCountBadge = document.getElementById('doc-count-badge');
  try {
    const data = await fetchDocuments();
    appState.documents = data.documents || [];
    if (docCountBadge) docCountBadge.textContent = appState.documents.length;

    renderSourcesList();
    populateJsonldDropdown();
    populateChatScopeDropdown();

    if (appState.documents.length > 0) {
      const activeDoc = appState.selectedDoc && appState.documents.some(d => d.name === appState.selectedDoc)
        ? appState.selectedDoc
        : appState.documents[0].name;
      selectActiveDocument(activeDoc);
    } else {
      appState.selectedDoc = '';
      const heroTitle = document.getElementById('doc-hero-title');
      const jsonldResultsContainer = document.getElementById('jsonld-results-container');
      const btnRunExtraction = document.getElementById('btn-run-extraction');
      if (btnRunExtraction) btnRunExtraction.disabled = true;
      if (heroTitle) heroTitle.textContent = 'No document selected';
      if (jsonldResultsContainer) jsonldResultsContainer.classList.add('hidden');
    }
  } catch (e) {
    console.error('Failed to fetch documents:', e);
  }
}

export function selectActiveDocument(name) {
  appState.selectedDoc = name;
  const selectJsonldDoc = document.getElementById('select-jsonld-doc');
  const selectChatScope = document.getElementById('select-chat-scope');
  const btnRunExtraction = document.getElementById('btn-run-extraction');

  if (selectJsonldDoc) selectJsonldDoc.value = name;
  if (selectChatScope && !selectChatScope.value) {
    selectChatScope.value = name;
  }
  if (btnRunExtraction) {
    btnRunExtraction.disabled = !name;
  }
  updateChatScopeUI();
  renderSourcesList();
  if (name) {
    checkExistingJsonLd(name);
  }
}

export function updateChatScopeUI() {
  const selectChatScope = document.getElementById('select-chat-scope');
  const chatScopePill = document.getElementById('chat-scope-pill');
  const chatScopePillText = document.getElementById('chat-scope-pill-text');

  const scopeVal = selectChatScope ? selectChatScope.value : '';
  if (scopeVal) {
    if (chatScopePill) chatScopePill.className = 'scope-pill scope-doc';
    if (chatScopePillText) chatScopePillText.textContent = `Doc: ${scopeVal}`;
  } else {
    if (chatScopePill) chatScopePill.className = 'scope-pill scope-all';
    if (chatScopePillText) chatScopePillText.textContent = 'Scope: All Documents';
  }
}

export function renderSourcesList() {
  const sourcesList = document.getElementById('sources-list');
  if (!sourcesList) return;
  sourcesList.innerHTML = '';

  if (appState.documents.length === 0) {
    sourcesList.innerHTML = '<div class="empty-state-card" style="padding: 20px 10px; font-size: 11px; text-align: center; color: var(--text-muted);">No documents uploaded yet.</div>';
    return;
  }

  appState.documents.forEach(doc => {
    const item = document.createElement('div');
    item.className = `source-item ${doc.name === appState.selectedDoc ? 'active' : ''}`;

    const info = document.createElement('div');
    info.className = 'source-info';
    info.innerHTML = `
      <div class="source-name" title="${escapeHtml(doc.name)}">${escapeHtml(doc.name)}</div>
      <div class="source-meta">${doc.pages || '?'} pages &bull; ${(doc.size_bytes / 1024).toFixed(1)} KB</div>
    `;

    const btn = document.createElement('button');
    btn.className = 'source-del-btn';
    btn.title = 'Delete Document';
    btn.innerHTML = '&times;';

    item.addEventListener('click', (e) => {
      if (e.target !== btn) {
        selectActiveDocument(doc.name);
      }
    });

    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (confirm(`Delete document "${doc.name}"?`)) {
        await deleteDoc(doc.name);
      }
    });

    item.appendChild(info);
    item.appendChild(btn);
    sourcesList.appendChild(item);
  });
}

export function populateJsonldDropdown() {
  const selectJsonldDoc = document.getElementById('select-jsonld-doc');
  if (!selectJsonldDoc) return;
  selectJsonldDoc.innerHTML = '';

  if (appState.documents.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '-- No documents uploaded --';
    selectJsonldDoc.appendChild(opt);
    return;
  }

  appState.documents.forEach(doc => {
    const opt = document.createElement('option');
    opt.value = doc.name;
    opt.textContent = doc.name;
    if (doc.name === appState.selectedDoc) opt.selected = true;
    selectJsonldDoc.appendChild(opt);
  });
}

export function populateChatScopeDropdown() {
  const selectChatScope = document.getElementById('select-chat-scope');
  if (!selectChatScope) return;
  const currentVal = selectChatScope.value;
  selectChatScope.innerHTML = '<option value="">Full Corpus (All Documents)</option>';

  appState.documents.forEach(doc => {
    const opt = document.createElement('option');
    opt.value = doc.name;
    opt.textContent = `Document: ${doc.name}`;
    if (doc.name === currentVal) opt.selected = true;
    selectChatScope.appendChild(opt);
  });
  updateChatScopeUI();
}

export async function deleteDoc(name) {
  try {
    await deleteDocument(name);
    if (appState.selectedDoc === name) {
      appState.selectedDoc = '';
    }
    await fetchDocumentsList();
    updateIndexStatus(false);
  } catch (e) {
    alert('Delete failed: ' + e);
  }
}

export async function checkExistingJsonLd(fileName) {
  const jsonldResultsContainer = document.getElementById('jsonld-results-container');
  const btnDownloadExport = document.getElementById('btn-download-export');
  const btnDownloadJsonld = document.getElementById('btn-download-jsonld');
  const selectExportFormat = document.getElementById('select-export-format');
  const btnSyncGraphdb = document.getElementById('btn-sync-graphdb');

  try {
    const data = await fetchExistingJsonLd(fileName);
    renderJsonLdData(data.data);
  } catch (e) {
    if (jsonldResultsContainer) jsonldResultsContainer.classList.add('hidden');
    if (btnDownloadJsonld) btnDownloadJsonld.disabled = true;
    if (selectExportFormat) selectExportFormat.disabled = true;
    if (btnDownloadExport) btnDownloadExport.disabled = true;
    if (btnSyncGraphdb) btnSyncGraphdb.disabled = true;
  }
}

export function triggerDocumentExport() {
  if (!appState.selectedDoc) return;
  const selectExportFormat = document.getElementById('select-export-format');
  const format = selectExportFormat ? selectExportFormat.value : 'jsonld';
  const exportUrl = getExportUrl(format, appState.selectedDoc);
  window.open(exportUrl, '_blank');
}

export function initDocumentsModule() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const btnClearWorkspace = document.getElementById('btn-clear-workspace');
  const btnSyncKb = document.getElementById('btn-sync-kb');
  const btnSyncLabel = document.getElementById('btn-sync-label');
  const syncSpinner = document.getElementById('sync-spinner');
  const syncStatusText = document.getElementById('sync-status-text');
  const syncStateBadge = document.getElementById('sync-state-badge');
  const selectJsonldDoc = document.getElementById('select-jsonld-doc');
  const selectChatScope = document.getElementById('select-chat-scope');
  const btnDownloadExport = document.getElementById('btn-download-export');
  const btnDownloadJsonld = document.getElementById('btn-download-jsonld');
  const btnSyncGraphdb = document.getElementById('btn-sync-graphdb');

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length) handleUploadFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length) handleUploadFiles(e.target.files);
    });
  }

  async function handleUploadFiles(fileList) {
    if (syncSpinner) syncSpinner.classList.remove('hidden');
    if (syncStatusText) syncStatusText.textContent = 'Uploading files...';

    try {
      const data = await uploadFiles(fileList);
      if (data.rejected && data.rejected.length) {
        const reasons = data.rejected.map(r => `${r.file}: ${r.reason}`).join('\n');
        alert('Some files were rejected:\n' + reasons);
      }
      await fetchDocumentsList();
      updateIndexStatus(false);
    } catch (e) {
      alert('File upload failed: ' + e);
    } finally {
      if (syncSpinner) syncSpinner.classList.add('hidden');
    }
  }

  if (selectJsonldDoc) {
    selectJsonldDoc.addEventListener('change', (e) => {
      selectActiveDocument(e.target.value);
    });
  }

  if (selectChatScope) {
    selectChatScope.addEventListener('change', () => {
      updateChatScopeUI();
    });
  }

  if (btnClearWorkspace) {
    btnClearWorkspace.addEventListener('click', async () => {
      if (confirm('Clear all uploaded files and workspace index?')) {
        try {
          await clearWorkspace();
          appState.selectedDoc = '';
          await fetchDocumentsList();
          updateIndexStatus(false);
        } catch (e) {
          alert('Failed to clear workspace: ' + e);
        }
      }
    });
  }

  if (btnSyncKb) {
    btnSyncKb.addEventListener('click', async () => {
      btnSyncKb.disabled = true;
      btnSyncKb.className = 'btn btn-sync btn-block';
      if (btnSyncLabel) btnSyncLabel.textContent = 'Syncing Vector DB...';
      if (syncStateBadge) {
        syncStateBadge.className = 'sync-badge badge-warning';
        syncStateBadge.textContent = 'Syncing...';
      }
      if (syncSpinner) syncSpinner.classList.remove('hidden');
      if (syncStatusText) syncStatusText.textContent = 'Parsing & Indexing Vector DB...';

      try {
        const data = await syncKnowledgeBase({
          parser: appState.settings.parser,
          llamaparseKey: appState.settings.llamaparseKey,
          unstructuredKey: appState.settings.unstructuredKey
        });
        if (data.success) {
          updateIndexStatus(true);
          if (syncStatusText) syncStatusText.textContent = 'Vector DB Ready';
          setTimeout(() => {
            if (syncStatusText && syncStatusText.textContent.includes('Ready')) syncStatusText.textContent = '';
          }, 4000);
        }
      } catch (e) {
        alert('Sync failed: ' + e);
        if (syncStatusText) syncStatusText.textContent = 'Sync Failed';
        updateIndexStatus(false);
      } finally {
        if (syncSpinner) syncSpinner.classList.add('hidden');
        updateIndexStatus(appState.isIndexed);
      }
    });
  }

  if (btnDownloadExport) btnDownloadExport.addEventListener('click', triggerDocumentExport);
  if (btnDownloadJsonld) btnDownloadJsonld.addEventListener('click', triggerDocumentExport);

  if (btnSyncGraphdb) {
    btnSyncGraphdb.addEventListener('click', async () => {
      if (!appState.selectedDoc) return;
      btnSyncGraphdb.disabled = true;
      const origText = btnSyncGraphdb.innerHTML;
      btnSyncGraphdb.innerHTML = '<span class="spinner"></span> <span>Syncing...</span>';

      try {
        const data = await syncGraphdb({
          file_name: appState.selectedDoc,
          target_type: appState.settings.graphdbType || 'neo4j',
          uri: appState.settings.neo4jUri || 'bolt://localhost:7687',
          user: appState.settings.neo4jUser || 'neo4j',
          password: appState.settings.neo4jPass || '',
          database: appState.settings.neo4jDb || 'neo4j',
          endpoint_url: appState.settings.sparqlUrl || ''
        });

        if (data.success) {
          alert(`Live Sync Success.\n${data.message}`);
        } else {
          alert(`Sync Notice:\n${data.message || JSON.stringify(data)}`);
        }
      } catch (e) {
        alert(`Sync failed: ${e}`);
      } finally {
        btnSyncGraphdb.disabled = false;
        btnSyncGraphdb.innerHTML = origText;
      }
    });
  }
}
