import { appState } from '../state.js';
import { renderValidatorReport } from './validator.js';
import { renderAuthorTab } from './tabs/authorTab.js';
import { renderKgTab } from './tabs/kgTab.js';
import { renderEntitiesTab } from './tabs/entitiesTab.js';
import { renderMetricsTab } from './tabs/metricsTab.js';
import { renderSectionsTab } from './tabs/sectionsTab.js';
import { renderTablesTab } from './tabs/tablesTab.js';
import { renderProceduresTab } from './tabs/proceduresTab.js';
import { renderFormulasTab } from './tabs/formulasTab.js';
import { renderTermsTab } from './tabs/termsTab.js';
import { renderRefsTab } from './tabs/refsTab.js';
import { renderLogsTab } from './tabs/logsTab.js';
import { renderRawTab } from './tabs/rawTab.js';
import { renderScholarTab } from './scholar.js';

const ICONS = {
  doc: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`,
  globe: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
  calendar: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>`,
  link: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>`,
  users: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>`,
  citations: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>`,
  alert: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`
};

export function renderJsonLdData(rawPayload) {
  const jsonldResultsContainer = document.getElementById('jsonld-results-container');
  const btnDownloadExport = document.getElementById('btn-download-export');
  const btnDownloadJsonld = document.getElementById('btn-download-jsonld');
  const selectExportFormat = document.getElementById('select-export-format');
  const btnSyncGraphdb = document.getElementById('btn-sync-graphdb');
  const btnCopyScholarTags = document.getElementById('btn-copy-scholar-tags');

  if (jsonldResultsContainer) jsonldResultsContainer.classList.remove('hidden');
  if (btnDownloadJsonld) btnDownloadJsonld.disabled = false;
  if (selectExportFormat) selectExportFormat.disabled = false;
  if (btnDownloadExport) btnDownloadExport.disabled = false;
  if (btnSyncGraphdb) btnSyncGraphdb.disabled = false;

  const data = rawPayload.schema_json_ld || rawPayload;
  const telemetry = rawPayload.telemetry || {};

  // Extract clean DOI if present
  let cleanDoi = '';
  const doiVal = data.identifier;
  if (Array.isArray(doiVal)) {
    for (const it of doiVal) {
      if (typeof it === 'object' && String(it.propertyID).toUpperCase() === 'DOI' && it.value) {
        cleanDoi = String(it.value).trim();
        break;
      }
    }
  } else if (typeof doiVal === 'object' && doiVal?.value) {
    cleanDoi = String(doiVal.value).trim();
  } else if (typeof doiVal === 'string') {
    cleanDoi = doiVal.replace('https://doi.org/', '').trim();
  }
  if (!cleanDoi && data.sameAs && String(data.sameAs).includes('10.')) {
    const m = String(data.sameAs).match(/10\.\d{4,9}\/[^\s"\]\[}<>]+/);
    if (m) cleanDoi = m[0];
  }

  const hasDate = Boolean(data.datePublished && String(data.datePublished).trim() !== '' && String(data.datePublished).toLowerCase() !== 'null');
  const hasAuthor = Boolean(data.author && Array.isArray(data.author) && data.author.length > 0);
  const hasDoi = Boolean(cleanDoi);

  // Hero title & description
  const heroTitle = document.getElementById('doc-hero-title');
  const heroDesc = document.getElementById('doc-hero-desc');
  if (heroTitle) heroTitle.textContent = data.name || appState.selectedDoc;
  if (heroDesc) heroDesc.textContent = data.description || '-';

  // Hero metadata pills with clean SVG icons
  const typeStr = Array.isArray(data['@type']) ? data['@type'].join(', ') : (data['@type'] || 'ScholarlyArticle');
  const heroType = document.getElementById('hero-badge-type');
  if (heroType) {
    heroType.className = 'hero-meta-pill pill-valid';
    heroType.innerHTML = `${ICONS.doc} <span>${typeStr}</span>`;
  }

  const heroLang = document.getElementById('hero-badge-lang');
  if (heroLang) {
    heroLang.className = 'hero-meta-pill pill-valid';
    heroLang.innerHTML = `${ICONS.globe} <span>${data.inLanguage || 'en'}</span>`;
  }

  const heroDate = document.getElementById('hero-badge-date');
  if (heroDate) {
    if (hasDate) {
      heroDate.className = 'hero-meta-pill pill-valid';
      heroDate.innerHTML = `${ICONS.calendar} <span>${data.datePublished}</span>`;
    } else {
      heroDate.className = 'hero-meta-pill pill-missing';
      heroDate.innerHTML = `${ICONS.alert} <span>Date: Not Identified in PDF</span>`;
    }
  }

  const heroDoi = document.getElementById('hero-badge-doi');
  if (heroDoi) {
    if (hasDoi) {
      heroDoi.className = 'hero-meta-pill pill-valid';
      heroDoi.innerHTML = `${ICONS.link} <span>${cleanDoi}</span>`;
    } else {
      heroDoi.className = 'hero-meta-pill pill-warning';
      heroDoi.innerHTML = `${ICONS.alert} <span>DOI: Unindexed</span>`;
    }
  }

  const heroAuthors = document.getElementById('hero-badge-authors');
  if (heroAuthors) {
    if (hasAuthor) {
      heroAuthors.className = 'hero-meta-pill pill-valid';
      heroAuthors.innerHTML = `${ICONS.users} <span>${data.author.length} Authors</span>`;
    } else {
      heroAuthors.className = 'hero-meta-pill pill-missing';
      heroAuthors.innerHTML = `${ICONS.alert} <span>Author: 0 Detected</span>`;
    }
  }

  const heroCitations = document.getElementById('hero-badge-citations');
  if (heroCitations) {
    const citCount = data.citation?.length || data.references_or_sources?.length || 0;
    heroCitations.className = 'hero-meta-pill pill-valid';
    heroCitations.innerHTML = `${ICONS.citations} <span>${citCount} Citations</span>`;
  }

  // Render Validator & Completeness Alerts
  renderValidatorReport(data, rawPayload, { hasDate, hasAuthor, hasDoi });

  // Render Subtabs
  renderAuthorTab(data, { hasDate, hasDoi, cleanDoi });
  renderKgTab(data);
  renderEntitiesTab(data);
  renderMetricsTab(data);
  renderSectionsTab(data);
  renderTablesTab(data);
  renderProceduresTab(data);
  renderFormulasTab(data);
  renderTermsTab(data);
  renderRefsTab(data);
  renderScholarTab(data);
  renderLogsTab(telemetry);
  renderRawTab(data);

  if (btnCopyScholarTags) btnCopyScholarTags.disabled = false;
}
