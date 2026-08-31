/**
 * CORPUSLD: Modern Client Controller
 * Native ES Module Entry Point & System Orchestrator
 */

import { appState, loadSettingsFromStorage, updateIndexStatus } from './state.js';
import { fetchSystemStatus } from './api.js';
import { initSettingsModule, applySettingsToUI } from './modules/settings.js';
import { initDocumentsModule, fetchDocumentsList } from './modules/documents.js';
import { initExtractionModule } from './modules/extraction.js';
import { initChatModule } from './modules/chat.js';
import { initScholarCopyHandlers } from './renderers/scholar.js';

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Initialize UI Submodules
  initSettingsModule();
  initDocumentsModule();
  initExtractionModule();
  initChatModule();
  initScholarCopyHandlers();

  // 2. Setup Tabs Controller
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      if (targetId) {
        document.getElementById(targetId)?.classList.add('active');
      }
    });
  });

  const subtabBtns = document.querySelectorAll('.subtab-btn');
  const subtabPanels = document.querySelectorAll('.subtab-panel');
  subtabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      subtabBtns.forEach(b => b.classList.remove('active'));
      subtabPanels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-subtab');
      if (targetId) {
        document.getElementById(targetId)?.classList.add('active');
      }
    });
  });

  // 3. Mobile Navigation & Drawer
  const appSidebar = document.getElementById('app-sidebar');
  const btnMobileSidebar = document.getElementById('btn-mobile-sidebar');
  const btnCloseSidebar = document.getElementById('btn-close-sidebar');
  const sidebarBackdrop = document.getElementById('sidebar-backdrop');
  const settingsModal = document.getElementById('settings-modal');

  const closeMobileSidebar = () => {
    if (appSidebar) appSidebar.classList.remove('open');
    if (sidebarBackdrop) sidebarBackdrop.classList.add('hidden');
  };

  if (btnMobileSidebar && appSidebar && sidebarBackdrop) {
    btnMobileSidebar.addEventListener('click', () => {
      appSidebar.classList.add('open');
      sidebarBackdrop.classList.remove('hidden');
    });
  }

  if (btnCloseSidebar) btnCloseSidebar.addEventListener('click', closeMobileSidebar);
  if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeMobileSidebar);

  // 4. Keyboard Shortcuts & Accessibility
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (settingsModal && !settingsModal.classList.contains('hidden')) {
        settingsModal.classList.add('hidden');
      }
      closeMobileSidebar();
    }
  });

  // 5. Load Stored Settings & Initial State
  loadSettingsFromStorage();
  applySettingsToUI();

  // 6. Fetch System & Model Status
  try {
    const statusData = await fetchSystemStatus();
    appState.isIndexed = statusData.is_indexed;
    appState.localModels = statusData.available_local_models || ['qwen2.5:3b'];

    const settingOllamaModel = document.getElementById('setting-ollama-model');
    if (settingOllamaModel) {
      settingOllamaModel.innerHTML = '';
      appState.localModels.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        if (m === appState.settings.ollamaModel) opt.selected = true;
        settingOllamaModel.appendChild(opt);
      });
    }
    updateIndexStatus(statusData.is_indexed);
  } catch (e) {
    console.error('Initial status fetch failed:', e);
  }

  // 7. Fetch Documents List
  await fetchDocumentsList();
});
